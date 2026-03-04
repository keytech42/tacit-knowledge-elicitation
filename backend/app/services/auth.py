import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Role, RoleName, User, UserType, user_roles


async def exchange_google_code(code: str, redirect_uri: str = "postmessage") -> dict:
    """Exchange Google OAuth authorization code for user info."""
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_response.raise_for_status()
        return userinfo_response.json()


async def find_or_create_user(db: AsyncSession, google_user_info: dict) -> User:
    """Find existing user by Google ID or create a new one."""
    google_id = google_user_info["id"]
    email = google_user_info.get("email", "")
    display_name = google_user_info.get("name", email)
    avatar_url = google_user_info.get("picture")

    result = await db.execute(select(User).where(User.external_id == google_id))
    user = result.scalar_one_or_none()

    if user:
        user.display_name = display_name
        user.avatar_url = avatar_url
        return user

    user = User(
        user_type=UserType.HUMAN,
        external_id=google_id,
        display_name=display_name,
        email=email,
        avatar_url=avatar_url,
    )
    db.add(user)
    await db.flush()

    # Determine which roles to assign
    role_names = {RoleName.RESPONDENT}
    if settings.BOOTSTRAP_ADMIN_EMAIL and email.lower() == settings.BOOTSTRAP_ADMIN_EMAIL.lower():
        role_names = set(RoleName)

    roles_result = await db.execute(select(Role).where(Role.name.in_([r.value for r in role_names])))
    roles = roles_result.scalars().all()

    # Insert directly into the association table to avoid async lazy-load issues
    if roles:
        await db.execute(
            insert(user_roles),
            [{"user_id": user.id, "role_id": role.id} for role in roles],
        )

    # Refresh so the user object has roles loaded for JWT creation
    await db.refresh(user, ["roles"])

    return user


def create_jwt_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "user_type": user.user_type if isinstance(user.user_type, str) else user.user_type.value,
        "roles": [r.name if isinstance(r.name, str) else r.name.value for r in user.roles],
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_jwt_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(48)


async def validate_api_key(db: AsyncSession, api_key: str) -> User | None:
    key_hash = hash_api_key(api_key)
    result = await db.execute(
        select(User).where(
            User.api_key_hash == key_hash,
            User.is_active == True,  # noqa: E712
            User.user_type == UserType.SERVICE,
        )
    )
    return result.scalar_one_or_none()
