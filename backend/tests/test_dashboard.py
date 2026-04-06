import uuid
import pytest
import pytest_asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def dashboard_setup(db_session):
    slug = f"dash-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Dash Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"dash-owner-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"DSHAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="Dash Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    holding = Holding(
        portfolio_id=portfolio.id,
        identifier="INE009A01021",
        security_name="Infosys",
        asset_class="equity",
        quantity=Decimal("10"),
        avg_cost_per_unit=Decimal("1500"),
        total_cost=Decimal("15000"),
        realized_pnl=Decimal("0"),
        dividend_income=Decimal("0"),
        current_price=Decimal("1800"),
        current_value=Decimal("18000"),
        unrealized_pnl=Decimal("3000"),
    )
    db_session.add(holding)

    pm = PerformanceMetrics(
        portfolio_id=portfolio.id,
        total_invested=Decimal("15000"),
        current_value=Decimal("18000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("3000"),
        abs_return_pct=Decimal("0.2"),
    )
    db_session.add(pm)

    event = PortfolioEvent(
        portfolio_id=portfolio.id,
        event_type=EventType.security_bought,
        payload={"isin": "INE009A01021", "security_name": "Infosys", "quantity": 10, "price": 1500.0, "amount": 15000.0, "broker": "Zerodha"},
        version=1,
        event_date=date(2026, 1, 10),
    )
    db_session.add(event)

    flag_event = PortfolioEvent(
        portfolio_id=portfolio.id,
        event_type=EventType.reconciliation_flagged,
        payload={"bank_entry_id": str(uuid.uuid4()), "expected_event_type": "SecurityBought", "amount": "5000", "date": "2026-01-05"},
        version=2,
        event_date=date(2026, 1, 5),
    )
    db_session.add(flag_event)

    await db_session.commit()
    return user, entity, portfolio


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def test_summary_returns_net_worth(client, dashboard_setup):
    user, _, _ = dashboard_setup
    token = await _login(client, user.email, "Password1!")

    resp = await client.get("/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_net_worth"] == 18000.0
    assert len(body["entities"]) == 1


async def test_holdings_by_type(client, dashboard_setup):
    user, _, _ = dashboard_setup
    token = await _login(client, user.email, "Password1!")

    resp = await client.get("/dashboard/holdings/equity", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    holdings = resp.json()
    assert len(holdings) == 1
    assert holdings[0]["identifier"] == "INE009A01021"


async def test_holdings_invalid_type(client, dashboard_setup):
    user, _, _ = dashboard_setup
    token = await _login(client, user.email, "Password1!")

    resp = await client.get("/dashboard/holdings/invalid", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


async def test_transactions_returns_events(client, dashboard_setup):
    user, _, _ = dashboard_setup
    token = await _login(client, user.email, "Password1!")

    resp = await client.get("/dashboard/transactions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) >= 1
    assert any(t["event_type"] == "SecurityBought" for t in body["items"])


async def test_alerts_returns_reconciliation_flags(client, dashboard_setup):
    user, _, _ = dashboard_setup
    token = await _login(client, user.email, "Password1!")

    resp = await client.get("/dashboard/alerts", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    alerts = resp.json()
    recon = [a for a in alerts if a["source"] == "reconciliation"]
    assert len(recon) >= 1
    assert recon[0]["alert_type"] == "reconciliation_flag"
    assert recon[0]["severity"] == "warning"
    assert "SecurityBought" in recon[0]["message"]
    assert recon[0]["payload"]["expected_event_type"] == "SecurityBought"
