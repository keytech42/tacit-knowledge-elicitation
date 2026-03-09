import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.database import get_db
from app.models.user import Role, RoleName, User
from app.schemas.user import RoleAssignRequest, UserListResponse, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    return current_user


@router.get("/search", response_model=UserListResponse)
async def search_users(
    current_user: User = require_role(RoleName.REVIEWER, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    q: str = "",
    role: str | None = None,
    limit: int = 20,
):
    """Search users by name/email with optional role filter. Available to reviewers and admins."""
    query = select(User).where(User.user_type == "human", User.is_active == True)  # noqa: E712

    if role:
        query = query.join(User.roles).where(Role.name == role)

    if q.strip():
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            func.lower(User.display_name).like(pattern)
            | func.lower(func.coalesce(User.email, "")).like(pattern)
        )

    result = await db.execute(query.order_by(User.display_name).limit(min(limit, 50)))
    users = list(result.scalars().unique().all())
    return UserListResponse(users=users, total=len(users))


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    skip: int = 0, limit: int = 50,
):
    result = await db.execute(select(User).offset(skip).limit(limit).order_by(User.created_at.desc()))
    users = result.scalars().all()
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar() or 0
    return UserListResponse(users=users, total=total)


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_role(
    user_id: uuid.UUID, request: RoleAssignRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        role_name = RoleName(request.role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role_name}")

    role_result = await db.execute(select(Role).where(Role.name == role_name.value))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role in user.roles:
        raise HTTPException(status_code=409, detail="User already has this role")

    user.roles.append(role)
    return user


@router.delete("/{user_id}/roles/{role_name}", response_model=UserResponse)
async def remove_role(
    user_id: uuid.UUID, role_name: str,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role_result = await db.execute(select(Role).where(Role.name == role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role not in user.roles:
        raise HTTPException(status_code=404, detail="User does not have this role")

    user.roles.remove(role)
    return user
