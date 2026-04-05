import uuid
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.models.extraction import StagedExtraction, ReviewStatus


async def _stage_extraction(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))

    try:
        normalized_rows: list[dict] = (doc.preprocessed_text or {}).get("normalized_rows", [])

        extraction = StagedExtraction(
            document_id=doc.id,
            extracted_data=normalized_rows,
            review_status=ReviewStatus.pending,
        )
        db.add(extraction)
        doc.status = DocumentStatus.awaiting_review
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def stage_extraction(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _stage_extraction(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
