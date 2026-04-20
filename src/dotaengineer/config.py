"""Application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API keys
    opendota_api_key: str = ""
    stratz_api_token: str = ""
    steam_api_key: str = ""

    # Player
    my_steam_id: int = 0
    high_mmr_threshold: int = 7000

    # Database
    database_url: str = "postgresql+psycopg://dota:dota@localhost:5432/dotaengineer"
    duckdb_path: str = "./data/warehouse.duckdb"

    # Storage
    raw_data_path: str = "./data/raw"
    processed_data_path: str = "./data/processed"

    # Rate limiting
    opendota_requests_per_minute: int = Field(default=60, description="Free tier limit")
    stratz_requests_per_minute: int = Field(default=30, description="Free tier limit")


settings = Settings()
