import asyncio
import json
from decimal import Decimal
from datetime import datetime, timezone, time
import zoneinfo
from sqlalchemy import select
import yfinance as yf
import redis as sync_redis

from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.security import Security
from app.models.holding import Holding
from app.models.price import Price
from app.models.portfolio import Portfolio
from app.config import settings

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def _is_market_open() -> bool:
    """Return True if NSE is currently open (Mon–Fri, 09:15–15:30 IST)."""
    now_ist = datetime.now(_IST)
    if now_ist.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now_ist.time() <= _MARKET_CLOSE


async def _run_price_feed() -> tuple[list[str], dict[str, float]]:
    """Fetch prices for securities with known NSE symbols, rebuild affected projections.
    Returns (updated_isins, day_change_map).
    """
    from app.services.projections import rebuild_portfolio, rebuild_entity_allocation
    try:
        from app.services.alerts import check_and_write_alerts, check_price_drop_alerts
        _alerts_enabled = True
    except ImportError:
        _alerts_enabled = False

    async with task_db_session() as db:
        result = await db.execute(
            select(Security.isin, Security.nse_symbol, Security.sector).where(
                Security.nse_symbol.isnot(None)
            )
        )
        securities = result.all()

        if not securities:
            return [], {}

        updated_isins: list[str] = []
        day_change_map: dict[str, float] = {}
        now = datetime.now(timezone.utc)

        for isin, nse_symbol, existing_sector in securities:
            try:
                ticker = yf.Ticker(f"{nse_symbol}.NS")
                fast = ticker.fast_info
                price = fast.get("lastPrice") or fast.get("regularMarketPrice")
                if not price or float(price) <= 0:
                    continue

                day_change_pct_raw = fast.get("regularMarketChangePercent")
                day_change_pct = Decimal(str(round(float(day_change_pct_raw), 4))) if day_change_pct_raw is not None else None

                db.add(Price(
                    isin=isin,
                    price=Decimal(str(price)),
                    day_change_pct=day_change_pct,
                    source="yfinance",
                    fetched_at=now,
                ))
                updated_isins.append(isin)
                if day_change_pct is not None:
                    day_change_map[isin] = float(day_change_pct)

                # Sector enrichment — only fetch ticker.info when sector is missing (slow call)
                if existing_sector is None:
                    try:
                        info = ticker.info
                        sector = info.get("sector")
                        if sector:
                            sec_result = await db.execute(select(Security).where(Security.isin == isin))
                            sec = sec_result.scalar_one_or_none()
                            if sec:
                                sec.sector = sector
                    except Exception:
                        pass

            except Exception:
                continue

        if updated_isins:
            await db.flush()

            result = await db.execute(
                select(Holding.portfolio_id).distinct().where(
                    Holding.identifier.in_(updated_isins)
                )
            )
            portfolio_ids = result.scalars().all()

            for portfolio_id in portfolio_ids:
                portfolio = await db.get(Portfolio, portfolio_id)
                if portfolio:
                    await rebuild_portfolio(portfolio_id, db)
                    await rebuild_entity_allocation(portfolio.entity_id, db)
                    if _alerts_enabled:
                        await check_and_write_alerts(portfolio_id, db)
                        await check_price_drop_alerts(portfolio_id, day_change_map, db)

        await db.commit()

    return updated_isins, day_change_map


@celery_app.task(bind=True)
def fetch_prices(self):
    """Celery Beat task: fetch NSE prices every 5 minutes during market hours."""
    if not _is_market_open():
        return {"skipped": True, "reason": "outside market hours"}
    try:
        updated_isins, _ = asyncio.run(_run_price_feed())

        if updated_isins:
            r = sync_redis.from_url(settings.redis_url)
            r.publish(
                "orbit:prices",
                json.dumps({
                    "updated_isins": updated_isins,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            )
            r.close()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60, max_retries=3)
