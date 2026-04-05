import uuid
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm.attributes import flag_modified
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.models.event import PortfolioEvent


SYNONYM_MAP = {
    "qty": "quantity",
    "mkt val": "current_value",
    "mkt. val": "current_value",
    "nav per unit": "nav",
    "trans. amount": "amount",
    "transaction amount": "amount",
}


def _lookup_isin(isin: str) -> str | None:
    """Return canonical security name from yfinance, or None if not found."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(isin)
        info = ticker.info
        return info.get("longName") or info.get("shortName")
    except Exception:
        return None


def _normalize_date(date_str: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


async def _check_duplicate(db: AsyncSession, portfolio_id: uuid.UUID, row: dict) -> bool:
    """Return True if an identical event already exists in the event store."""
    if not portfolio_id:
        return False
    event_date = row.get("date")
    isin = row.get("isin")
    amount = row.get("amount")
    if not (event_date and amount):
        return False
    result = await db.execute(
        select(PortfolioEvent).where(
            and_(
                PortfolioEvent.portfolio_id == portfolio_id,
                PortfolioEvent.event_date == event_date,
                PortfolioEvent.payload["amount"].cast(float) == amount,
            )
        ).limit(1)
    )
    return result.scalar() is not None


async def _normalize_extraction(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.normalizing
    await db.commit()

    try:
        raw_rows: list[dict] = (doc.preprocessed_text or {}).get("raw_rows", [])
        normalized = []

        for row in raw_rows:
            row = dict(row)

            # Synonym normalization
            for old_key, new_key in SYNONYM_MAP.items():
                if old_key in row and new_key not in row:
                    row[new_key] = row.pop(old_key)

            # Date normalization
            if row.get("date"):
                row["date"] = _normalize_date(row["date"])

            # ISIN validation via yfinance
            isin = row.get("isin")
            if isin:
                canonical_name = _lookup_isin(isin)
                if canonical_name:
                    row["security_name"] = canonical_name
                else:
                    conf = dict(row.get("confidence", {}))
                    conf["isin"] = 0.0
                    row["confidence"] = conf

            # Duplicate detection
            is_dup = await _check_duplicate(db, doc.portfolio_id, row)
            row["duplicate"] = is_dup

            normalized.append(row)

        updated = dict(doc.preprocessed_text or {})
        updated["normalized_rows"] = normalized
        doc.preprocessed_text = updated
        flag_modified(doc, "preprocessed_text")
        doc.status = DocumentStatus.awaiting_review
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def normalize_extraction(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _normalize_extraction(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
