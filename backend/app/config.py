from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://app:devpassword@db:5432/knowledge_elicitation"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_EXPIRY_HOURS: int = 24
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
