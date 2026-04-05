import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def owner_with_portfolio(db_session):
    slug = f"ob-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="OB Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"ob-owner-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"OBFAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="OB Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    return user, entity, portfolio


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def test_set_opening_balance_writes_event(client, owner_with_portfolio, db_session):
    user, entity, portfolio = owner_with_portfolio
    token = await _login(client, user.email, "Password1!")

    resp = await client.post(
        f"/entities/{entity.id}/portfolios/{portfolio.id}/opening-balance",
        json={
            "holdings": [
                {
                    "isin": "INE009A01021",
                    "security_name": "Infosys Limited",
                    "asset_class": "equity",
                    "quantity": 100,
                    "avg_cost": 1500.0,
                }
            ],
            "total_value": 150000.0,
            "as_of_date": "2026-04-01",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    result = await db_session.execute(
        select(PortfolioEvent).where(
            PortfolioEvent.portfolio_id == portfolio.id,
            PortfolioEvent.event_type == EventType.opening_balance_set,
        )
    )
    event = result.scalar_one()
    assert event.payload["total_value"] == 150000.0
    assert len(event.payload["holdings"]) == 1
    assert event.payload["holdings"][0]["isin"] == "INE009A01021"


async def test_cannot_set_opening_balance_twice(client, owner_with_portfolio, db_session):
    user, entity, portfolio = owner_with_portfolio
    token = await _login(client, user.email, "Password1!")

    payload = {
        "holdings": [{"isin": "INE009A01021", "security_name": "Infosys", "asset_class": "equity", "quantity": 10, "avg_cost": 1500.0}],
        "total_value": 15000.0,
        "as_of_date": "2026-04-01",
    }
    await client.post(
        f"/entities/{entity.id}/portfolios/{portfolio.id}/opening-balance",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.post(
        f"/entities/{entity.id}/portfolios/{portfolio.id}/opening-balance",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_non_owner_cannot_set_opening_balance(client, owner_with_portfolio, db_session):
    user, entity, portfolio = owner_with_portfolio
    uid = uuid.uuid4().hex[:8]
    viewer = User(
        family_id=user.family_id,
        email=f"ob-viewer-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    await db_session.commit()

    token = await _login(client, viewer.email, "Password1!")
    resp = await client.post(
        f"/entities/{entity.id}/portfolios/{portfolio.id}/opening-balance",
        json={
            "holdings": [{"isin": "INE009A01021", "security_name": "X", "asset_class": "equity", "quantity": 10, "avg_cost": 100.0}],
            "total_value": 1000.0,
            "as_of_date": "2026-04-01",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
