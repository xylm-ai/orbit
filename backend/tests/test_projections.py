import uuid
import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import date
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.models.allocation import AllocationSnapshot
from app.services.auth import hash_password
from app.services.projections import rebuild_portfolio, rebuild_entity_allocation


@pytest_asyncio.fixture
async def portfolio_with_events(db_session):
    slug = f"proj-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Proj Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"proj-owner-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"PRJAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="Proj Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    # Write events directly (bypass confirm endpoint)
    events = [
        PortfolioEvent(
            portfolio_id=portfolio.id,
            event_type=EventType.security_bought,
            payload={"isin": "INE009A01021", "security_name": "Infosys", "quantity": 10, "price": 1500.0, "amount": 15000.0, "broker": "Zerodha"},
            version=1,
            event_date=date(2026, 1, 10),
        ),
        PortfolioEvent(
            portfolio_id=portfolio.id,
            event_type=EventType.security_bought,
            payload={"isin": "INE009A01021", "security_name": "Infosys", "quantity": 5, "price": 1600.0, "amount": 8000.0, "broker": "Zerodha"},
            version=2,
            event_date=date(2026, 2, 5),
        ),
        PortfolioEvent(
            portfolio_id=portfolio.id,
            event_type=EventType.security_sold,
            payload={"isin": "INE009A01021", "security_name": "Infosys", "quantity": 5, "price": 1700.0, "amount": 8500.0, "broker": "Zerodha"},
            version=3,
            event_date=date(2026, 3, 1),
        ),
    ]
    db_session.add_all(events)
    await db_session.commit()

    return user, entity, portfolio


async def test_rebuild_portfolio_creates_holdings(portfolio_with_events, db_session):
    _, _, portfolio = portfolio_with_events
    await rebuild_portfolio(portfolio.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Holding).where(Holding.portfolio_id == portfolio.id)
    )
    holdings = result.scalars().all()
    assert len(holdings) == 1
    h = holdings[0]
    assert h.identifier == "INE009A01021"
    assert h.quantity == Decimal("10")  # bought 10+5, sold 5 → 10 remain


async def test_rebuild_portfolio_avg_cost(portfolio_with_events, db_session):
    _, _, portfolio = portfolio_with_events
    await rebuild_portfolio(portfolio.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Holding).where(Holding.portfolio_id == portfolio.id)
    )
    h = result.scalar_one()
    # Allow small rounding difference due to Numeric precision (6 vs 2 decimal places)
    assert abs(h.avg_cost_per_unit - h.total_cost / h.quantity) < Decimal("0.01")


async def test_rebuild_portfolio_realized_pnl(portfolio_with_events, db_session):
    _, _, portfolio = portfolio_with_events
    await rebuild_portfolio(portfolio.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Holding).where(Holding.portfolio_id == portfolio.id)
    )
    h = result.scalar_one()
    # Sold 5 shares at 1700 = 8500. Cost of those 5 = 5 * (23000/15) ≈ 7666.67
    # Realized PnL ≈ 8500 - 7666.67 = 833.33
    assert h.realized_pnl > 0


async def test_rebuild_portfolio_creates_performance_metrics(portfolio_with_events, db_session):
    _, _, portfolio = portfolio_with_events
    await rebuild_portfolio(portfolio.id, db_session)
    await db_session.commit()

    pm = await db_session.scalar(
        select(PerformanceMetrics).where(PerformanceMetrics.portfolio_id == portfolio.id)
    )
    assert pm is not None
    assert pm.total_invested == Decimal("23000")


async def test_rebuild_entity_allocation(portfolio_with_events, db_session):
    _, entity, portfolio = portfolio_with_events
    await rebuild_portfolio(portfolio.id, db_session)
    await rebuild_entity_allocation(entity.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(AllocationSnapshot).where(AllocationSnapshot.entity_id == entity.id)
    )
    snapshots = result.scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].identifier == "INE009A01021"
    assert snapshots[0].weight_pct == Decimal("100")  # only holding, 100% weight (no price data)
