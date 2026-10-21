"""Configuration. Every number here is a proposed default from the PRD, to be
validated during the build; the methodology page reads them from /meta."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ESCAPEMENT_", env_file=".env", extra="ignore")

    # "local": self-hosted research mode, admin endpoints on, local sign-in.
    # "public": the hosted arena; every administrative call is rejected (FR-11).
    mode: Literal["local", "public"] = "local"

    database_url: str = "sqlite:///./.escapement/escapement.db"
    # Optional separate login roles; otherwise the app uses SET ROLE on Postgres.
    database_url_api: str | None = None
    database_url_service: str | None = None

    data_dir: Path = Path(".escapement")
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    cookie_secure: bool = False

    github_client_id: str | None = None
    github_client_secret: str | None = None

    seed_secret: str = "local-development-seed-secret"
    signing_key: str | None = None  # base64 Ed25519 private seed
    signing_key_created: str = "2026-10-21"

    replay_store: Literal["fs", "s3"] = "fs"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_prefix: str = "replays/"

    # Budgets enforced by the server (11.1).
    idle_timeout_s: int = 600
    wall_clock_s: int = 1800
    decision_summary_max: int = 280
    payload_limit_bytes: int = 16 * 1024

    # Abuse caps (section 22).
    daily_run_cap: int = 50
    new_account_daily_run_cap: int = 20
    new_account_days: int = 7
    global_daily_run_ceiling: int = 20000
    rate_per_key_per_min: int = 240
    rate_per_user_per_min: int = 480
    rate_anonymous_per_min: int = 120
    max_api_keys: int = 10
    kill_switch: bool = False

    # Seasons (16.3) and Daily (16.4).
    season_weeks: int = 12
    season_instances_per_tier: int = 10
    certified_runs_per_instance: int = 3
    daily_attempts: int = 3

    # Resume bullet floor (14.4).
    bullet_min_instances: int = 5
    bullet_min_runs_per_instance: int = 3

    session_days: int = 30

    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
