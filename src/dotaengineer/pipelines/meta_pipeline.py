"""Prefect pipeline: ingest high-MMR hero meta from OpenDota + Stratz.

Runs daily. Writes raw JSON to data/raw/, then loads into DuckDB.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import duckdb
import structlog
from prefect import flow, task

from dotaengineer.config import settings
from dotaengineer.ingestion.opendota import OpenDotaClient
from dotaengineer.ingestion.stratz import StratzClient

logger = structlog.get_logger()
RAW_PATH = pathlib.Path(settings.raw_data_path)


@task(retries=2, retry_delay_seconds=10)
async def fetch_hero_stats_opendota() -> list[dict]:
    async with OpenDotaClient() as client:
        stats = await client.get_hero_stats()
    logger.info("fetched hero stats", source="opendota", count=len(stats))
    return stats


@task(retries=2, retry_delay_seconds=10)
async def fetch_hero_win_rates_stratz(bracket: str = "IMMORTAL") -> dict:
    async with StratzClient() as client:
        stats = await client.get_hero_stats_by_bracket(bracket)
    logger.info("fetched win rates", source="stratz", bracket=bracket)
    return stats


@task
def save_raw(data: dict | list, name: str) -> pathlib.Path:
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    path = RAW_PATH / "meta" / f"{name}_{today}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    logger.info("saved raw", path=str(path))
    return path


@task
def load_hero_meta_to_duckdb(opendota_path: pathlib.Path, stratz_path: pathlib.Path) -> None:
    con = duckdb.connect(settings.duckdb_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS hero_meta_raw (
            ingested_at     TIMESTAMP DEFAULT now(),
            source          VARCHAR,
            hero_id         INTEGER,
            hero_name       VARCHAR,
            -- Aggregate win rates (all brackets, OpenDota)
            total_matches   BIGINT,
            total_wins      BIGINT,
            -- Win rate at immortal bracket (Stratz)
            immortal_wins   BIGINT,
            immortal_matches BIGINT
        )
    """)

    # Load OpenDota stats
    con.execute(f"""
        INSERT INTO hero_meta_raw (source, hero_id, hero_name, total_matches, total_wins)
        SELECT
            'opendota',
            id,
            localized_name,
            pro_pick + "8_pick",
            pro_win + "8_win"
        FROM read_json_auto('{opendota_path}')
    """)

    logger.info("loaded hero meta into duckdb")
    con.close()


@flow(name="meta-ingestion", log_prints=True)
async def meta_ingestion_flow() -> None:
    """Daily pipeline: pull high-MMR hero meta from all sources."""
    od_stats, stratz_stats = await fetch_hero_stats_opendota(), await fetch_hero_win_rates_stratz()

    od_path = save_raw(od_stats, "hero_stats_opendota")
    stratz_path = save_raw(stratz_stats, "hero_stats_stratz")

    load_hero_meta_to_duckdb(od_path, stratz_path)


if __name__ == "__main__":
    import asyncio

    asyncio.run(meta_ingestion_flow())
