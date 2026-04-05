import uuid
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.deps import current_user
from app.models import User, UserRole, FamilyUserAccess, Entity, Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.models.holding import Holding
from app.models.performance import PerformanceMetrics
from app.schemas.dashboard import (
    SummaryResponse, EntitySummaryItem, PortfolioSummaryItem,
    HoldingItem, PaginatedTransactions, TransactionItem, AlertItem,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

EXCLUDED_FROM_TRANSACTIONS = {EventType.reconciliation_flagged}


async def _accessible_entity_ids(user: User, db: AsyncSession) -> list[uuid.UUID]:
    if user.role == UserRole.owner:
        result = await db.execute(
            select(Entity.id).where(Entity.family_id == user.family_id)
        )
    else:
        result = await db.execute(
            select(FamilyUserAccess.entity_id).where(FamilyUserAccess.user_id == user.id)
        )
    return result.scalars().all()


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entity_ids = await _accessible_entity_ids(user, db)
    if not entity_ids:
        return SummaryResponse(
            total_net_worth=Decimal("0"), total_invested=Decimal("0"),
            total_unrealized_pnl=Decimal("0"), entities=[],
        )

    result = await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))
    entities = result.scalars().all()

    result = await db.execute(select(Portfolio).where(Portfolio.entity_id.in_(entity_ids)))
    portfolios = result.scalars().all()
    portfolio_ids = [p.id for p in portfolios]

    pm_result = await db.execute(
        select(PerformanceMetrics).where(PerformanceMetrics.portfolio_id.in_(portfolio_ids))
    )
    pm_map = {pm.portfolio_id: pm for pm in pm_result.scalars().all()}

    total_net_worth = Decimal("0")
    total_invested = Decimal("0")
    total_unrealized_pnl = Decimal("0")
    entity_map: dict[uuid.UUID, list[PortfolioSummaryItem]] = {e.id: [] for e in entities}

    for p in portfolios:
        pm = pm_map.get(p.id)
        current_value = pm.current_value if pm else Decimal("0")
        t_invested = pm.total_invested if pm else Decimal("0")
        unreal_pnl = pm.unrealized_pnl if pm else Decimal("0")

        total_net_worth += current_value
        total_invested += t_invested
        total_unrealized_pnl += unreal_pnl

        entity_map[p.entity_id].append(PortfolioSummaryItem(
            portfolio_id=p.id,
            portfolio_type=p.type.value,
            provider_name=p.provider_name,
            current_value=current_value,
            total_invested=t_invested,
            xirr=pm.xirr if pm else None,
            unrealized_pnl=unreal_pnl,
            abs_return_pct=pm.abs_return_pct if pm else None,
        ))

    entity_summaries = [
        EntitySummaryItem(
            entity_id=e.id,
            entity_name=e.name,
            entity_type=e.type.value,
            total_value=sum(p.current_value for p in entity_map[e.id]),
            portfolios=entity_map[e.id],
        )
        for e in entities
    ]

    return SummaryResponse(
        total_net_worth=total_net_worth,
        total_invested=total_invested,
        total_unrealized_pnl=total_unrealized_pnl,
        entities=entity_summaries,
    )


@router.get("/holdings/{asset_type}", response_model=list[HoldingItem])
async def get_holdings(
    asset_type: Literal["pms", "equity", "mf"],
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entity_ids = await _accessible_entity_ids(user, db)
    if not entity_ids:
        return []

    portfolio_type = PortfolioType(asset_type)
    result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.entity_id.in_(entity_ids),
            Portfolio.type == portfolio_type,
        )
    )
    portfolio_ids = result.scalars().all()
    if not portfolio_ids:
        return []

    result = await db.execute(
        select(Holding).where(Holding.portfolio_id.in_(portfolio_ids))
    )
    return result.scalars().all()


@router.get("/transactions", response_model=PaginatedTransactions)
async def get_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entity_ids = await _accessible_entity_ids(user, db)
    if not entity_ids:
        return PaginatedTransactions(items=[], total=0, page=page, page_size=page_size)

    result = await db.execute(
        select(Portfolio.id).where(Portfolio.entity_id.in_(entity_ids))
    )
    portfolio_ids = result.scalars().all()

    base_filter = [
        PortfolioEvent.portfolio_id.in_(portfolio_ids),
        PortfolioEvent.event_type.notin_(list(EXCLUDED_FROM_TRANSACTIONS)),
    ]

    total_result = await db.execute(
        select(func.count(PortfolioEvent.id)).where(*base_filter)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(PortfolioEvent)
        .where(*base_filter)
        .order_by(PortfolioEvent.event_date.desc(), PortfolioEvent.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = result.scalars().all()

    items = [
        TransactionItem(
            event_id=e.id,
            portfolio_id=e.portfolio_id,
            event_type=e.event_type.value,
            payload=e.payload,
            event_date=e.event_date,
            version=e.version,
            created_at=e.created_at,
        )
        for e in events
    ]
    return PaginatedTransactions(items=items, total=total, page=page, page_size=page_size)


@router.get("/alerts", response_model=list[AlertItem])
async def get_alerts(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entity_ids = await _accessible_entity_ids(user, db)
    if not entity_ids:
        return []

    result = await db.execute(
        select(Portfolio.id).where(Portfolio.entity_id.in_(entity_ids))
    )
    portfolio_ids = result.scalars().all()

    result = await db.execute(
        select(PortfolioEvent)
        .where(
            PortfolioEvent.portfolio_id.in_(portfolio_ids),
            PortfolioEvent.event_type == EventType.reconciliation_flagged,
        )
        .order_by(PortfolioEvent.event_date.desc())
    )
    events = result.scalars().all()

    return [
        AlertItem(
            event_id=e.id,
            portfolio_id=e.portfolio_id,
            event_date=e.event_date,
            payload=e.payload,
            created_at=e.created_at,
        )
        for e in events
    ]
