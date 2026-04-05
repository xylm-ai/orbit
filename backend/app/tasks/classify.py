import uuid
import asyncio
import json
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus, DocType
from app.services.storage import get_file_bytes
from app.config import settings

CLASSIFY_PROMPT = """You are a financial document classifier.
Read the following text from a financial document and classify it.
Respond with ONLY a JSON object — no other text:
{
  "doc_type": "contract_note" | "pms_transaction" | "cas" | "bank_statement",
  "confidence": 0.0 to 1.0,
  "detected_pan": "<PAN if found, else null>",
  "detected_provider": "<broker/PMS/bank name if found, else null>",
  "detected_account_number": "<account number if found, else null>"
}

Document text (first 2000 characters):
"""


def _call_llm_classify(text: str) -> dict:
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": CLASSIFY_PROMPT + text[:2000]}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


async def _classify_document(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.classifying
    await db.commit()

    try:
        file_bytes = get_file_bytes(doc.storage_path)
        text = file_bytes.decode("utf-8", errors="ignore")
        result = _call_llm_classify(text)

        valid_types = {t.value for t in DocType}
        if result.get("doc_type") in valid_types:
            doc.doc_type = DocType(result["doc_type"])
        doc.status = DocumentStatus.preprocessing
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def classify_document(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _classify_document(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
