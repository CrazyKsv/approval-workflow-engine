from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/approvals"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2.6"
    agent_max_iterations: int = 8
    agent_history_limit: int = 40

    enable_escalation_sweep: bool = True
    escalation_sweep_seconds: int = 60

    seed_on_startup: bool = True

    # Declarative workflow-template catalog, auto-loaded on startup (create-if-missing).
    load_templates_on_startup: bool = True
    templates_file: str = str(Path(__file__).resolve().parent / "workflow_templates.yaml")


@lru_cache
def get_settings() -> Settings:
    return Settings()
