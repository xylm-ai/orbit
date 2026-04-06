import uuid
import pytest
import pytest_asyncio
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.models.alert import Alert, AlertType, Severity
from app.services.alerts import check_and_write_alerts, check_price_drop_alerts
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def alert_setup(db_session):
    slug = f"al-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Alert Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"al-owner-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"ALFAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="AL Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Test")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    return user, entity, portfolio


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def test_concentration_alert_written(alert_setup, db_session):
    _, entity, portfolio = alert_setup

    holding = Holding(
        portfolio_id=portfolio.id,
        identifier="INE001A01036",
        security_name="Reliance",
        asset_class="equity",
        quantity=Decimal("10"),
        avg_cost_per_unit=Decimal("2000"),
        total_cost=Decimal("20000"),
        realized_pnl=Decimal("0"),
        dividend_income=Decimal("0"),
        current_price=Decimal("2500"),
        current_value=Decimal("25000"),
        unrealized_pnl=Decimal("5000"),
    )
    pm = PerformanceMetrics(
        portfolio_id=portfolio.id,
        total_invested=Decimal("20000"),
        current_value=Decimal("25000"),
        unrealized_pnl=Decimal("5000"),
        realized_pnl=Decimal("0"),
    )
    db_session.add(holding)
    db_session.add(pm)
    await db_session.commit()

    await check_and_write_alerts(portfolio.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Alert).where(Alert.portfolio_id == portfolio.id, Alert.alert_type == AlertType.concentration)
    )
    alert = result.scalar_one()
    assert alert.severity == Severity.warning
    assert "Reliance" in alert.message
    assert alert.identifier == "INE001A01036"


async def test_concentration_alert_not_duplicated(alert_setup, db_session):
    _, entity, portfolio = alert_setup

    holding = Holding(
        portfolio_id=portfolio.id,
        identifier="INE002A01018",
        security_name="TCS",
        asset_class="equity",
        quantity=Decimal("5"),
        avg_cost_per_unit=Decimal("3000"),
        total_cost=Decimal("15000"),
        realized_pnl=Decimal("0"),
        dividend_income=Decimal("0"),
        current_price=Decimal("3500"),
        current_value=Decimal("17500"),
        unrealized_pnl=Decimal("2500"),
    )
    pm = PerformanceMetrics(
        portfolio_id=portfolio.id,
        total_invested=Decimal("15000"),
        current_value=Decimal("17500"),
        unrealized_pnl=Decimal("2500"),
        realized_pnl=Decimal("0"),
    )
    db_session.add(holding)
    db_session.add(pm)
    await db_session.commit()

    await check_and_write_alerts(portfolio.id, db_session)
    await db_session.commit()
    await check_and_write_alerts(portfolio.id, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Alert).where(
            Alert.portfolio_id == portfolio.id,
            Alert.alert_type == AlertType.concentration,
            Alert.identifier == "INE002A01018",
        )
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1


async def test_price_drop_alert_written(alert_setup, db_session):
    _, entity, portfolio = alert_setup

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
        current_price=Decimal("1400"),
        current_value=Decimal("14000"),
        unrealized_pnl=Decimal("-1000"),
    )
    db_session.add(holding)
    await db_session.commit()

    day_change_map = {"INE009A01021": -6.5}
    await check_price_drop_alerts(portfolio.id, day_change_map, db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Alert).where(Alert.portfolio_id == portfolio.id, Alert.alert_type == AlertType.price_drop)
    )
    alert = result.scalar_one()
    assert alert.severity == Severity.warning
    assert "Infosys" in alert.message
    assert "6.5" in alert.message


async def test_dismiss_alert_endpoint(client, alert_setup, db_session):
    user, entity, portfolio = alert_setup
    token = await _login(client, user.email, "Password1!")

    alert = Alert(
        entity_id=entity.id,
        portfolio_id=portfolio.id,
        identifier=None,
        alert_type=AlertType.drawdown,
        severity=Severity.critical,
        message="Portfolio is down 20%",
        payload={"drawdown_pct": -20.0},
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    resp = await client.post(
        f"/dashboard/alerts/{alert.id}/dismiss",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    await db_session.refresh(alert)
    assert alert.dismissed_at is not None


async def test_dismissed_alert_excluded_from_list(client, alert_setup, db_session):
    user, entity, portfolio = alert_setup
    token = await _login(client, user.email, "Password1!")

    alert = Alert(
        entity_id=entity.id,
        portfolio_id=portfolio.id,
        identifier=None,
        alert_type=AlertType.drawdown,
        severity=Severity.critical,
        message="Portfolio is down 20%",
        payload={},
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    await client.post(
        f"/dashboard/alerts/{alert.id}/dismiss",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get("/dashboard/alerts", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    threshold_alerts = [a for a in resp.json() if a["source"] == "threshold"]
    assert not any(a["id"] == str(alert.id) for a in threshold_alerts)
