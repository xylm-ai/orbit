import base64
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.services.auth import hash_password
import app.config


@pytest_asyncio.fixture
async def postmark_family(db_session):
    slug = f"postmark-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Postmark Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"sender-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    pan = f"PMARK{uuid.uuid4().hex[:4].upper()}C"[:10]
    entity = Entity(family_id=family.id, name="PM Entity", type=EntityType.individual, pan=pan)
    db_session.add(entity)
    await db_session.commit()
    return user, family


def _make_postmark_payload(sender_email: str, filename: str = "statement.pdf"):
    pdf_bytes = b"%PDF-1.4 fake statement"
    return {
        "From": sender_email,
        "Subject": "Monthly Statement",
        "Attachments": [
            {
                "Name": filename,
                "ContentType": "application/pdf",
                "Content": base64.b64encode(pdf_bytes).decode(),
            }
        ],
    }


async def test_valid_sender_creates_document(client, postmark_family):
    user, family = postmark_family
    original_token = app.config.settings.postmark_inbound_token
    app.config.settings.postmark_inbound_token = "secret123"

    try:
        with patch("app.routers.documents.upload_file"), \
             patch("app.routers.documents._enqueue_pipeline") as mock_enqueue:
            resp = await client.post(
                "/documents/inbound-email?token=secret123",
                json=_make_postmark_payload(user.email),
            )
    finally:
        app.config.settings.postmark_inbound_token = original_token

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_enqueue.assert_called_once()


async def test_invalid_token_is_rejected(client, postmark_family):
    # postmark_inbound_token defaults to "" — any non-empty token won't match
    resp = await client.post(
        "/documents/inbound-email?token=wrongtoken",
        json=_make_postmark_payload("anyone@test.com"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_unknown_sender_is_dropped(client, postmark_family):
    original_token = app.config.settings.postmark_inbound_token
    app.config.settings.postmark_inbound_token = "secret123"

    try:
        with patch("app.routers.documents.upload_file"), \
             patch("app.routers.documents._enqueue_pipeline") as mock_enqueue:
            resp = await client.post(
                "/documents/inbound-email?token=secret123",
                json=_make_postmark_payload("unknown@stranger.com"),
            )
    finally:
        app.config.settings.postmark_inbound_token = original_token

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_sender"
    mock_enqueue.assert_not_called()
