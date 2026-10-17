"""
Application configuration via pydantic-settings.
All values are read from environment variables or .env file.
No secrets are hardcoded here.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me"

    # Database
    database_url: str = "sqlite+aiosqlite:///./skillsync.db"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = "skillsync-webhook-secret"


    # Gemini AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Timeouts & Test Doubles
    github_timeout_seconds: float = 10.0
    ai_timeout_seconds: float = 30.0
    use_test_doubles: bool = True

    # CORS
    cors_origins: str = "http://localhost:5173,https://skill-sync-sarang18.vercel.app"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
