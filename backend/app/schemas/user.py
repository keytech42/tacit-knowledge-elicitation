import uuid
from datetime import datetime

from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: uuid.UUID
    user_type: str
    display_name: str
    email: str | None = None
    avatar_url: str | None = None
    is_active: bool
    roles: list[RoleResponse] = []
    created_at: datetime
    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class RoleAssignRequest(BaseModel):
    role_name: str


class ServiceAccountCreate(BaseModel):
    display_name: str
    model_id: str | None = None
    system_version: str | None = None


class ServiceAccountResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    model_id: str | None = None
    system_version: str | None = None
    is_active: bool
    roles: list[RoleResponse] = []
    created_at: datetime
    model_config = {"from_attributes": True}


class ServiceAccountWithKeyResponse(ServiceAccountResponse):
    api_key: str
