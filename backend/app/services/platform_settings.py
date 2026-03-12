import logging
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import PlatformSetting

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "auto_review_enabled": True,
    "auto_scaffold_enabled": True,
}


async def get_setting(db: AsyncSession, key: str) -> Any:
    """Get a single setting value. Returns the default if no row exists or on DB error."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    try:
        result = await db.execute(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        row = result.scalar_one_or_none()
    except Exception:
        logger.warning("Failed to read setting %s, using default", key, exc_info=True)
        return DEFAULTS[key]
    if row is None:
        return DEFAULTS[key]
    return row.value


async def get_all_settings(db: AsyncSession) -> dict[str, Any]:
    """Get all settings, merging DB overrides onto defaults. Falls back to defaults on DB error."""
    settings = dict(DEFAULTS)
    try:
        result = await db.execute(select(PlatformSetting))
        for row in result.scalars().all():
            if row.key in DEFAULTS:
                settings[row.key] = row.value
    except Exception:
        logger.warning("Failed to read settings, using defaults", exc_info=True)
    return settings


async def set_setting(
    db: AsyncSession, key: str, value: Any, user_id: uuid.UUID | None = None
) -> PlatformSetting:
    """Upsert a setting. Validates key is known and type matches default."""
    if key not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {key}")

    default = DEFAULTS[key]
    if type(value) is not type(default):
        raise HTTPException(
            status_code=422,
            detail=f"Expected {type(default).__name__} for '{key}', got {type(value).__name__}",
        )

    result = await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == key)
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = PlatformSetting(key=key, value=value, updated_by_id=user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by_id = user_id

    await db.flush()
    await db.refresh(row)
    return row
