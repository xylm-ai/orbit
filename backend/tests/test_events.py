import pytest
from datetime import date
from sqlalchemy import func, select
from app.services.events import append_event, get_events, VersionConflictError
from app.models.event import EventType, PortfolioEvent

async def _make_portfolio(db_session):
    from app.models import Family, Entity, EntityType, Portfolio, PortfolioType
    import secrets
    family = Family(name="Test", inbound_email_slug=secrets.token_urlsafe(6))
    db_session.add(family)
    await db_session.flush()
    entity = Entity(family_id=family.id, name="E", type=EntityType.individual)
    db_session.add(entity)
    await db_session.flush()
    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    return portfolio.id

@pytest.mark.asyncio
async def test_append_event_increments_version(db_session):
    portfolio_id = await _make_portfolio(db_session)

    e1 = await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE002A01018", "quantity": 10, "price": 2400.0, "amount": 24000.0},
        event_date=date(2026, 4, 5))
    e2 = await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE009A01021", "quantity": 5, "price": 1500.0, "amount": 7500.0},
        event_date=date(2026, 4, 6))

    assert e1.version == 1
    assert e2.version == 2

@pytest.mark.asyncio
async def test_get_events_returns_ordered(db_session):
    portfolio_id = await _make_portfolio(db_session)

    await append_event(db_session, portfolio_id, EventType.opening_balance_set,
        {"total_value": 100000.0, "holdings": []},
        event_date=date(2026, 4, 1))
    await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE002A01018", "quantity": 10, "price": 2400.0, "amount": 24000.0},
        event_date=date(2026, 4, 5))

    events = await get_events(db_session, portfolio_id)
    assert len(events) == 2
    assert events[0].event_type == EventType.opening_balance_set
    assert events[1].event_type == EventType.security_bought

@pytest.mark.asyncio
async def test_events_are_never_duplicated(db_session):
    portfolio_id = await _make_portfolio(db_session)

    await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "TEST", "quantity": 1, "price": 100.0, "amount": 100.0},
        event_date=date(2026, 4, 5))

    count = await db_session.scalar(
        select(func.count()).select_from(PortfolioEvent).where(PortfolioEvent.portfolio_id == portfolio_id)
    )
    assert count == 1
