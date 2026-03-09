"""Tests for application startup (lifespan hook) and migration consistency.

These tests catch mismatches between the Alembic migration enum values and
the SQLAlchemy model enum values — the exact scenario that caused the
'invalid input value for enum rolename: "ADMIN"' crash on docker-compose up.
"""

import pytest
from sqlalchemy import inspect, select

from app.main import seed_roles
from app.models import Base
from app.models.user import RoleName, UserType
from app.models.answer import AnswerStatus, RevisionTrigger
from app.models.question import QuestionStatus, Confirmation, SourceType
from app.models.review import ReviewTargetType, ReviewVerdict


# ---------------------------------------------------------------------------
# Migration ↔ model enum consistency
# ---------------------------------------------------------------------------

def _model_enum_values(enum_name: str) -> list[str]:
    """Extract the enum values that SQLAlchemy would send to PostgreSQL
    for a given named enum, based on the model metadata."""
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if hasattr(col.type, "enums") and getattr(col.type, "name", None) == enum_name:
                return list(col.type.enums)
    raise ValueError(f"Enum {enum_name!r} not found in model metadata")


# Map of PG enum name → Python enum class (must stay in sync with migration)
_ENUM_MAP = {
    "rolename": RoleName,
    "usertype": UserType,
    "answerstatus": AnswerStatus,
    "revisiontrigger": RevisionTrigger,
    "questionstatus": QuestionStatus,
    "confirmation": Confirmation,
    "reviewtargettype": ReviewTargetType,
    "reviewverdict": ReviewVerdict,
    "sourcetype": SourceType,
}


@pytest.mark.parametrize("enum_name,enum_class", list(_ENUM_MAP.items()))
def test_model_enum_values_are_lowercase(enum_name, enum_class):
    """SQLAlchemy model enums must use .value (lowercase), not .name (UPPERCASE).

    If this fails it means SAEnum is missing values_callable and will send
    the Python enum NAME to PostgreSQL, which won't match the migration's
    lowercase values.
    """
    model_values = _model_enum_values(enum_name)
    expected_values = [e.value for e in enum_class]
    assert model_values == expected_values, (
        f"Enum {enum_name!r}: model sends {model_values} but migration expects {expected_values}. "
        f"Add values_callable=lambda e: [x.value for x in e] to the SAEnum."
    )


# ---------------------------------------------------------------------------
# seed_roles integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_roles_creates_default_roles(setup_database):
    """seed_roles() must insert all default roles into an empty roles table."""
    from tests.conftest import test_session_factory

    await seed_roles(session_factory=test_session_factory)

    async with test_session_factory() as session:
        from app.models.user import Role
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
        from app.models.user import Role
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
