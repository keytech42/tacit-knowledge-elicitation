from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

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
