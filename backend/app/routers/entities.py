from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, UserRole
from app.schemas.entity import EntityCreate, EntityResponse

router = APIRouter(prefix="/entities", tags=["entities"])

@router.post("", response_model=EntityResponse, status_code=201)
async def create_entity(
    body: EntityCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can create entities")
    entity = Entity(family_id=user.family_id, **body.model_dump())
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity

@router.get("", response_model=list[EntityResponse])
async def list_entities(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == UserRole.owner:
        result = await db.execute(select(Entity).where(Entity.family_id == user.family_id))
        return result.scalars().all()
    else:
        from app.models import FamilyUserAccess
        result = await db.execute(
            select(Entity)
            .join(FamilyUserAccess, FamilyUserAccess.entity_id == Entity.id)
            .where(FamilyUserAccess.user_id == user.id)
        )
        return result.scalars().all()
