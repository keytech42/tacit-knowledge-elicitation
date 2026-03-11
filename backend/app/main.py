from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.database import async_session, engine
from app.models import Base
from app.models.user import Role, RoleName
from app.api.v1.router import api_router
from app.middleware.ai_logging import AILoggingMiddleware


async def seed_roles(session_factory=None):
    """Seed default roles if they don't exist."""
    factory = session_factory or async_session
    async with factory() as session:
        for role_name in RoleName:
            existing = await session.execute(
                select(Role).where(Role.name == role_name.value)
            )
            if not existing.scalar_one_or_none():
                session.add(Role(name=role_name.value))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_roles()
    yield
    await engine.dispose()


app = FastAPI(
    title="Knowledge Elicitation Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(AILoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db():
    """Extended health check with DB pool stats and table counts."""
    pool = engine.pool

    pool_stats = {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
    }

    async with async_session() as session:
        # Table row counts for key tables
        tables = ["users", "questions", "answers", "reviews", "source_documents"]
        row_counts = {}
        for table in tables:
            result = await session.execute(
                text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — table names are hardcoded
            )
            row_counts[table] = result.scalar()

        # Database size on disk
        result = await session.execute(
            text("SELECT pg_database_size(current_database())")
        )
        db_size_bytes = result.scalar()

    return {
        "status": "ok",
        "pool": pool_stats,
        "row_counts": row_counts,
        "database_size_bytes": db_size_bytes,
    }
