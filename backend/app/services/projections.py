import uuid
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from app.models.event import PortfolioEvent, EventType
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.models.allocation import AllocationSnapshot
from app.models.price import Price
from app.models.portfolio import Portfolio
from app.models.security import Security


async def _get_latest_prices(identifiers: list[str], db: AsyncSession) -> dict[str, Decimal]:
    """Single query — most recent price per identifier."""
    if not identifiers:
        return {}
    subq = (
        select(Price.isin, func.max(Price.fetched_at).label("max_fetched"))
        .where(Price.isin.in_(identifiers))
        .group_by(Price.isin)
        .subquery()
    )
    result = await db.execute(
        select(Price.isin, Price.price).join(
            subq,
            (Price.isin == subq.c.isin) & (Price.fetched_at == subq.c.max_fetched),
        )
    )
    return {row.isin: row.price for row in result.all()}


async def rebuild_portfolio(portfolio_id: uuid.UUID, db: AsyncSession) -> None:
    """Replay all events for a portfolio to rebuild Holdings and PerformanceMetrics.
    Uses db.flush() — caller must db.commit() afterwards.
    """
    result = await db.execute(
        select(PortfolioEvent)
        .where(PortfolioEvent.portfolio_id == portfolio_id)
        .order_by(PortfolioEvent.event_date, PortfolioEvent.version)
    )
    events = result.scalars().all()

    holdings_map: dict[str, dict] = {}
    cash_flows: list[tuple[date, Decimal]] = []

    for event in events:
        p = event.payload
        ed = event.event_date

        if event.event_type == EventType.opening_balance_set:
            for h in p.get("holdings", []):
                ident = h.get("isin") or h.get("scheme_code", "")
                if not ident:
                    continue
                qty = Decimal(str(h.get("quantity", 0)))
                avg_cost = Decimal(str(h.get("avg_cost", 0)))
                holdings_map[ident] = {
                    "security_name": h.get("security_name", ""),
                    "asset_class": h.get("asset_class", "equity"),
                    "quantity": qty,
                    "total_cost": qty * avg_cost,
                    "realized_pnl": Decimal("0"),
                    "dividend_income": Decimal("0"),
                }
            cash_flows.append((ed, -Decimal(str(p.get("total_value", 0)))))

        elif event.event_type == EventType.security_bought:
            ident = p.get("isin", "")
            if not ident:
                continue
            amount = Decimal(str(p.get("amount", 0)))
            qty = Decimal(str(p.get("quantity", 0)))
            if ident not in holdings_map:
                holdings_map[ident] = {
                    "security_name": p.get("security_name", ""),
                    "asset_class": "equity",
                    "quantity": Decimal("0"),
                    "total_cost": Decimal("0"),
                    "realized_pnl": Decimal("0"),
                    "dividend_income": Decimal("0"),
                }
            holdings_map[ident]["quantity"] += qty
            holdings_map[ident]["total_cost"] += amount
            cash_flows.append((ed, -amount))

        elif event.event_type == EventType.security_sold:
            ident = p.get("isin", "")
            if not ident or ident not in holdings_map:
                continue
            amount = Decimal(str(p.get("amount", 0)))
            qty = Decimal(str(p.get("quantity", 0)))
            h = holdings_map[ident]
            if h["quantity"] > 0:
                cost_per_unit = h["total_cost"] / h["quantity"]
                cost_of_sold = cost_per_unit * qty
                h["realized_pnl"] += amount - cost_of_sold
                h["quantity"] = max(Decimal("0"), h["quantity"] - qty)
                h["total_cost"] = max(Decimal("0"), h["total_cost"] - cost_of_sold)
            cash_flows.append((ed, amount))

        elif event.event_type == EventType.dividend_received:
            ident = p.get("isin", "")
            amount = Decimal(str(p.get("amount", 0)))
            if ident in holdings_map:
                holdings_map[ident]["dividend_income"] += amount
            cash_flows.append((ed, amount))

        elif event.event_type == EventType.mf_units_purchased:
            ident = p.get("scheme_code", "")
            if not ident:
                continue
            amount = Decimal(str(p.get("amount", 0)))
            units = Decimal(str(p.get("units", 0)))
            if ident not in holdings_map:
                holdings_map[ident] = {
                    "security_name": p.get("scheme_name", ""),
                    "asset_class": "mf",
                    "quantity": Decimal("0"),
                    "total_cost": Decimal("0"),
                    "realized_pnl": Decimal("0"),
                    "dividend_income": Decimal("0"),
                }
            holdings_map[ident]["quantity"] += units
            holdings_map[ident]["total_cost"] += amount
            cash_flows.append((ed, -amount))

        elif event.event_type == EventType.mf_units_redeemed:
            ident = p.get("scheme_code", "")
            if not ident or ident not in holdings_map:
                continue
            amount = Decimal(str(p.get("amount", 0)))
            units = Decimal(str(p.get("units", 0)))
            h = holdings_map[ident]
            if h["quantity"] > 0:
                cost_per_unit = h["total_cost"] / h["quantity"]
                cost_of_sold = cost_per_unit * units
                h["realized_pnl"] += amount - cost_of_sold
                h["quantity"] = max(Decimal("0"), h["quantity"] - units)
                h["total_cost"] = max(Decimal("0"), h["total_cost"] - cost_of_sold)
            cash_flows.append((ed, amount))

    # Current prices
    active_identifiers = [ident for ident, h in holdings_map.items() if h["quantity"] > 0]
    prices_map = await _get_latest_prices(active_identifiers, db)

    total_current_value = sum(
        h["quantity"] * prices_map[ident]
        for ident, h in holdings_map.items()
        if h["quantity"] > 0 and ident in prices_map
    ) or Decimal("0")

    total_invested = sum(-cf[1] for cf in cash_flows if cf[1] < 0) if cash_flows else Decimal("0")
    realized_inflows = sum(cf[1] for cf in cash_flows if cf[1] > 0) if cash_flows else Decimal("0")
    realized_pnl = sum(h["realized_pnl"] for h in holdings_map.values())
    remaining_total_cost = sum(
        h["total_cost"] for h in holdings_map.values() if h["quantity"] > 0
    )
    unrealized_pnl = total_current_value - remaining_total_cost

    # XIRR
    xirr_val = None
    if cash_flows and total_current_value > 0:
        try:
            import pyxirr
            cf_dates = [cf[0] for cf in cash_flows] + [date.today()]
            cf_amounts = [float(cf[1]) for cf in cash_flows] + [float(total_current_value)]
            xirr_val = pyxirr.xirr(cf_dates, cf_amounts)
            xirr_val = float(xirr_val) if xirr_val is not None else None
        except Exception:
            xirr_val = None

    # CAGR
    cagr_val = None
    if cash_flows and total_invested > 0 and total_current_value > 0:
        years = max((date.today() - cash_flows[0][0]).days / 365.25, 0.01)
        total_wealth = realized_inflows + total_current_value
        try:
            cagr_val = float((total_wealth / float(total_invested)) ** (1.0 / years) - 1)
        except Exception:
            cagr_val = None

    abs_return_pct = None
    if total_invested > 0:
        abs_return_pct = float(
            (realized_inflows + total_current_value - total_invested) / total_invested
        )

    # Clear old holdings
    await db.execute(delete(Holding).where(Holding.portfolio_id == portfolio_id))

    now = datetime.now(timezone.utc)

    for ident, h_data in holdings_map.items():
        qty = h_data["quantity"]
        if qty <= 0:
            continue
        total_cost = h_data["total_cost"]
        avg_cost = total_cost / qty
        current_price = prices_map.get(ident)
        current_value = qty * current_price if current_price is not None else None
        unrealised = (current_value - total_cost) if current_value is not None else None
        db.add(Holding(
            portfolio_id=portfolio_id,
            identifier=ident,
            security_name=h_data["security_name"],
            asset_class=h_data["asset_class"],
            quantity=qty,
            avg_cost_per_unit=avg_cost,
            total_cost=total_cost,
            realized_pnl=h_data["realized_pnl"],
            dividend_income=h_data["dividend_income"],
            current_price=current_price,
            current_value=current_value,
            unrealized_pnl=unrealised,
            as_of=now,
        ))

    # Upsert PerformanceMetrics
    pm = await db.scalar(
        select(PerformanceMetrics).where(PerformanceMetrics.portfolio_id == portfolio_id)
    )
    if pm:
        pm.xirr = Decimal(str(xirr_val)) if xirr_val is not None else None
        pm.cagr = Decimal(str(cagr_val)) if cagr_val is not None else None
        pm.total_invested = total_invested
        pm.current_value = total_current_value
        pm.realized_pnl = Decimal(str(realized_pnl))
        pm.unrealized_pnl = Decimal(str(unrealized_pnl))
        pm.abs_return_pct = Decimal(str(abs_return_pct)) if abs_return_pct is not None else None
        pm.as_of = now
    else:
        db.add(PerformanceMetrics(
            portfolio_id=portfolio_id,
            xirr=Decimal(str(xirr_val)) if xirr_val is not None else None,
            cagr=Decimal(str(cagr_val)) if cagr_val is not None else None,
            total_invested=total_invested,
            current_value=total_current_value,
            realized_pnl=Decimal(str(realized_pnl)),
            unrealized_pnl=Decimal(str(unrealized_pnl)),
            abs_return_pct=Decimal(str(abs_return_pct)) if abs_return_pct is not None else None,
            as_of=now,
        ))

    await db.flush()


async def rebuild_entity_allocation(entity_id: uuid.UUID, db: AsyncSession) -> None:
    """Rebuild AllocationSnapshot for all portfolios under an entity.
    Uses db.flush() — caller must db.commit() afterwards.
    """
    result = await db.execute(
        select(Portfolio.id).where(Portfolio.entity_id == entity_id)
    )
    portfolio_ids = result.scalars().all()

    if not portfolio_ids:
        return

    result = await db.execute(
        select(Holding).where(
            Holding.portfolio_id.in_(portfolio_ids),
            Holding.quantity > 0,
        )
    )
    all_holdings = result.scalars().all()

    if not all_holdings:
        return

    total_value = sum(h.current_value or Decimal("0") for h in all_holdings)

    # Sector lookup from Securities
    isins = [h.identifier for h in all_holdings if h.asset_class != "mf"]
    sectors_map: dict[str, str | None] = {}
    if isins:
        result = await db.execute(
            select(Security.isin, Security.sector).where(Security.isin.in_(isins))
        )
        sectors_map = {row.isin: row.sector for row in result.all()}

    await db.execute(
        delete(AllocationSnapshot).where(AllocationSnapshot.entity_id == entity_id)
    )

    now = datetime.now(timezone.utc)
    for h in all_holdings:
        value = h.current_value or Decimal("0")
        if total_value > 0:
            weight = value / total_value * 100
        else:
            weight = Decimal("100") / len(all_holdings)
        db.add(AllocationSnapshot(
            entity_id=entity_id,
            asset_class=h.asset_class,
            sector=sectors_map.get(h.identifier),
            identifier=h.identifier,
            security_name=h.security_name,
            value=value,
            weight_pct=weight,
            as_of=now,
        ))

    await db.flush()
