import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models.event import PortfolioEvent, EventType

class VersionConflictError(Exception):
    pass

async def append_event(
    db: AsyncSession,
    portfolio_id: uuid.UUID,
    event_type: EventType,
    payload: dict,
    event_date: date,
    created_by: uuid.UUID | None = None,
    ingestion_id: uuid.UUID | None = None,
) -> PortfolioEvent:
    max_version = await db.scalar(
        select(func.max(PortfolioEvent.version))
        .where(PortfolioEvent.portfolio_id == portfolio_id)
    )
    next_version = (max_version or 0) + 1

    event = PortfolioEvent(
        portfolio_id=portfolio_id,
        event_type=event_type,
        payload=payload,
        version=next_version,
        event_date=event_date,
        created_by=created_by,
        ingestion_id=ingestion_id,
    )
    db.add(event)
    try:
        await db.commit()
        await db.refresh(event)
        return event
    except IntegrityError:
        await db.rollback()
        raise VersionConflictError(f"Version conflict on portfolio {portfolio_id}")

async def get_events(
    db: AsyncSession,
    portfolio_id: uuid.UUID,
    from_version: int = 0,
) -> list[PortfolioEvent]:
    result = await db.execute(
        select(PortfolioEvent)
        .where(PortfolioEvent.portfolio_id == portfolio_id, PortfolioEvent.version > from_version)
        .order_by(PortfolioEvent.version)
    )
    return result.scalars().all()
