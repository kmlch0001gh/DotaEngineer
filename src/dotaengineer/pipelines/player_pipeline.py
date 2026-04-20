"""Prefect pipeline: ingest your own match history and build personal analytics.

Fetches last N ranked matches, stores full JSON, builds personal fact table.
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


@task(retries=2)
async def fetch_player_match_list(account_id: int, limit: int = 200) -> list[dict]:
    async with OpenDotaClient() as client:
        matches = await client.get_player_matches(account_id, limit=limit)
    logger.info("fetched match list", account_id=account_id, count=len(matches))
    return matches


@task(retries=2)
async def fetch_full_match(match_id: int) -> dict:
    """Fetch full match data including itemization, ward positions, etc."""
    async with OpenDotaClient() as client:
        match = await client.get_match(match_id)
    return match.model_dump()


@task(retries=2)
async def fetch_stratz_matches(steam_id: int, take: int = 100) -> dict:
    async with StratzClient() as client:
        data = await client.get_player_matches(steam_id, take=take)
    return data


@task
def save_player_raw(data: list | dict, account_id: int, name: str) -> pathlib.Path:
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    path = RAW_PATH / "players" / str(account_id) / f"{name}_{today}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


@task
def build_player_fact_table(match_list_path: pathlib.Path) -> None:
    """Load match list into DuckDB personal fact table."""
    con = duckdb.connect(settings.duckdb_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS player_matches (
            match_id        BIGINT PRIMARY KEY,
            hero_id         INTEGER,
            player_slot     INTEGER,
            radiant_win     BOOLEAN,
            won             BOOLEAN,
            start_time      TIMESTAMP,
            duration_sec    INTEGER,
            kills           INTEGER,
            deaths          INTEGER,
            assists         INTEGER,
            last_hits       INTEGER,
            denies          INTEGER,
            gpm             INTEGER,
            xpm             INTEGER,
            net_worth       INTEGER,
            hero_damage     INTEGER,
            tower_damage    INTEGER,
            lane            INTEGER,
            lane_role       INTEGER,
            is_roaming      BOOLEAN,
            rank_tier       INTEGER,
            fetched_at      TIMESTAMP DEFAULT now()
        )
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO player_matches
        SELECT
            match_id,
            hero_id,
            player_slot,
            radiant_win,
            CASE
                WHEN player_slot < 128 AND radiant_win THEN true
                WHEN player_slot >= 128 AND NOT radiant_win THEN true
                ELSE false
            END AS won,
            to_timestamp(start_time) AS start_time,
            duration AS duration_sec,
            kills, deaths, assists, last_hits, denies,
            gold_per_min AS gpm,
            xp_per_min AS xpm,
            net_worth, hero_damage, tower_damage,
            lane, lane_role, is_roaming, rank_tier,
            now() AS fetched_at
        FROM read_json_auto('{match_list_path}')
    """)

    con.close()
    logger.info("player fact table updated")


@flow(name="player-ingestion", log_prints=True)
async def player_ingestion_flow(
    account_id: int | None = None,
    limit: int = 200,
) -> None:
    """Ingest personal match history and build analytics tables."""
    account_id = account_id or settings.my_steam_id
    if not account_id:
        raise ValueError("Set MY_STEAM_ID in .env or pass account_id")

    match_list = await fetch_player_match_list(account_id, limit=limit)
    match_list_path = save_player_raw(match_list, account_id, "match_list")
    build_player_fact_table(match_list_path)

    # Optionally pull from Stratz for richer data (imp score, laning outcome)
    if settings.stratz_api_token:
        stratz_data = await fetch_stratz_matches(account_id)
        save_player_raw(stratz_data, account_id, "stratz_matches")

    logger.info("player ingestion complete", account_id=account_id)


if __name__ == "__main__":
    import asyncio

    asyncio.run(player_ingestion_flow())
