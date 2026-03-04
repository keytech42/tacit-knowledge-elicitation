import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import RoleName, User
from app.services.auth import validate_api_key, verify_jwt_token


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the current user from the request."""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = await validate_api_key(db, api_key)
        if user:
            request.state.auth_method = "api_key"
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication")

    token = auth_header[7:]
    try:
        payload = verify_jwt_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    request.state.auth_method = "jwt"
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*role_names: RoleName):
    """Dependency factory that requires the user to have at least one of the specified roles."""
    async def checker(current_user: CurrentUser) -> User:
        user_role_names = {r.name for r in current_user.roles}
        required = {rn.value if isinstance(rn, RoleName) else rn for rn in role_names}
        if not user_role_names.intersection(required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return Depends(checker)
