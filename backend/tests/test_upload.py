import io
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def owner(db_session):
    slug = f"upload-test-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Upload Test Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    uid = uuid.uuid4().hex[:8]
    user = User(
        family_id=family.id,
        email=f"uploader-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def entity(db_session, owner):
    e = Entity(
        family_id=owner.family_id,
        name="Upload Entity",
        type=EntityType.individual,
        pan="UPLDA1234A",
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    return e


@pytest_asyncio.fixture
async def auth_token(client, owner):
    resp = await client.post("/auth/login", json={"email": owner.email, "password": "Password1!"})
    return resp.json()["access_token"]


async def test_upload_creates_document_and_enqueues_task(client, entity, auth_token):
    with patch("app.routers.documents.upload_file", return_value="documents/fam/id/test.pdf"), \
         patch("app.routers.documents._enqueue_pipeline") as mock_enqueue:
        resp = await client.post(
            "/documents",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            data={"entity_id": str(entity.id)},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source"] == "upload"
    mock_enqueue.assert_called_once_with(body["id"])


async def test_upload_rejects_viewer(client, db_session):
    slug = f"viewer-fam-{uuid.uuid4().hex[:8]}"
    family = Family(name="Viewer Family", inbound_email_slug=slug)
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)
    uid = uuid.uuid4().hex[:8]
    viewer = User(
        family_id=family.id,
        email=f"viewer-{uid}@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    await db_session.commit()

    login = await client.post("/auth/login", json={"email": viewer.email, "password": "Password1!"})
    token = login.json()["access_token"]

    resp = await client.post(
        "/documents",
        files={"file": ("test.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        data={"entity_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_upload_rejects_unsupported_file_type(client, entity, auth_token):
    resp = await client.post(
        "/documents",
        files={"file": ("test.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
        data={"entity_id": str(entity.id)},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 400


async def test_list_documents_returns_accessible(client, entity, auth_token):
    with patch("app.routers.documents.upload_file"), \
         patch("app.routers.documents._enqueue_pipeline"):
        await client.post(
            "/documents",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            data={"entity_id": str(entity.id)},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    resp = await client.get("/documents", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1
    assert all(d["source"] == "upload" for d in docs)
