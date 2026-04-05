import uuid
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm.attributes import flag_modified
from app.database import get_db
from app.deps import current_user
from app.models import User, UserRole, FamilyUserAccess
from app.models.document import Document, DocumentStatus
from app.models.extraction import StagedExtraction, ReviewStatus
from app.models.event import EventType
from app.services.events import append_event, VersionConflictError
from app.models.portfolio import Portfolio
from app.services.projections import rebuild_portfolio, rebuild_entity_allocation
from app.schemas.extraction import (
    ExtractionReviewResponse, RowEditRequest, ConfirmResponse, RejectRequest
)

router = APIRouter(prefix="/extractions", tags=["extractions"])

CAN_CONFIRM = {UserRole.owner, UserRole.advisor, UserRole.ca}

EVENT_TYPE_MAP = {
    "SecurityBought": EventType.security_bought,
    "SecuritySold": EventType.security_sold,
    "DividendReceived": EventType.dividend_received,
    "MFUnitsPurchased": EventType.mf_units_purchased,
    "MFUnitsRedeemed": EventType.mf_units_redeemed,
    "BankEntryRecorded": EventType.bank_entry_recorded,
}

PAYLOAD_FIELDS = {
    EventType.security_bought: ["isin", "security_name", "quantity", "price", "amount", "broker"],
    EventType.security_sold: ["isin", "security_name", "quantity", "price", "amount", "broker"],
    EventType.dividend_received: ["isin", "security_name", "amount"],
    EventType.mf_units_purchased: ["scheme_code", "scheme_name", "units", "nav", "amount"],
    EventType.mf_units_redeemed: ["scheme_code", "scheme_name", "units", "nav", "amount"],
    EventType.bank_entry_recorded: ["amount", "type", "narration"],
}


async def _get_extraction_with_access(
    extraction_id: uuid.UUID, user: User, db: AsyncSession
) -> StagedExtraction:
    extraction = await db.get(StagedExtraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    doc = await db.get(Document, extraction.document_id)

    if user.role == UserRole.owner:
        from app.models import Entity
        entity = await db.get(Entity, doc.entity_id)
        if entity.family_id != user.family_id:
            raise HTTPException(status_code=403, detail="No access")
    else:
        access = await db.scalar(
            select(FamilyUserAccess).where(
                FamilyUserAccess.user_id == user.id,
                FamilyUserAccess.entity_id == doc.entity_id,
            )
        )
        if not access:
            raise HTTPException(status_code=403, detail="No access")
    return extraction


@router.get("/{extraction_id}/review", response_model=ExtractionReviewResponse)
async def get_review(
    extraction_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_extraction_with_access(extraction_id, user, db)


@router.put("/{extraction_id}/rows/{row_index}")
async def edit_row(
    extraction_id: uuid.UUID,
    row_index: int,
    body: RowEditRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")
    rows = list(extraction.extracted_data)
    if row_index < 0 or row_index >= len(rows):
        raise HTTPException(status_code=400, detail="Invalid row index")

    updated_row = dict(rows[row_index])
    for field, value in body.model_dump(exclude_none=True).items():
        updated_row[field] = value
    rows[row_index] = updated_row
    extraction.extracted_data = rows
    flag_modified(extraction, "extracted_data")
    await db.commit()
    return updated_row


@router.post("/{extraction_id}/confirm", response_model=ConfirmResponse)
async def confirm_extraction(
    extraction_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in CAN_CONFIRM:
        raise HTTPException(status_code=403, detail="Insufficient permissions to confirm")

    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")

    doc = await db.get(Document, extraction.document_id)
    if not doc.portfolio_id:
        raise HTTPException(status_code=400, detail="Document has no portfolio assigned — set portfolio_id first")

    events_written = 0
    skipped = 0

    for row in extraction.extracted_data:
        if row.get("duplicate"):
            skipped += 1
            continue

        event_type_str = row.get("event_type", "")
        event_type = EVENT_TYPE_MAP.get(event_type_str)
        if not event_type:
            skipped += 1
            continue

        allowed_fields = PAYLOAD_FIELDS.get(event_type, [])
        payload = {k: row[k] for k in allowed_fields if k in row}

        try:
            await append_event(
                db=db,
                portfolio_id=doc.portfolio_id,
                event_type=event_type,
                payload=payload,
                event_date=date.fromisoformat(row["date"]),
                created_by=user.id,
                ingestion_id=extraction.id,
            )
            events_written += 1
        except VersionConflictError:
            skipped += 1

    extraction.review_status = ReviewStatus.approved
    extraction.reviewed_by = user.id
    extraction.reviewed_at = datetime.now(timezone.utc)
    doc.status = DocumentStatus.ingested
    await db.commit()

    # Rebuild projections if events were written
    if events_written > 0 and doc.portfolio_id:
        portfolio = await db.get(Portfolio, doc.portfolio_id)
        if portfolio:
            await rebuild_portfolio(doc.portfolio_id, db)
            await rebuild_entity_allocation(portfolio.entity_id, db)
            await db.commit()

    return ConfirmResponse(events_written=events_written, skipped_duplicates=skipped)


@router.post("/{extraction_id}/reject", status_code=200)
async def reject_extraction(
    extraction_id: uuid.UUID,
    body: RejectRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in CAN_CONFIRM:
        raise HTTPException(status_code=403, detail="Insufficient permissions to reject")

    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")

    doc = await db.get(Document, extraction.document_id)
    extraction.review_status = ReviewStatus.rejected
    extraction.reviewed_by = user.id
    extraction.reviewed_at = datetime.now(timezone.utc)
    doc.status = DocumentStatus.failed
    doc.failure_reason = body.reason[:500] if body.reason else "Rejected by user"
    await db.commit()
    return {"status": "rejected"}
