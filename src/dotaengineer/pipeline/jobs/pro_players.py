"""Sync professional and high-MMR players from OpenDota."""

from __future__ import annotations

import structlog

from dotaengineer.db import Connection
from dotaengineer.pipeline.sources.opendota import OpenDotaClient

log = structlog.get_logger()


def sync_pro_players(con: Connection, client: OpenDotaClient) -> int:
    """Sync verified professional players from OpenDota.

    Fetches /proPlayers — list of ~500 verified pro accounts.
    Stores with category='pro'.

    Returns number of players upserted.
    """
    log.info("sync_pro_players_start")
    data = client.pro_players()

    count = 0
    for p in data:
        account_id = p.get("account_id")
        name = p.get("name") or p.get("personaname") or ""
        if not account_id or not name:
            continue

        team = p.get("team_name") or ""
        country = p.get("country_code") or ""
        avatar = p.get("avatarfull") or ""

        con.execute(
            """
            INSERT INTO dota_tracked_players
                (account_id, name, team, category, region, avatar_url, synced_at)
            VALUES (?, ?, ?, 'pro', ?, ?, now())
            ON CONFLICT (account_id)
            DO UPDATE SET
                name = ?, team = ?, region = ?, avatar_url = ?,
                synced_at = now()
            """,
            [account_id, name, team, country, avatar,
             name, team, country, avatar],
        )
        count += 1

    log.info("sync_pro_players_done", players=count)
    return count


def add_tracked_player(
    con: Connection,
    account_id: int,
    name: str,
    category: str = "high_mmr",
    team: str = "",
    region: str = "",
) -> None:
    """Manually add a player to tracking."""
    con.execute(
        """
        INSERT INTO dota_tracked_players
            (account_id, name, team, category, region, synced_at)
        VALUES (?, ?, ?, ?, ?, now())
        ON CONFLICT (account_id)
        DO UPDATE SET
            name = ?, team = ?, category = ?, region = ?,
            synced_at = now()
        """,
        [account_id, name, team, category, region,
         name, team, category, region],
    )
    log.info("player_tracked", account_id=account_id, name=name)
