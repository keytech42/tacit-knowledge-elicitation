"""Tests for application startup (lifespan hook).

These tests exercise seed_roles() against real tables to catch
the kind of failure that occurs on `docker compose up` when
tables don't exist. Other tests bypass this because conftest
creates tables via Base.metadata.create_all() and manually
inserts roles per-test via fixtures.
"""

import pytest
from sqlalchemy import select

from app.main import seed_roles
from app.models.user import Role, RoleName


@pytest.mark.asyncio
async def test_seed_roles_creates_default_roles(setup_database):
    """seed_roles() must insert all default roles into an empty roles table."""
    from tests.conftest import test_session_factory

    await seed_roles(session_factory=test_session_factory)

    async with test_session_factory() as session:
        result = await session.execute(select(Role))
        roles = result.scalars().all()

    expected = {r.value for r in RoleName}
    actual = {r.name for r in roles}
    assert expected <= actual, f"Missing roles: {expected - actual}"


@pytest.mark.asyncio
async def test_seed_roles_is_idempotent(setup_database):
    """Calling seed_roles() twice must not duplicate roles."""
    from tests.conftest import test_session_factory

    await seed_roles(session_factory=test_session_factory)
    await seed_roles(session_factory=test_session_factory)

    async with test_session_factory() as session:
        result = await session.execute(select(Role))
        roles = result.scalars().all()

    role_names = [r.name for r in roles]
    assert len(role_names) == len(set(role_names)), "Duplicate roles found"


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health endpoint should return 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
