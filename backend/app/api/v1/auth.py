import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import Role, RoleName, User, UserType, user_roles
from app.schemas.auth import AuthConfigResponse, GoogleAuthRequest, TokenResponse
from app.services.auth import create_jwt_token, exchange_google_code, find_or_create_user, verify_jwt_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_jwt_token(user),
        user_id=user.id,
        email=user.email or "",
        display_name=user.display_name,
        roles=[r.name if isinstance(r.name, str) else r.name.value for r in user.roles],
    )


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    """Return public auth configuration for the frontend."""
    return AuthConfigResponse(
        google_client_id=settings.GOOGLE_CLIENT_ID,
        dev_login_enabled=settings.DEV_LOGIN_ENABLED,
    )


@router.post("/google", response_model=TokenResponse)
async def google_auth(request: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google OAuth is not configured")
    try:
        google_user_info = await exchange_google_code(request.code)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange Google authorization code")

    user = await find_or_create_user(db, google_user_info)
    return _token_response(user)


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(db: AsyncSession = Depends(get_db)):
    """Create or return a dev admin user. Available when DEV_LOGIN_ENABLED is true."""
    if not settings.DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    dev_email = "dev@localhost"
    result = await db.execute(select(User).where(User.email == dev_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            user_type=UserType.HUMAN,
            external_id="dev-local-admin",
            display_name="Dev Admin",
            email=dev_email,
        )
        db.add(user)
        await db.flush()

        # Same pattern as find_or_create_user: insert directly into the
        # association table to avoid MissingGreenlet on user.roles.append().
        roles_result = await db.execute(select(Role))
        roles = roles_result.scalars().all()
        if roles:
            await db.execute(
                insert(user_roles),
                [{"user_id": user.id, "role_id": role.id} for role in roles],
            )
        await db.refresh(user, ["roles"])

    return _token_response(user)


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
