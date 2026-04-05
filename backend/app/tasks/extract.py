import uuid
import asyncio
import json
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus, DocType
from app.config import settings

PROMPTS: dict[str, str] = {
    DocType.contract_note: """Extract all transactions from this broker contract note.
Return ONLY a JSON array (no other text). Each element must have exactly these fields:
{"event_type": "SecurityBought" or "SecuritySold", "date": "YYYY-MM-DD", "isin": "string or null",
 "security_name": "string", "quantity": number, "price": number, "amount": number, "broker": "string",
 "confidence": {"date": 0-1, "isin": 0-1, "security_name": 0-1, "quantity": 0-1, "price": 0-1, "amount": 0-1}}""",

    DocType.pms_transaction: """Extract all transactions from this PMS transaction statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "SecurityBought" | "SecuritySold" | "DividendReceived", "date": "YYYY-MM-DD",
 "isin": "string or null", "security_name": "string or null", "quantity": number or null,
 "price": number or null, "amount": number, "broker": "string",
 "confidence": {"date": 0-1, "isin": 0-1, "security_name": 0-1, "quantity": 0-1, "price": 0-1, "amount": 0-1}}""",

    DocType.cas: """Extract all mutual fund transactions from this CAS statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "MFUnitsPurchased" or "MFUnitsRedeemed", "date": "YYYY-MM-DD",
 "scheme_code": "string or null", "scheme_name": "string", "units": number, "nav": number, "amount": number,
 "confidence": {"date": 0-1, "scheme_code": 0-1, "scheme_name": 0-1, "units": 0-1, "nav": 0-1, "amount": 0-1}}""",

    DocType.bank_statement: """Extract all transactions from this bank statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "BankEntryRecorded", "date": "YYYY-MM-DD",
 "amount": number (positive=credit, negative=debit), "type": "credit" or "debit", "narration": "string",
 "confidence": {"date": 0-1, "amount": 0-1, "type": 0-1, "narration": 0-1}}""",
}


def _call_llm_extract(doc_type: DocType, text: str) -> list[dict]:
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = PROMPTS.get(doc_type, PROMPTS[DocType.contract_note])
    full_text = text[:15000]
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_text},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)


async def _extract_with_llm(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.extracting
    await db.commit()

    try:
        pages = (doc.preprocessed_text or {}).get("pages", [])
        full_text = "\n\n".join(pages)
        raw_rows = _call_llm_extract(doc.doc_type, full_text)

        updated = dict(doc.preprocessed_text or {})
        updated["raw_rows"] = raw_rows
        doc.preprocessed_text = updated
        flag_modified(doc, "preprocessed_text")
        doc.status = DocumentStatus.normalizing
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def extract_with_llm(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _extract_with_llm(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
