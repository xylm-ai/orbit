import uuid
import asyncio
import io
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.services.storage import get_file_bytes


def _extract_with_pdfplumber(file_bytes: bytes) -> dict:
    import pdfplumber
    pages = []
    tables = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
            for table in (page.extract_tables() or []):
                if table:
                    tables.append(table)
    return {"pages": pages, "tables": tables}


def _extract_with_ocr(file_bytes: bytes) -> dict:
    import pytesseract
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(file_bytes)
    pages = [pytesseract.image_to_string(img) for img in images]
    return {"pages": pages, "tables": []}


def _is_mostly_empty(extracted: dict) -> bool:
    total_chars = sum(len(p) for p in extracted["pages"])
    return total_chars < 100 * max(len(extracted["pages"]), 1)


async def _preprocess_document(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.preprocessing
    await db.commit()

    try:
        file_bytes = get_file_bytes(doc.storage_path)
        extracted = _extract_with_pdfplumber(file_bytes)
        if _is_mostly_empty(extracted):
            extracted = _extract_with_ocr(file_bytes)
        doc.preprocessed_text = extracted
        flag_modified(doc, "preprocessed_text")
        doc.status = DocumentStatus.extracting
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def preprocess_document(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _preprocess_document(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
