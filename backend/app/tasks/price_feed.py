import asyncio
import json
from decimal import Decimal
from datetime import datetime, timezone
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


async def _run_price_feed() -> list[str]:
    """Fetch prices for securities with known NSE symbols, rebuild affected projections.
    Returns list of updated ISINs.
    """
    from app.services.projections import rebuild_portfolio, rebuild_entity_allocation

    async with task_db_session() as db:
        result = await db.execute(
            select(Security.isin, Security.nse_symbol).where(
                Security.nse_symbol.isnot(None)
            )
        )
        securities = result.all()

        if not securities:
            return []

        updated_isins: list[str] = []
        now = datetime.now(timezone.utc)

        for isin, nse_symbol in securities:
            try:
                ticker = yf.Ticker(f"{nse_symbol}.NS")
                info = ticker.fast_info
                price = info.get("lastPrice") or info.get("regularMarketPrice")
                if price and float(price) > 0:
                    db.add(Price(
                        isin=isin,
                        price=Decimal(str(price)),
                        source="yfinance",
                        fetched_at=now,
                    ))
                    updated_isins.append(isin)
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

        await db.commit()

    return updated_isins


@celery_app.task(bind=True)
def fetch_prices(self):
    """Celery Beat task: fetch NSE prices every 15 minutes."""
    try:
        updated_isins = asyncio.run(_run_price_feed())

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
