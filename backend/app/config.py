from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://app:devpassword@db:5432/knowledge_elicitation"
    JWT_SECRET: str = "dev-secret-change-me-at-least-32b"
    JWT_EXPIRY_HOURS: int = 24
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    DEV_LOGIN_ENABLED: bool = True
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    WORKER_URL: str = ""  # e.g. "http://worker:8001", empty = worker disabled
    ANTHROPIC_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""  # e.g. "openai/bge-m3" (local llama.cpp/TEI) or "text-embedding-3-small" (OpenAI)
    EMBEDDING_API_BASE: str = ""  # e.g. "http://host.docker.internal:8090/v1/" (local) or "" (cloud)
    EMBEDDING_API_KEY: str = ""  # e.g. "no-key" (local) or actual API key (cloud)
    SLACK_BOT_TOKEN: str = ""  # xoxb-... Bot User OAuth Token
    SLACK_DEFAULT_CHANNEL: str = ""  # e.g. "#knowledge-elicitation" or channel ID

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
