import uuid
import pytest
import pytest_asyncio
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.services.auth import hash_password
from app.services.reconciliation import run_reconciliation


@pytest_asyncio.fixture
async def pms_portfolio(db_session):
    slug = f"recon-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Recon Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"recon-owner-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"RCNAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="Recon Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.pms, provider_name="Motilal PMS")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    return portfolio


async def test_matched_bank_entry_no_flag(pms_portfolio, db_session):
    """Bank debit matches a SecurityBought within tolerance → no ReconciliationFlagged."""
    events = [
        PortfolioEvent(
            portfolio_id=pms_portfolio.id,
            event_type=EventType.security_bought,
            payload={"isin": "INE009A01021", "security_name": "Infosys", "quantity": 10, "price": 1500.0, "amount": 15000.0, "broker": "Motilal"},
            version=1,
            event_date=date(2026, 3, 10),
        ),
        PortfolioEvent(
            portfolio_id=pms_portfolio.id,
            event_type=EventType.bank_entry_recorded,
            payload={"amount": 15000.0, "type": "debit", "narration": "BUY INFOSYS"},
            version=2,
            event_date=date(2026, 3, 10),
        ),
    ]
    db_session.add_all(events)
    await db_session.commit()

    flags = await run_reconciliation(pms_portfolio.id, db_session)
    await db_session.commit()
    assert flags == 0


async def test_unmatched_bank_debit_creates_flag(pms_portfolio, db_session):
    """Bank debit with no matching SecurityBought → ReconciliationFlagged written."""
    events = [
        PortfolioEvent(
            portfolio_id=pms_portfolio.id,
            event_type=EventType.bank_entry_recorded,
            payload={"amount": 50000.0, "type": "debit", "narration": "UNKNOWN DEBIT"},
            version=1,
            event_date=date(2026, 3, 15),
        ),
    ]
    db_session.add_all(events)
    await db_session.commit()

    flags = await run_reconciliation(pms_portfolio.id, db_session)
    await db_session.commit()
    assert flags == 1

    result = await db_session.execute(
        select(PortfolioEvent).where(
            PortfolioEvent.portfolio_id == pms_portfolio.id,
            PortfolioEvent.event_type == EventType.reconciliation_flagged,
        )
    )
    flag_events = result.scalars().all()
    assert len(flag_events) == 1
    assert flag_events[0].payload["expected_event_type"] == "SecurityBought"


async def test_amount_tolerance(pms_portfolio, db_session):
    """Bank amount within 0.5% of SecurityBought → match (no flag)."""
    events = [
        PortfolioEvent(
            portfolio_id=pms_portfolio.id,
            event_type=EventType.security_bought,
            payload={"isin": "INE040A01034", "security_name": "HDFC Bank", "quantity": 5, "price": 1500.0, "amount": 7500.0, "broker": "Motilal"},
            version=1,
            event_date=date(2026, 3, 20),
        ),
        PortfolioEvent(
            portfolio_id=pms_portfolio.id,
            event_type=EventType.bank_entry_recorded,
            # 7530 is within 0.5% of 7500 (diff = 30/7500 = 0.4%)
            payload={"amount": 7530.0, "type": "debit", "narration": "BUY HDFCBANK"},
            version=2,
            event_date=date(2026, 3, 20),
        ),
    ]
    db_session.add_all(events)
    await db_session.commit()

    flags = await run_reconciliation(pms_portfolio.id, db_session)
    await db_session.commit()
    assert flags == 0
