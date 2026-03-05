import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.user import Role, RoleName, User, UserType
from app.schemas.user import ServiceAccountCreate, ServiceAccountResponse, ServiceAccountWithKeyResponse
from app.services.auth import generate_api_key, hash_api_key

router = APIRouter(prefix="/service-accounts", tags=["service-accounts"])


@router.post("", response_model=ServiceAccountWithKeyResponse, status_code=201)
async def create_service_account(
    request: ServiceAccountCreate,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    api_key = generate_api_key()
    user = User(
        user_type=UserType.SERVICE, display_name=request.display_name,
        model_id=request.model_id, system_version=request.system_version,
        api_key_hash=hash_api_key(api_key),
    )
    db.add(user)
    await db.flush()

    # Determine which roles to assign (default: ["author"])
    role_names = request.roles or ["author"]
    valid_role_values = {r.value for r in RoleName}
    for rn in role_names:
        if rn not in valid_role_values:
            raise HTTPException(status_code=400, detail=f"Invalid role: {rn}")
    roles_result = await db.execute(select(Role).where(Role.name.in_(role_names)))
    roles = roles_result.scalars().all()
    await db.refresh(user, ["roles"])
    for role in roles:
        user.roles.append(role)
    await db.flush()
    await db.refresh(user, ["roles"])

    return ServiceAccountWithKeyResponse(
        id=user.id, display_name=user.display_name, model_id=user.model_id,
        system_version=user.system_version, is_active=user.is_active,
        roles=user.roles, created_at=user.created_at, api_key=api_key,
    )


@router.get("", response_model=list[ServiceAccountResponse])
async def list_service_accounts(
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.user_type == UserType.SERVICE).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.get("/{account_id}", response_model=ServiceAccountResponse)
async def get_service_account(
    account_id: uuid.UUID,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == account_id, User.user_type == UserType.SERVICE))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Service account not found")
    return user


@router.patch("/{account_id}", response_model=ServiceAccountResponse)
async def update_service_account(
    account_id: uuid.UUID, request: ServiceAccountCreate,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == account_id, User.user_type == UserType.SERVICE))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Service account not found")
    user.display_name = request.display_name
    if request.model_id is not None:
        user.model_id = request.model_id
    if request.system_version is not None:
        user.system_version = request.system_version
    return user


@router.post("/{account_id}/rotate-key", response_model=ServiceAccountWithKeyResponse)
async def rotate_api_key(
    account_id: uuid.UUID,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == account_id, User.user_type == UserType.SERVICE))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Service account not found")
    api_key = generate_api_key()
    user.api_key_hash = hash_api_key(api_key)
    await db.refresh(user, ["roles"])
    return ServiceAccountWithKeyResponse(
        id=user.id, display_name=user.display_name, model_id=user.model_id,
        system_version=user.system_version, is_active=user.is_active,
        roles=user.roles, created_at=user.created_at, api_key=api_key,
    )
