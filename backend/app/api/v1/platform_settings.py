from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.user import RoleName, User
from app.schemas.platform_setting import (
    PlatformSettingResponse,
    PlatformSettingsListResponse,
    PlatformSettingUpdate,
)
from app.services.platform_settings import get_all_settings, set_setting

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=PlatformSettingsListResponse)
async def list_settings(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Get all platform settings with defaults applied."""
    settings = await get_all_settings(db)
    return PlatformSettingsListResponse(settings=settings)


@router.put("/{key}", response_model=PlatformSettingResponse)
async def update_setting(
    key: str,
    request: PlatformSettingUpdate,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Update a single platform setting."""
    row = await set_setting(db, key, request.value, current_user.id)
    return row
