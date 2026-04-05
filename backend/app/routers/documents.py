import uuid
import base64
import hmac
from celery import chain as celery_chain
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, UserRole, FamilyUserAccess
from app.models.document import Document, DocumentSource, DocumentStatus
from app.schemas.document import DocumentResponse, DocumentListItem
from app.services.storage import upload_file
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _enqueue_pipeline(document_id: str) -> None:
    from app.tasks.classify import classify_document
    from app.tasks.preprocess import preprocess_document
    from app.tasks.extract import extract_with_llm
    from app.tasks.normalize import normalize_extraction
    from app.tasks.stage import stage_extraction
    celery_chain(
        classify_document.s(document_id),
        preprocess_document.s(),
        extract_with_llm.s(),
        normalize_extraction.s(),
        stage_extraction.s(),
    ).delay()


async def _get_accessible_entity_ids(user: User, db: AsyncSession) -> list[uuid.UUID]:
    if user.role == UserRole.owner:
        own = await db.execute(select(Entity.id).where(Entity.family_id == user.family_id))
        own_ids = [r[0] for r in own.all()]
    else:
        own_ids = []
    granted = await db.execute(select(FamilyUserAccess.entity_id).where(FamilyUserAccess.user_id == user.id))
    granted_ids = [r[0] for r in granted.all()]
    return list(set(own_ids + granted_ids))


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    entity_id: uuid.UUID = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Viewers cannot upload documents")

    accessible = await _get_accessible_entity_ids(user, db)
    if entity_id not in accessible:
        raise HTTPException(status_code=403, detail="No access to this entity")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    s3_key = f"documents/{user.family_id}/{uuid.uuid4()}/{file.filename}"
    upload_file(file_bytes, s3_key, content_type)

    doc = Document(
        entity_id=entity_id,
        source=DocumentSource.upload,
        storage_path=s3_key,
        status=DocumentStatus.pending,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    _enqueue_pipeline(str(doc.id))
    return doc


@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    accessible = await _get_accessible_entity_ids(user, db)
    if not accessible:
        return []
    result = await db.execute(
        select(Document)
        .where(Document.entity_id.in_(accessible))
        .order_by(Document.uploaded_at.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/{document_id}/extraction")
async def get_document_extraction(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select as sa_select
    from app.models.extraction import StagedExtraction
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    accessible = await _get_accessible_entity_ids(user, db)
    if doc.entity_id not in accessible:
        raise HTTPException(status_code=403, detail="No access to this document")
    extraction = await db.scalar(
        sa_select(StagedExtraction).where(StagedExtraction.document_id == document_id)
    )
    if not extraction:
        raise HTTPException(status_code=404, detail="No extraction for this document")
    return {"extraction_id": str(extraction.id)}


@router.get("/{document_id}/status", response_model=DocumentResponse)
async def get_document_status(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    accessible = await _get_accessible_entity_ids(user, db)
    if doc.entity_id not in accessible:
        raise HTTPException(status_code=403, detail="No access to this document")
    return doc


@router.post("/inbound-email", status_code=200)
async def postmark_inbound(request: Request, token: str = "", db: AsyncSession = Depends(get_db)):
    # Validate token
    if not token or not hmac.compare_digest(token, settings.postmark_inbound_token):
        return {"status": "rejected"}

    body = await request.json()
    sender_email = body.get("From", "").split("<")[-1].rstrip(">").strip().lower()

    from sqlalchemy import select as sa_select
    from app.models import User as UserModel
    sender = await db.scalar(sa_select(UserModel).where(UserModel.email == sender_email))
    if not sender:
        return {"status": "rejected_sender"}

    attachments = body.get("Attachments", [])
    for attachment in attachments:
        content_type = attachment.get("ContentType", "")
        if content_type not in ALLOWED_CONTENT_TYPES:
            continue

        file_bytes = base64.b64decode(attachment["Content"])
        filename = attachment.get("Name", "attachment")
        s3_key = f"documents/{sender.family_id}/{uuid.uuid4()}/{filename}"
        upload_file(file_bytes, s3_key, content_type)

        from app.models import Entity as EntityModel
        entity = await db.scalar(
            sa_select(EntityModel).where(EntityModel.family_id == sender.family_id).limit(1)
        )
        if not entity:
            continue

        doc = Document(
            entity_id=entity.id,
            source=DocumentSource.email,
            storage_path=s3_key,
            status=DocumentStatus.pending,
            uploaded_by=sender.id,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        _enqueue_pipeline(str(doc.id))

    return {"status": "ok"}
