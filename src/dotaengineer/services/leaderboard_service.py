"""Leaderboard and MMR history queries."""

from __future__ import annotations

from dotaengineer.db import Connection


def get_leaderboard(con: Connection, limit: int = 50) -> list[dict]:
    """Get leaderboard ordered by MMR descending."""
    rows = con.execute(
        """
        SELECT
            id, display_name, username, mmr,
            games_played, wins, losses,
            CASE WHEN games_played > 0
                THEN round(wins::NUMERIC / games_played * 100, 1)
                ELSE 0.0
            END as win_rate_pct
        FROM players
        WHERE is_active = true AND games_played > 0
        ORDER BY mmr DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    results = []
    for i, r in enumerate(rows):
        d = dict(zip(cols, r))
        d["rank"] = i + 1
        results.append(d)
    return results


def get_mmr_history(player_id: int, con: Connection) -> list[dict]:
    """Get MMR history for a player, ordered by match time."""
    rows = con.execute(
        """
        SELECT
            mh.match_id, mh.mmr_before, mh.mmr_after, mh.mmr_change,
            mh.created_at, m.played_at
        FROM mmr_history mh
        JOIN matches m ON m.id = mh.match_id
        WHERE mh.player_id = ?
        ORDER BY m.played_at ASC
        """,
        [player_id],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_cafe_stats(con: Connection) -> dict:
    """Get overall cafe statistics for the dashboard."""
    total_matches = con.execute("SELECT count(*) FROM matches").fetchone()[0]
    total_players = con.execute("SELECT count(*) FROM players WHERE is_active = true").fetchone()[0]
    total_games_played = con.execute(
        "SELECT coalesce(sum(games_played), 0) FROM players"
    ).fetchone()[0]

    # Most popular hero
    popular_hero = con.execute(
        """
        SELECT hero_name, count(*) as picks
        FROM match_players
        GROUP BY hero_name
        ORDER BY picks DESC
        LIMIT 1
        """
    ).fetchone()

    # Highest MMR player
    top_player = con.execute(
        """
        SELECT display_name, mmr FROM players
        WHERE is_active = true AND games_played > 0
        ORDER BY mmr DESC LIMIT 1
        """
    ).fetchone()

    return {
        "total_matches": total_matches,
        "total_players": total_players,
        "total_games_played": total_games_played,
        "popular_hero": popular_hero[0] if popular_hero else None,
        "popular_hero_picks": popular_hero[1] if popular_hero else 0,
        "top_player_name": top_player[0] if top_player else None,
        "top_player_mmr": top_player[1] if top_player else 0,
    }
