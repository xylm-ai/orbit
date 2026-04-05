import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, Portfolio, FamilyUserAccess, UserRole
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse
from app.schemas.opening_balance import OpeningBalanceRequest, OpeningBalanceResponse
from app.models.event import PortfolioEvent, EventType
from app.services.events import append_event

router = APIRouter(prefix="/entities/{entity_id}/portfolios", tags=["portfolios"])

async def _get_entity_or_403(entity_id: uuid.UUID, user: User, db: AsyncSession) -> Entity:
    entity = await db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    # Same-family owner: admit immediately
    if entity.family_id == user.family_id and user.role == UserRole.owner:
        return entity
    # Check entity-scoped access grant (covers same-family non-owners AND cross-family invites)
    access = await db.scalar(
        select(FamilyUserAccess)
        .where(FamilyUserAccess.user_id == user.id, FamilyUserAccess.entity_id == entity_id)
    )
    if not access:
        raise HTTPException(status_code=403, detail="Access denied")
    return entity

@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    entity_id: uuid.UUID,
    body: PortfolioCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can create portfolios")
    await _get_entity_or_403(entity_id, user, db)
    portfolio = Portfolio(entity_id=entity_id, **body.model_dump())
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio

@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    entity_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_entity_or_403(entity_id, user, db)
    result = await db.execute(select(Portfolio).where(Portfolio.entity_id == entity_id))
    return result.scalars().all()


@router.post("/{portfolio_id}/opening-balance", response_model=OpeningBalanceResponse, status_code=201)
async def set_opening_balance(
    entity_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    body: OpeningBalanceRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can set opening balance")

    await _get_entity_or_403(entity_id, user, db)

    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio or portfolio.entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    existing = await db.scalar(
        select(func.count(PortfolioEvent.id)).where(
            PortfolioEvent.portfolio_id == portfolio_id,
            PortfolioEvent.event_type == EventType.opening_balance_set,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Opening balance already set for this portfolio")

    holdings_payload = [
        {k: float(v) if hasattr(v, "__float__") and not isinstance(v, str) else v
         for k, v in h.model_dump(exclude_none=True).items()}
        for h in body.holdings
    ]
    event = await append_event(
        db=db,
        portfolio_id=portfolio_id,
        event_type=EventType.opening_balance_set,
        payload={
            "holdings": holdings_payload,
            "total_value": float(body.total_value),
            "as_of_date": body.as_of_date.isoformat(),
        },
        event_date=body.as_of_date,
        created_by=user.id,
    )

    return OpeningBalanceResponse(
        event_id=str(event.id),
        portfolio_id=str(portfolio_id),
        version=event.version,
    )
