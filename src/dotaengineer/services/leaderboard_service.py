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
        "top_player_name": top_player[0] if top_player else None,
        "top_player_mmr": top_player[1] if top_player else 0,
    }


def get_top_heroes_picked(con: Connection, limit: int = 5) -> list[dict]:
    """Most picked heroes in the cafe."""
    rows = con.execute(
        """
        SELECT hero_id, hero_name, count(*) as picks,
               sum(CASE WHEN won THEN 1 ELSE 0 END) as wins,
               round(sum(CASE WHEN won THEN 1 ELSE 0 END)::NUMERIC
                     / count(*) * 100, 1) as win_rate
        FROM match_players
        GROUP BY hero_id, hero_name
        ORDER BY picks DESC, win_rate DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_top_heroes_winrate(con: Connection, limit: int = 5) -> list[dict]:
    """Highest win rate heroes (min 2 games)."""
    rows = con.execute(
        """
        SELECT hero_id, hero_name, count(*) as picks,
               sum(CASE WHEN won THEN 1 ELSE 0 END) as wins,
               round(sum(CASE WHEN won THEN 1 ELSE 0 END)::NUMERIC
                     / count(*) * 100, 1) as win_rate
        FROM match_players
        GROUP BY hero_id, hero_name
        HAVING count(*) >= 2
        ORDER BY win_rate DESC, picks DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_top_heroes_banned(con: Connection, limit: int = 5) -> list[dict]:
    """Most banned heroes in the cafe."""
    total_matches = con.execute("SELECT count(*) FROM matches").fetchone()[0]
    rows = con.execute(
        """
        SELECT hero_id, hero_name, count(*) as bans
        FROM match_bans
        GROUP BY hero_id, hero_name
        ORDER BY bans DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    results = []
    for r in rows:
        d = dict(zip(cols, r))
        d["ban_rate"] = round(d["bans"] / max(total_matches, 1) * 100, 1)
        results.append(d)
    return results
