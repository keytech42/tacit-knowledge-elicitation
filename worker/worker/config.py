from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    PLATFORM_API_URL: str = "http://api:8000"
    PLATFORM_API_KEY: str = ""
    LLM_MODEL: str = "anthropic/claude-sonnet-4-6"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.7
    LLM_REVIEW_TEMPERATURE: float = 0.3
    MAX_RETRIES: int = 3
    TASK_TIMEOUT_SECONDS: int = 120
    DEDUP_STRATEGY: str = "llm"  # "llm" or "embedding"
    EXTRACTION_TEMPERATURE: float = 0.3
    EXTRACTION_AUTO_SUBMIT: bool = False
    RECOMMENDATION_MODEL: str = ""  # Override LLM_MODEL for recommendations (e.g. "anthropic/claude-haiku-4-5-20251001")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = WorkerSettings()
