import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.event import PortfolioEvent, EventType
from app.services.events import append_event

AMOUNT_TOLERANCE = Decimal("0.005")   # 0.5%
DATE_TOLERANCE_DAYS = 2


async def run_reconciliation(portfolio_id: uuid.UUID, db: AsyncSession) -> int:
    """Match BankEntryRecorded events against transaction events.
    Writes a ReconciliationFlagged event for each unmatched bank entry.
    Returns the number of flags written.
    Caller must db.commit() afterwards.
    """
    result = await db.execute(
        select(PortfolioEvent)
        .where(PortfolioEvent.portfolio_id == portfolio_id)
        .order_by(PortfolioEvent.event_date, PortfolioEvent.version)
    )
    events = result.scalars().all()

    bank_entries = [e for e in events if e.event_type == EventType.bank_entry_recorded]
    tx_events = [
        e for e in events
        if e.event_type in {
            EventType.security_bought,
            EventType.security_sold,
            EventType.dividend_received,
            EventType.mf_units_purchased,
            EventType.mf_units_redeemed,
        }
    ]
    already_flagged_bank_ids = {
        e.payload.get("bank_entry_id")
        for e in events
        if e.event_type == EventType.reconciliation_flagged
    }

    matched_tx_ids: set[uuid.UUID] = set()
    flags_written = 0

    for bank_event in bank_entries:
        if str(bank_event.id) in already_flagged_bank_ids:
            continue

        bp = bank_event.payload
        bank_amount = Decimal(str(bp.get("amount", 0)))
        bank_date = bank_event.event_date
        bank_type = bp.get("type", "").lower()

        expected_types = (
            {EventType.security_bought, EventType.mf_units_purchased}
            if bank_type == "debit"
            else {EventType.security_sold, EventType.dividend_received, EventType.mf_units_redeemed}
        )
        expected_type_name = "SecurityBought" if bank_type == "debit" else "SecuritySold"

        matched = False
        for tx in tx_events:
            if tx.id in matched_tx_ids or tx.event_type not in expected_types:
                continue
            if abs((tx.event_date - bank_date).days) > DATE_TOLERANCE_DAYS:
                continue
            tx_amount = Decimal(str(tx.payload.get("amount", 0)))
            if tx_amount == 0 or bank_amount == 0:
                continue
            if abs(tx_amount - bank_amount) / bank_amount <= AMOUNT_TOLERANCE:
                matched = True
                matched_tx_ids.add(tx.id)
                break

        if not matched:
            try:
                await append_event(
                    db=db,
                    portfolio_id=portfolio_id,
                    event_type=EventType.reconciliation_flagged,
                    payload={
                        "bank_entry_id": str(bank_event.id),
                        "expected_event_type": expected_type_name,
                        "amount": str(bank_amount),
                        "date": str(bank_date),
                    },
                    event_date=bank_date,
                    created_by=None,
                    ingestion_id=None,
                )
                flags_written += 1
            except Exception:
                pass

    return flags_written
