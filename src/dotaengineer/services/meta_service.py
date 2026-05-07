"""Service for pipeline meta data — hero stats, counters, builds, pro scene."""

from __future__ import annotations

import json

from dotaengineer.db import Connection


def get_hero_meta(
    con: Connection, bracket: str = "immortal", limit: int = 30
) -> list[dict]:
    """Get hero meta stats for a bracket, sorted by winrate."""
    rows = con.execute(
        """
        SELECT hero_id, hero_name, picks, wins, bans,
               win_rate, pick_rate, ban_rate
        FROM dota_hero_meta
        WHERE bracket = ? AND picks > 0
        ORDER BY win_rate DESC
        LIMIT ?
        """,
        [bracket, limit],
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_brackets(con: Connection) -> list[str]:
    """Get available brackets."""
    rows = con.execute(
        "SELECT DISTINCT bracket FROM dota_hero_meta ORDER BY bracket"
    ).fetchall()
    return [r[0] for r in rows]


def get_hero_counters(
    con: Connection, hero_id: int, limit: int = 10
) -> list[dict]:
    """Get worst matchups (counters) for a hero."""
    rows = con.execute(
        """
        SELECT c.counter_hero_id, m.hero_name, c.advantage, c.games
        FROM dota_hero_counters c
        LEFT JOIN dota_hero_meta m
            ON m.hero_id = c.counter_hero_id AND m.bracket = 'all'
        WHERE c.hero_id = ?
        ORDER BY c.advantage ASC
        LIMIT ?
        """,
        [hero_id, limit],
    ).fetchall()
    return [
        {
            "hero_id": r[0],
            "hero_name": r[1] or f"Hero {r[0]}",
            "advantage": round(float(r[2]), 1),
            "games": r[3],
        }
        for r in rows
    ]


def get_hero_best_against(
    con: Connection, hero_id: int, limit: int = 10
) -> list[dict]:
    """Get best matchups (strong against) for a hero."""
    rows = con.execute(
        """
        SELECT c.counter_hero_id, m.hero_name, c.advantage, c.games
        FROM dota_hero_counters c
        LEFT JOIN dota_hero_meta m
            ON m.hero_id = c.counter_hero_id AND m.bracket = 'all'
        WHERE c.hero_id = ?
        ORDER BY c.advantage DESC
        LIMIT ?
        """,
        [hero_id, limit],
    ).fetchall()
    return [
        {
            "hero_id": r[0],
            "hero_name": r[1] or f"Hero {r[0]}",
            "advantage": round(float(r[2]), 1),
            "games": r[3],
        }
        for r in rows
    ]


def get_hero_builds(con: Connection, hero_id: int) -> dict:
    """Get item builds for a hero across game phases."""
    rows = con.execute(
        """
        SELECT build_type, items
        FROM dota_hero_builds
        WHERE hero_id = ? AND bracket = 'all'
        ORDER BY build_type
        """,
        [hero_id],
    ).fetchall()
    result = {}
    for build_type, items_raw in rows:
        items = items_raw if isinstance(items_raw, list) else json.loads(items_raw)
        result[build_type] = items[:8]
    return result


def get_top_heroes_by_bracket(con: Connection) -> dict[str, list[dict]]:
    """Get top 5 heroes per bracket for quick overview."""
    brackets = ["immortal", "divine", "ancient", "pro"]
    result = {}
    for b in brackets:
        rows = con.execute(
            """
            SELECT hero_id, hero_name, win_rate, picks
            FROM dota_hero_meta
            WHERE bracket = ? AND picks > 100
            ORDER BY win_rate DESC LIMIT 5
            """,
            [b],
        ).fetchall()
        result[b] = [
            {"hero_id": r[0], "hero_name": r[1],
             "win_rate": round(float(r[2]), 1), "picks": r[3]}
            for r in rows
        ]
    return result


def get_pro_players_sample(con: Connection, limit: int = 20) -> list[dict]:
    """Get sample of tracked pro players."""
    rows = con.execute(
        """
        SELECT account_id, name, team, category, region
        FROM dota_tracked_players
        WHERE team IS NOT NULL AND team != ''
        ORDER BY name
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return [
        {"account_id": r[0], "name": r[1], "team": r[2],
         "category": r[3], "region": r[4] or ""}
        for r in rows
    ]


def get_meta_summary(con: Connection) -> dict:
    """Get summary stats for the meta page header."""
    hero_count = con.execute(
        "SELECT count(DISTINCT hero_id) FROM dota_hero_meta"
    ).fetchone()[0]
    counter_count = con.execute(
        "SELECT count(*) FROM dota_hero_counters"
    ).fetchone()[0]
    build_count = con.execute(
        "SELECT count(*) FROM dota_hero_builds"
    ).fetchone()[0]
    pro_count = con.execute(
        "SELECT count(*) FROM dota_tracked_players"
    ).fetchone()[0]
    match_count = con.execute(
        "SELECT count(*) FROM dota_tracked_matches"
    ).fetchone()[0]
    synced_at = con.execute(
        "SELECT max(synced_at) FROM dota_hero_meta"
    ).fetchone()[0]
    return {
        "heroes": hero_count,
        "counters": counter_count,
        "builds": build_count,
        "pro_players": pro_count,
        "pro_matches": match_count,
        "synced_at": synced_at,
    }
