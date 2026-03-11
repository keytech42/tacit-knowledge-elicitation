"""
Create a service account directly against the database.

Use this in production when dev-login is disabled and you need to create
or rotate a service account without a browser-based admin JWT.

Usage:
    docker compose exec api python scripts/create_service_account.py
    docker compose exec api python scripts/create_service_account.py \
        --name "LLM Worker" --roles author,reviewer
"""

import argparse
import asyncio
import sys

from sqlalchemy import insert, select

sys.path.insert(0, "/app")

from app.database import async_session
from app.models.user import Role, User, UserType, user_roles
from app.services.auth import generate_api_key, hash_api_key


async def create_service_account(
    display_name: str,
    role_names: list[str],
    model_id: str | None = None,
) -> tuple[User, str]:
    async with async_session() as session:
        # Load requested roles
        result = await session.execute(select(Role).where(Role.name.in_(role_names)))
        roles = result.scalars().all()

        found_names = {r.name for r in roles}
        missing = set(role_names) - found_names
        if missing:
            print(f"Error: roles not found: {missing}")
            print(f"Available: {found_names}")
            sys.exit(1)

        # Create user
        api_key = generate_api_key()
        user = User(
            user_type=UserType.SERVICE.value,
            display_name=display_name,
            model_id=model_id,
            api_key_hash=hash_api_key(api_key),
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # Assign roles
        await session.execute(
            insert(user_roles),
            [{"user_id": user.id, "role_id": r.id} for r in roles],
        )

        await session.commit()
        await session.refresh(user, ["roles"])

        return user, api_key


async def main():
    parser = argparse.ArgumentParser(description="Create a service account")
    parser.add_argument(
        "--name", default="LLM Worker", help="Display name (default: LLM Worker)"
    )
    parser.add_argument(
        "--roles",
        default="author,reviewer",
        help="Comma-separated roles (default: author,reviewer)",
    )
    parser.add_argument(
        "--model-id",
        default="claude-sonnet-4-6",
        help="Model identifier (default: claude-sonnet-4-6)",
    )
    args = parser.parse_args()

    role_list = [r.strip() for r in args.roles.split(",")]

    print(f"Creating service account '{args.name}' with roles: {role_list}")
    user, api_key = await create_service_account(
        display_name=args.name,
        role_names=role_list,
        model_id=args.model_id,
    )

    print()
    print(f"Service account created:")
    print(f"  ID:    {user.id}")
    print(f"  Name:  {user.display_name}")
    print(f"  Roles: {[r.name for r in user.roles]}")
    print()
    print(f"  API Key: {api_key}")
    print()
    print(f"Set this in your .env:")
    print(f"  WORKER_API_KEY={api_key}")


if __name__ == "__main__":
    asyncio.run(main())
