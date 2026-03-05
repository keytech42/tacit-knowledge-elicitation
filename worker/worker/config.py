from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    PLATFORM_API_URL: str = "http://api:8000"
    PLATFORM_API_KEY: str = ""
    LLM_MODEL: str = "anthropic/claude-sonnet-4-5-20250929"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.7
    LLM_REVIEW_TEMPERATURE: float = 0.3
    MAX_RETRIES: int = 3
    TASK_TIMEOUT_SECONDS: int = 120

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = WorkerSettings()
