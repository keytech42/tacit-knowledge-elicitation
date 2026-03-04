import uuid

from pydantic import BaseModel


class GoogleAuthRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]


class TokenRefreshRequest(BaseModel):
    refresh_token: str
