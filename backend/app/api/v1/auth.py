import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import GoogleAuthRequest, TokenResponse
from app.services.auth import create_jwt_token, exchange_google_code, find_or_create_user, verify_jwt_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=TokenResponse)
async def google_auth(request: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        google_user_info = await exchange_google_code(request.code)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange Google authorization code")

    user = await find_or_create_user(db, google_user_info)
    token = create_jwt_token(user)

    return TokenResponse(
        access_token=token, user_id=user.id, email=user.email or "",
        display_name=user.display_name,
        roles=[r.name if isinstance(r.name, str) else r.name.value for r in user.roles],
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(db: AsyncSession = Depends(get_db), token: str = ""):
    try:
        payload = verify_jwt_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_token = create_jwt_token(user)
    return TokenResponse(
        access_token=new_token, user_id=user.id, email=user.email or "",
        display_name=user.display_name,
        roles=[r.name if isinstance(r.name, str) else r.name.value for r in user.roles],
    )
