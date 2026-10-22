from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://steelos:steelos@localhost:5432/steelos"
    session_hours: int = Field(default=8, ge=1, le=24)
    allowed_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def settings() -> Settings:
    return Settings()
