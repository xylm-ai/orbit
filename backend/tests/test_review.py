import uuid
import pytest
import pytest_asyncio
from datetime import date
from sqlalchemy import select
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.document import Document, DocumentSource, DocumentStatus, DocType
from app.models.extraction import StagedExtraction, ReviewStatus
from app.models.event import PortfolioEvent
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def owner_with_portfolio(db_session):
    slug = f"review-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Review Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"reviewer-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"REVAA{uuid.uuid4().hex[:4].upper()}B"[:10]
    entity = Entity(family_id=family.id, name="Rev Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    return user, entity, portfolio


@pytest_asyncio.fixture
async def extraction_with_document(db_session, owner_with_portfolio):
    user, entity, portfolio = owner_with_portfolio
    doc = Document(
        entity_id=entity.id,
        portfolio_id=portfolio.id,
        source=DocumentSource.upload,
        storage_path="documents/test/doc.pdf",
        doc_type=DocType.contract_note,
        status=DocumentStatus.awaiting_review,
        uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    extraction = StagedExtraction(
        document_id=doc.id,
        extracted_data=[
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE009A01021",
                "security_name": "Infosys Limited",
                "quantity": 10,
                "price": 1800.0,
                "amount": 18000.0,
                "broker": "Zerodha",
                "duplicate": False,
                "confidence": {"date": 0.95, "isin": 0.88, "security_name": 0.92, "quantity": 0.99, "price": 0.95, "amount": 0.98},
            },
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE040A01034",
                "security_name": "HDFC Bank",
                "quantity": 5,
                "price": 1500.0,
                "amount": 7500.0,
                "broker": "Zerodha",
                "duplicate": True,
                "confidence": {"date": 0.99, "isin": 0.99, "security_name": 0.99, "quantity": 0.99, "price": 0.99, "amount": 0.99},
            },
        ],
        review_status=ReviewStatus.pending,
    )
    db_session.add(extraction)
    await db_session.commit()
    await db_session.refresh(extraction)

    return user, extraction


async def _login(client, email, password):
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def test_get_review_returns_extraction(client, extraction_with_document):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.get(
        f"/extractions/{extraction.id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["extracted_data"]) == 2
    assert body["review_status"] == "pending"


async def test_edit_row_updates_field(client, extraction_with_document):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.put(
        f"/extractions/{extraction.id}/rows/0",
        json={"quantity": 12.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 12.0


async def test_confirm_writes_events_skips_duplicates(client, extraction_with_document, db_session):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.post(
        f"/extractions/{extraction.id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["events_written"] == 1
    assert body["skipped_duplicates"] == 1

    result = await db_session.execute(select(PortfolioEvent).where(PortfolioEvent.ingestion_id == extraction.id))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["isin"] == "INE009A01021"


async def test_viewer_cannot_confirm(client, extraction_with_document, db_session):
    user, extraction = extraction_with_document

    uid = uuid.uuid4().hex[:8]
    viewer = User(
        family_id=user.family_id,
        email=f"viewonly-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    await db_session.commit()

    token = await _login(client, viewer.email, "Password1!")
    resp = await client.post(
        f"/extractions/{extraction.id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_reject_marks_document_failed(client, extraction_with_document, db_session):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.post(
        f"/extractions/{extraction.id}/reject",
        json={"reason": "Wrong document"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    await db_session.refresh(extraction)
    assert extraction.review_status == ReviewStatus.rejected
