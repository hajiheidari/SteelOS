from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://steelos:steelos@localhost:5432/steelos"
    assistant_provider: Literal["disabled", "ollama"] = "disabled"
    assistant_model: Literal["qwen3:1.7b"] = "qwen3:1.7b"
    assistant_ollama_url: str = "http://127.0.0.1:11434"

    @field_validator("assistant_ollama_url")
    @classmethod
    def local_model_url(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname
            not in {"127.0.0.1", "localhost", "::1", "ollama", "host.docker.internal"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError("Only a local Ollama base URL is allowed")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("Invalid local model port")
        return value

    session_hours: int = Field(default=8, ge=1, le=24)
    allowed_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def settings() -> Settings:
    return Settings()
