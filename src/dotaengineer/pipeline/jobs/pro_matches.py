"""Sync recent matches from tracked pro/high-MMR players."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from dotaengineer.db import Connection
from dotaengineer.models.hero import get_hero_name
from dotaengineer.pipeline.sources.opendota import OpenDotaClient

log = structlog.get_logger()


def sync_pro_matches(con: Connection, client: OpenDotaClient) -> int:
    """Sync recent professional matches from OpenDota.

    Fetches /proMatches — last 100 pro matches.
    Stores basic match data with players linked to tracked accounts.

    Returns number of match rows inserted.
    """
    log.info("sync_pro_matches_start")
    matches = client.pro_matches()

    count = 0
    for m in matches:
        match_id = m.get("match_id")
        if not match_id:
            continue

        # Check if already synced
        existing = con.execute(
            "SELECT 1 FROM dota_tracked_matches WHERE match_id = ? LIMIT 1",
            [match_id],
        ).fetchone()
        if existing:
            continue

        duration = m.get("duration", 0) or 0
        radiant_win = m.get("radiant_win")
        start_time = m.get("start_time", 0)
        played_at = (
            datetime.fromtimestamp(start_time, tz=UTC)
            if start_time else None
        )

        # Pro matches from /proMatches don't have per-player stats
        # Store as a marker with match_id so we don't re-fetch
        con.execute(
            """
            INSERT INTO dota_tracked_matches
                (match_id, account_id, hero_id, hero_name, won,
                 duration_seconds, played_at, bracket, synced_at)
            VALUES (?, 0, 0, '', ?, ?, ?, 'pro', now())
            ON CONFLICT (match_id, account_id) DO NOTHING
            """,
            [match_id, radiant_win, duration, played_at],
        )
        count += 1

    log.info("sync_pro_matches_done", matches=count)
    return count


def sync_tracked_player_matches(
    con: Connection, client: OpenDotaClient, limit: int = 20
) -> int:
    """Sync recent matches for all tracked players.

    Fetches /players/{id}/recentMatches for each tracked player.
    This is expensive (~N API calls for N tracked players).
    Use limit to control how many players to sync per run.

    Returns total match rows inserted.
    """
    log.info("sync_tracked_player_matches_start")

    players = con.execute(
        """
        SELECT account_id, name, category
        FROM dota_tracked_players
        ORDER BY synced_at ASC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    total = 0
    for account_id, name, category in players:
        try:
            matches = client.player_recent_matches(account_id)
        except Exception as e:
            log.warning(
                "player_matches_failed",
                account_id=account_id, error=str(e),
            )
            continue

        for m in matches:
            match_id = m.get("match_id")
            if not match_id:
                continue

            hero_id = m.get("hero_id", 0)
            hero_name = get_hero_name(hero_id)
            kills = m.get("kills", 0)
            deaths = m.get("deaths", 0)
            assists = m.get("assists", 0)
            gpm = m.get("gold_per_min", 0)
            xpm = m.get("xp_per_min", 0)
            duration = m.get("duration", 0)
            player_slot = m.get("player_slot", 0)
            radiant_win = m.get("radiant_win")

            # Determine if player won
            is_radiant = player_slot < 128
            won = (is_radiant == radiant_win) if radiant_win is not None else None

            start_time = m.get("start_time", 0)
            played_at = (
                datetime.fromtimestamp(start_time, tz=UTC)
                if start_time else None
            )

            con.execute(
                """
                INSERT INTO dota_tracked_matches
                    (match_id, account_id, hero_id, hero_name, won,
                     kills, deaths, assists, gpm, xpm,
                     duration_seconds, played_at, bracket, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
                ON CONFLICT (match_id, account_id) DO NOTHING
                """,
                [
                    match_id, account_id, hero_id, hero_name, won,
                    kills, deaths, assists, gpm, xpm,
                    duration, played_at, category,
                ],
            )
            total += 1

        # Update player's synced_at
        con.execute(
            "UPDATE dota_tracked_players SET synced_at = now() WHERE account_id = ?",
            [account_id],
        )
        log.info("player_synced", name=name, matches=len(matches))

    log.info("sync_tracked_player_matches_done", total=total)
    return total
