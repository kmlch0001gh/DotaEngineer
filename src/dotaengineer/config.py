"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Cafe
    cafe_name: str = "Dota Cafe"

    # Database (PostgreSQL)
    database_url: str = "postgresql://localhost:5432/dotacafe"

    # Replay
    replay_watch_dir: str = ""
    replay_upload_dir: str = "./data/replays"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Admin (access /admin?token=THIS_VALUE to enable write mode)
    admin_token: str = "changeme"

    # ELO
    elo_k_factor: int = 32
    elo_calibration_k: int = 48
    elo_calibration_games: int = 10
    elo_starting_mmr: int = 1000
    elo_floor: int = 100

    @property
    def static_dir(self) -> Path:
        return Path(__file__).parent / "static"

    @property
    def template_dir(self) -> Path:
        return Path(__file__).parent / "templates"

    @property
    def heroes_json_path(self) -> Path:
        return self.static_dir / "heroes.json"


settings = Settings()
