import uuid
import zoneinfo
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertType, Severity
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.models.portfolio import Portfolio

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def _today_ist_start() -> datetime:
    now = datetime.now(_IST)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _already_alerted(
    alert_type: AlertType,
    portfolio_id: uuid.UUID,
    identifier: str | None,
    db: AsyncSession,
) -> bool:
    filters = [
        Alert.alert_type == alert_type,
        Alert.portfolio_id == portfolio_id,
        Alert.dismissed_at.is_(None),
        Alert.created_at >= _today_ist_start(),
    ]
    if identifier is not None:
        filters.append(Alert.identifier == identifier)
    result = await db.execute(select(Alert.id).where(and_(*filters)).limit(1))
    return result.scalar_one_or_none() is not None


async def check_and_write_alerts(portfolio_id: uuid.UUID, db: AsyncSession) -> None:
    """Check concentration and drawdown rules for a portfolio."""
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        return

    holdings_result = await db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    )
    holdings = holdings_result.scalars().all()

    pm_result = await db.execute(
        select(PerformanceMetrics).where(PerformanceMetrics.portfolio_id == portfolio_id)
    )
    pm = pm_result.scalar_one_or_none()

    # Concentration rule: single holding >= 20% of portfolio value
    total_value = sum(h.current_value or Decimal("0") for h in holdings)
    if total_value > 0:
        for h in holdings:
            val = h.current_value or Decimal("0")
            weight = float(val / total_value * 100)
            if weight >= 20:
                if not await _already_alerted(AlertType.concentration, portfolio_id, h.identifier, db):
                    db.add(Alert(
                        entity_id=portfolio.entity_id,
                        portfolio_id=portfolio_id,
                        identifier=h.identifier,
                        alert_type=AlertType.concentration,
                        severity=Severity.warning,
                        message=f"{h.security_name} is {weight:.1f}% of the portfolio",
                        payload={"identifier": h.identifier, "weight_pct": weight},
                    ))

    # Drawdown rule: unrealized P&L <= -15% of invested
    if pm and pm.total_invested > 0:
        drawdown = float(pm.unrealized_pnl / pm.total_invested * 100)
        if drawdown <= -15:
            if not await _already_alerted(AlertType.drawdown, portfolio_id, None, db):
                db.add(Alert(
                    entity_id=portfolio.entity_id,
                    portfolio_id=portfolio_id,
                    identifier=None,
                    alert_type=AlertType.drawdown,
                    severity=Severity.critical,
                    message=f"Portfolio is down {abs(drawdown):.1f}% (unrealized loss)",
                    payload={"drawdown_pct": drawdown},
                ))


async def check_price_drop_alerts(
    portfolio_id: uuid.UUID,
    day_change_map: dict[str, float],
    db: AsyncSession,
) -> None:
    """Check price drop rules using the day_change_map from the latest price fetch."""
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        return

    holdings_result = await db.execute(
        select(Holding.identifier, Holding.security_name).where(
            Holding.portfolio_id == portfolio_id
        )
    )
    holdings = holdings_result.all()

    for identifier, security_name in holdings:
        change = day_change_map.get(identifier)
        if change is None:
            continue

        if change <= -10:
            alert_type = AlertType.price_drop_critical
            sev = Severity.critical
            message = f"{security_name} fell {abs(change):.1f}% today"
        elif change <= -5:
            alert_type = AlertType.price_drop
            sev = Severity.warning
            message = f"{security_name} fell {abs(change):.1f}% today"
        else:
            continue

        if not await _already_alerted(alert_type, portfolio_id, identifier, db):
            db.add(Alert(
                entity_id=portfolio.entity_id,
                portfolio_id=portfolio_id,
                identifier=identifier,
                alert_type=alert_type,
                severity=sev,
                message=message,
                payload={"identifier": identifier, "day_change_pct": change},
            ))
