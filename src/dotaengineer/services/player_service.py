"""Player registration, retrieval, and stats."""

from __future__ import annotations

import structlog

from dotaengineer.db import Connection
from dotaengineer.models.player import (
    HeroBreakdown,
    Player,
    PlayerAchievements,
    PlayerCreate,
    PlayerStats,
)

log = structlog.get_logger()


def create_player(data: PlayerCreate, con: Connection) -> int:
    """Register a new player. Returns the new player ID."""
    from dotaengineer.models.player import CATEGORIES

    starting_mmr = CATEGORIES.get(data.category, CATEGORIES["konoha"])["starting_mmr"]
    row = con.execute(
        """
        INSERT INTO players (username, display_name, mmr, category)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        [data.username, data.display_name, starting_mmr, data.category],
    ).fetchone()
    player_id = row[0]
    log.info("player_created", player_id=player_id, username=data.username)
    return player_id


def get_player(player_id: int, con: Connection) -> Player | None:
    row = con.execute("SELECT * FROM players WHERE id = ?", [player_id]).fetchone()
    if not row:
        return None
    cols = [desc[0] for desc in con.description]
    return Player(**dict(zip(cols, row)))


def update_player(player_id: int, display_name: str, username: str, con: Connection) -> bool:
    """Update a player's display name and username."""
    con.execute(
        """UPDATE players SET display_name = ?, username = ?,
           updated_at = current_timestamp WHERE id = ?""",
        [display_name, username, player_id],
    )
    return True


def get_player_by_username(username: str, con: Connection) -> Player | None:
    row = con.execute("SELECT * FROM players WHERE username = ?", [username]).fetchone()
    if not row:
        return None
    cols = [desc[0] for desc in con.description]
    return Player(**dict(zip(cols, row)))


def list_players(con: Connection, active_only: bool = True) -> list[Player]:
    query = "SELECT * FROM players"
    if active_only:
        query += " WHERE is_active = true"
    query += " ORDER BY display_name"
    rows = con.execute(query).fetchall()
    cols = [desc[0] for desc in con.description]
    return [Player(**dict(zip(cols, r))) for r in rows]


def get_player_hero_breakdown(player_id: int, con: Connection) -> list[HeroBreakdown]:
    rows = con.execute(
        """
        SELECT
            hero_id,
            hero_name,
            count(*) as games,
            sum(CASE WHEN won THEN 1 ELSE 0 END) as wins,
            sum(CASE WHEN NOT won THEN 1 ELSE 0 END) as losses,
            round(avg(kills), 1) as avg_kills,
            round(avg(deaths), 1) as avg_deaths,
            round(avg(assists), 1) as avg_assists,
            round(avg(gpm), 0) as avg_gpm
        FROM match_players
        WHERE player_id = ?
        GROUP BY hero_id, hero_name
        ORDER BY games DESC
        """,
        [player_id],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    return [HeroBreakdown(**dict(zip(cols, r))) for r in rows]


def get_player_recent_matches(player_id: int, limit: int, con: Connection) -> list[dict]:
    rows = con.execute(
        """
        SELECT
            m.id as match_id,
            m.played_at,
            m.duration_seconds,
            m.radiant_win,
            mp.hero_name,
            mp.hero_id,
            mp.team,
            mp.kills,
            mp.deaths,
            mp.assists,
            mp.won
        FROM match_players mp
        JOIN matches m ON m.id = mp.match_id
        WHERE mp.player_id = ?
        ORDER BY m.played_at DESC
        LIMIT ?
        """,
        [player_id, limit],
    ).fetchall()
    cols = [desc[0] for desc in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_player_stats(player_id: int, con: Connection) -> PlayerStats | None:
    player = get_player(player_id, con)
    if not player:
        return None

    # Aggregate stats
    agg = con.execute(
        """
        SELECT
            round(avg(kills), 1) as avg_kills,
            round(avg(deaths), 1) as avg_deaths,
            round(avg(assists), 1) as avg_assists,
            round(avg(gpm), 0) as avg_gpm
        FROM match_players
        WHERE player_id = ?
        """,
        [player_id],
    ).fetchone()

    avg_kills = agg[0] or 0.0
    avg_deaths = agg[1] or 0.0
    avg_assists = agg[2] or 0.0
    avg_gpm = agg[3] or 0.0

    # Favorite hero
    fav = con.execute(
        """
        SELECT hero_name FROM match_players
        WHERE player_id = ?
        GROUP BY hero_name
        ORDER BY count(*) DESC
        LIMIT 1
        """,
        [player_id],
    ).fetchone()
    favorite_hero = fav[0] if fav else None

    # Current streak
    recent = con.execute(
        """
        SELECT mp.won
        FROM match_players mp
        JOIN matches m ON m.id = mp.match_id
        WHERE mp.player_id = ?
        ORDER BY m.played_at DESC
        """,
        [player_id],
    ).fetchall()

    current_streak = 0
    best_win_streak = 0
    if recent:
        # Current streak
        first_result = recent[0][0]
        for r in recent:
            if r[0] == first_result:
                current_streak += 1
            else:
                break
        if not first_result:
            current_streak = -current_streak

        # Best win streak
        streak = 0
        for r in recent:
            if r[0]:
                streak += 1
                best_win_streak = max(best_win_streak, streak)
            else:
                streak = 0

    hero_breakdown = get_player_hero_breakdown(player_id, con)

    # Achievements totals
    ach_row = con.execute(
        """
        SELECT
            coalesce(sum(double_kills), 0),
            coalesce(sum(triple_kills), 0),
            coalesce(sum(ultra_kills), 0),
            coalesce(sum(rampage), 0),
            coalesce(sum(killing_sprees), 0),
            coalesce(sum(dominating), 0),
            coalesce(sum(mega_kills), 0),
            coalesce(sum(unstoppable), 0),
            coalesce(sum(wicked_sick), 0),
            coalesce(sum(monster_kill), 0),
            coalesce(sum(godlike), 0),
            coalesce(sum(beyond_godlike), 0),
            coalesce(sum(courier_kills), 0),
            coalesce(sum(roshan_kills), 0),
            coalesce(sum(tormentor_kills), 0)
        FROM match_players
        WHERE player_id = ?
        """,
        [player_id],
    ).fetchone()
    achievements = PlayerAchievements(
        double_kills=ach_row[0],
        triple_kills=ach_row[1],
        ultra_kills=ach_row[2],
        rampage=ach_row[3],
        killing_sprees=ach_row[4],
        dominating=ach_row[5],
        mega_kills=ach_row[6],
        unstoppable=ach_row[7],
        wicked_sick=ach_row[8],
        monster_kill=ach_row[9],
        godlike=ach_row[10],
        beyond_godlike=ach_row[11],
        courier_kills=ach_row[12],
        roshan_kills=ach_row[13],
        tormentor_kills=ach_row[14],
    )

    return PlayerStats(
        player=player,
        avg_kills=avg_kills,
        avg_deaths=avg_deaths,
        avg_assists=avg_assists,
        avg_gpm=avg_gpm,
        favorite_hero=favorite_hero,
        current_streak=current_streak,
        best_win_streak=best_win_streak,
        hero_breakdown=hero_breakdown,
        achievements=achievements,
    )
