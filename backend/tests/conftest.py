from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.user import Role, RoleName, User, UserType
from app.services.auth import create_jwt_token, generate_api_key, hash_api_key

TEST_DATABASE_URL = settings.DATABASE_URL.replace("/knowledge_elicitation", "/knowledge_elicitation_test")
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        nested = await conn.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(session_sync, transaction):
            nonlocal nested
            if transaction.nested and not transaction._parent.nested:
                nested = conn.sync_connection.begin_nested()

        yield session
        await session.close()
        await trans.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def roles(db: AsyncSession) -> dict[str, Role]:
    result = {}
    for role_name in RoleName:
        role = Role(name=role_name.value)
        db.add(role)
        result[role_name.value] = role
    await db.flush()
    return result


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession, roles: dict[str, Role]) -> User:
    user = User(user_type=UserType.HUMAN, external_id="google_admin_123", display_name="Admin User", email="admin@test.com")
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.ADMIN.value])
    user.roles.append(roles[RoleName.AUTHOR.value])
    await db.flush()
    return user


@pytest_asyncio.fixture
async def author_user(db: AsyncSession, roles: dict[str, Role]) -> User:
    user = User(user_type=UserType.HUMAN, external_id="google_author_123", display_name="Author User", email="author@test.com")
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.AUTHOR.value])
    await db.flush()
    return user


@pytest_asyncio.fixture
async def respondent_user(db: AsyncSession, roles: dict[str, Role]) -> User:
    user = User(user_type=UserType.HUMAN, external_id="google_respondent_123", display_name="Respondent User", email="respondent@test.com")
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.RESPONDENT.value])
    await db.flush()
    return user


@pytest_asyncio.fixture
async def reviewer_user(db: AsyncSession, roles: dict[str, Role]) -> User:
    user = User(user_type=UserType.HUMAN, external_id="google_reviewer_123", display_name="Reviewer User", email="reviewer@test.com")
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.REVIEWER.value])
    await db.flush()
    return user


@pytest_asyncio.fixture
async def service_user(db: AsyncSession, roles: dict[str, Role]) -> tuple[User, str]:
    api_key = generate_api_key()
    user = User(user_type=UserType.SERVICE, display_name="Test LLM Agent", model_id="claude-sonnet-4-5-20250929", api_key_hash=hash_api_key(api_key))
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.AUTHOR.value])
    await db.flush()
    return user, api_key


def auth_header(user: User) -> dict[str, str]:
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token}"}


def api_key_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}
