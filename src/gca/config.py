from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/game_competitor"
    )
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-4-6"
    embedding_model: str = "all-MiniLM-L6-v2"
    steam_api_key: str | None = None
    youtube_api_key: str | None = None

    week_of: str | None = None
    top_games_limit: int = 200
    top_n_competitors: int = 20

    log_level: str = "INFO"
    http_timeout: float = 20.0


settings = Settings()
