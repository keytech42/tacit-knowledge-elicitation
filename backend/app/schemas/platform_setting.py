import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlatformSettingResponse(BaseModel):
    key: str
    value: Any
    updated_by_id: uuid.UUID | None = None
    updated_at: datetime | None = None
    model_config = {"from_attributes": True}


class PlatformSettingsListResponse(BaseModel):
    settings: dict[str, Any]


class PlatformSettingUpdate(BaseModel):
    value: Any
