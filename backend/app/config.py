"""Backend configuration (environment-driven, 12-factor)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AQUA_", env_file=".env", extra="ignore")

    # Storage. Default: local SQLite file. Swap for e.g.
    # postgresql+psycopg://user:pass@host/db (or a TimescaleDB URL) in production.
    database_url: str = "sqlite:///./aqua.db"

    # MQTT broker.
    broker_host: str = "localhost"
    broker_port: int = 1883
    broker_user: str | None = None
    broker_pass: str | None = None

    # Optional API key. When set, write/control endpoints require header
    # `X-API-Key: <key>`. Empty = open (development).
    api_key: str | None = None

    # Push notifications.
    # provider: "console" (logs), "fcm" (needs fcm_server_key), or "none".
    push_provider: str = "console"
    fcm_server_key: str | None = None

    # Alert debounce: minimum seconds between repeated pushes for the same
    # (device, metric) breach.
    alert_debounce_s: int = 300

    # CORS origins for the mobile app / web tooling (comma-separated, "*" = any).
    cors_origins: str = "*"


settings = Settings()
