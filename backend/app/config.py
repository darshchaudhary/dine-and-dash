from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Dine&Dash API"
    database_url: str = "postgresql+asyncpg://plateful:plateful@localhost:5432/plateful"
    nutrislice_base_url: str = "https://techdining.api.nutrislice.com"
    frontend_origin: str = "http://localhost:5173"
    nutrislice_timeout_seconds: float = 12.0
    menu_cache_seconds: int = 300
    session_days: int = 7
    cookie_secure: bool = True

    @field_validator("database_url")
    @classmethod
    def async_postgres_url(cls, value: str) -> str:
        # Managed hosts commonly provide the plain PostgreSQL URL scheme.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
