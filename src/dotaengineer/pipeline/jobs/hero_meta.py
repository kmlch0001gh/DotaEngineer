"""Sync hero meta stats (winrate, pickrate, banrate) from OpenDota."""

from __future__ import annotations

import structlog

from dotaengineer.db import Connection
from dotaengineer.pipeline.sources.opendota import OpenDotaClient

log = structlog.get_logger()

# OpenDota bracket IDs → our bracket names
BRACKETS = {
    "1": "herald",
    "2": "guardian",
    "3": "crusader",
    "4": "archon",
    "5": "legend",
    "6": "ancient",
    "7": "divine",
    "8": "immortal",
}


def sync_hero_meta(con: Connection, client: OpenDotaClient) -> int:
    """Sync hero meta stats from OpenDota.

    Fetches /heroStats which returns per-hero win/pick counts
    for each bracket + pro matches.

    Returns number of rows upserted.
    """
    log.info("sync_hero_meta_start")
    data = client.hero_stats()

    count = 0
    for hero in data:
        hero_id = hero["id"]
        hero_name = hero.get("localized_name", f"hero_{hero_id}")

        # Pro bracket
        pro_pick = hero.get("pro_pick", 0) or 0
        pro_win = hero.get("pro_win", 0) or 0
        pro_ban = hero.get("pro_ban", 0) or 0
        if pro_pick > 0:
            _upsert_meta(
                con, hero_id, hero_name, "pro",
                pro_pick, pro_win, pro_ban, 0,
            )
            count += 1

        # Public brackets 1-8
        total_picks = 0
        total_wins = 0
        for bracket_id, bracket_name in BRACKETS.items():
            picks = hero.get(f"{bracket_id}_pick", 0) or 0
            wins = hero.get(f"{bracket_id}_win", 0) or 0
            total_picks += picks
            total_wins += wins
            if picks > 0:
                _upsert_meta(
                    con, hero_id, hero_name, bracket_name,
                    picks, wins, 0, 0,
                )
                count += 1

        # All brackets combined
        if total_picks > 0:
            _upsert_meta(
                con, hero_id, hero_name, "all",
                total_picks, total_wins, pro_ban, 0,
            )
            count += 1

    log.info("sync_hero_meta_done", rows=count)
    return count


def sync_hero_counters(
    con: Connection, client: OpenDotaClient, top_n: int = 10
) -> int:
    """Sync top counters for each hero.

    Fetches /heroes/{id}/matchups for each hero. This is expensive
    (~130 API calls) so use sparingly.

    Returns number of counter rows upserted.
    """
    log.info("sync_hero_counters_start")

    # Get hero list from existing meta
    heroes = con.execute(
        "SELECT DISTINCT hero_id FROM dota_hero_meta"
    ).fetchall()
    hero_ids = [r[0] for r in heroes]

    if not hero_ids:
        # Fallback: use OpenDota hero list
        hero_data = client.hero_stats()
        hero_ids = [h["id"] for h in hero_data]

    count = 0
    for hero_id in hero_ids:
        try:
            matchups = client.hero_matchups(hero_id)
        except Exception as e:
            log.warning("hero_matchup_failed", hero_id=hero_id, error=str(e))
            continue

        # Sort by advantage (games_played > 0, disadvantage = counter)
        valid = [
            m for m in matchups
            if m.get("games_played", 0) > 50
        ]
        valid.sort(key=lambda m: m["wins"] / m["games_played"])

        # Top N counters (lowest winrate against)
        for m in valid[:top_n]:
            counter_id = m["hero_id"]
            games = m["games_played"]
            wins = m["wins"]
            advantage = (wins / games * 100 - 50) if games > 0 else 0

            con.execute(
                """
                INSERT INTO dota_hero_counters
                    (hero_id, counter_hero_id, advantage, games, synced_at)
                VALUES (?, ?, ?, ?, now())
                ON CONFLICT (hero_id, counter_hero_id)
                DO UPDATE SET advantage = ?, games = ?, synced_at = now()
                """,
                [hero_id, counter_id, round(advantage, 2), games,
                 round(advantage, 2), games],
            )
            count += 1

    log.info("sync_hero_counters_done", rows=count)
    return count


def _upsert_meta(
    con: Connection,
    hero_id: int,
    hero_name: str,
    bracket: str,
    picks: int,
    wins: int,
    bans: int,
    total_matches: int,
) -> None:
    wr = round(wins / picks * 100, 2) if picks > 0 else 0
    pr = round(picks / max(total_matches, 1) * 100, 2) if total_matches > 0 else 0
    br = round(bans / max(total_matches, 1) * 100, 2) if total_matches > 0 else 0

    con.execute(
        """
        INSERT INTO dota_hero_meta
            (hero_id, hero_name, bracket, picks, wins, bans,
             win_rate, pick_rate, ban_rate, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT (hero_id, bracket)
        DO UPDATE SET
            hero_name = ?, picks = ?, wins = ?, bans = ?,
            win_rate = ?, pick_rate = ?, ban_rate = ?,
            synced_at = now()
        """,
        [hero_id, hero_name, bracket, picks, wins, bans, wr, pr, br,
         hero_name, picks, wins, bans, wr, pr, br],
    )
