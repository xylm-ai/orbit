import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, UserRole
from app.schemas.entity import EntityCreate, EntityResponse
from app.schemas.access import InviteRequest, AccessResponse

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
    from app.models import FamilyUserAccess
    from sqlalchemy import union

    # Own-family entities (owners only)
    own_family_ids = (
        select(Entity.id).where(Entity.family_id == user.family_id)
        if user.role == UserRole.owner
        else select(Entity.id).where(False)
    )
    # Entities granted via FamilyUserAccess
    granted_ids = select(FamilyUserAccess.entity_id).where(FamilyUserAccess.user_id == user.id)

    result = await db.execute(
        select(Entity).where(Entity.id.in_(union(own_family_ids, granted_ids)))
    )
    return result.scalars().all()

@router.post("/{entity_id}/invite", response_model=AccessResponse, status_code=201)
async def invite_user(
    entity_id: uuid.UUID,
    body: InviteRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import FamilyUserAccess

    entity = await db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if user.role != UserRole.owner or entity.family_id != user.family_id:
        raise HTTPException(status_code=403, detail="Only owners can invite users")

    invitee = await db.scalar(select(User).where(User.email == body.email))
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found — they must register first")

    existing = await db.scalar(
        select(FamilyUserAccess)
        .where(FamilyUserAccess.user_id == invitee.id, FamilyUserAccess.entity_id == entity_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already has access to this entity")

    access = FamilyUserAccess(
        user_id=invitee.id,
        entity_id=entity_id,
        role=body.role,
        granted_by=user.id,
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)
    return access
