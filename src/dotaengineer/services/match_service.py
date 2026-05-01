"""Match creation, retrieval, and claiming logic."""

from __future__ import annotations

import json

import structlog

from dotaengineer.db import Connection
from dotaengineer.elo import process_match_elo
from dotaengineer.models.hero import get_hero_name
from dotaengineer.models.match import CafeMatch, MatchCreate, MatchPlayer

log = structlog.get_logger()


def create_match(data: MatchCreate, con: Connection) -> int:
    """Insert a match and its player slots. Returns the new match ID."""
    row = con.execute(
        """
        INSERT INTO matches (played_at, duration_seconds, radiant_win, game_mode,
                             radiant_score, dire_score, source, notes, replay_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [
            data.played_at,
            data.duration_seconds,
            data.radiant_win,
            data.game_mode,
            data.radiant_score,
            data.dire_score,
            data.source,
            data.notes,
            data.replay_file,
        ],
    ).fetchone()
    match_id = row[0]

    for p in data.players:
        hero_name = get_hero_name(p.hero_id)
        won = (p.team == "radiant") == data.radiant_win
        items_json = json.dumps(p.items)
        con.execute(
            """
            INSERT INTO match_players (match_id, slot, hero_id, hero_name, team,
                                       kills, deaths, assists, last_hits, denies,
                                       gpm, xpm, net_worth, hero_damage, tower_damage,
                                       hero_healing, level, items_json, won)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                match_id,
                p.slot,
                p.hero_id,
                hero_name,
                p.team,
                p.kills,
                p.deaths,
                p.assists,
                p.last_hits,
                p.denies,
                p.gpm,
                p.xpm,
                p.net_worth,
                p.hero_damage,
                p.tower_damage,
                p.hero_healing,
                p.level,
                items_json,
                won,
            ],
        )

    # Insert bans
    for i, hero_id in enumerate(data.bans):
        if hero_id <= 0:
            continue
        ban_hero_name = get_hero_name(hero_id)
        con.execute(
            """INSERT INTO match_bans (match_id, hero_id, hero_name, ban_order)
               VALUES (?, ?, ?, ?)""",
            [match_id, hero_id, ban_hero_name, i],
        )

    log.info("match_created", match_id=match_id, source=data.source, bans=len(data.bans))
    return match_id


def backfill_bans(match_id: int, bans: list[int], con: Connection) -> int:
    """Add bans to an existing match without modifying anything else.

    Skips if the match already has bans. Returns number of bans inserted.
    """
    existing = con.execute(
        "SELECT count(*) FROM match_bans WHERE match_id = ?", [match_id]
    ).fetchone()[0]
    if existing > 0:
        return 0

    count = 0
    for i, hero_id in enumerate(bans):
        if hero_id <= 0:
            continue
        ban_hero_name = get_hero_name(hero_id)
        con.execute(
            """INSERT INTO match_bans (match_id, hero_id, hero_name, ban_order)
               VALUES (?, ?, ?, ?)""",
            [match_id, hero_id, ban_hero_name, i],
        )
        count += 1
    return count


def get_match(match_id: int, con: Connection) -> CafeMatch | None:
    """Fetch a match with all player slots."""
    row = con.execute("SELECT * FROM matches WHERE id = ?", [match_id]).fetchone()
    if not row:
        return None

    cols = [desc[0] for desc in con.description]
    match_dict = dict(zip(cols, row))

    player_rows = con.execute(
        """
        SELECT mp.*, p.display_name as player_name
        FROM match_players mp
        LEFT JOIN players p ON p.id = mp.player_id
        WHERE mp.match_id = ?
        ORDER BY mp.slot
        """,
        [match_id],
    ).fetchall()
    player_cols = [desc[0] for desc in con.description]

    players = []
    for pr in player_rows:
        pd = dict(zip(player_cols, pr))
        players.append(MatchPlayer(**pd))

    return CafeMatch(**match_dict, players=players)


def list_matches(page: int, per_page: int, con: Connection) -> tuple[list[CafeMatch], int]:
    """Paginated match list. Returns (matches, total_count)."""
    total = con.execute("SELECT count(*) FROM matches").fetchone()[0]
    offset = (page - 1) * per_page

    rows = con.execute(
        "SELECT id FROM matches ORDER BY played_at DESC LIMIT ? OFFSET ?",
        [per_page, offset],
    ).fetchall()

    matches = []
    for (mid,) in rows:
        m = get_match(mid, con)
        if m:
            matches.append(m)

    return matches, total


def claim_slot(
    match_id: int,
    slot: int,
    player_id: int,
    con: Connection,
) -> bool:
    """Assign a player to a match slot. Returns True if successful."""
    # Check slot exists and is unclaimed
    existing = con.execute(
        "SELECT player_id FROM match_players WHERE match_id = ? AND slot = ?",
        [match_id, slot],
    ).fetchone()

    if not existing:
        return False
    if existing[0] is not None:
        return False  # already claimed

    # Check player isn't already claiming another slot in this match
    already = con.execute(
        "SELECT slot FROM match_players WHERE match_id = ? AND player_id = ?",
        [match_id, player_id],
    ).fetchone()
    if already:
        return False

    con.execute(
        "UPDATE match_players SET player_id = ? WHERE match_id = ? AND slot = ?",
        [player_id, match_id, slot],
    )

    # Check if all slots are now claimed → trigger ELO
    unclaimed = con.execute(
        "SELECT count(*) FROM match_players WHERE match_id = ? AND player_id IS NULL",
        [match_id],
    ).fetchone()[0]

    if unclaimed == 0:
        # Check ELO hasn't been processed yet
        elo_exists = con.execute(
            "SELECT 1 FROM mmr_history WHERE match_id = ? LIMIT 1",
            [match_id],
        ).fetchone()
        if not elo_exists:
            process_match_elo(match_id, con)

    log.info("slot_claimed", match_id=match_id, slot=slot, player_id=player_id)
    return True


def unclaim_slot(
    match_id: int,
    slot: int,
    con: Connection,
) -> bool:
    """Remove a player from a match slot. Returns True if successful."""
    existing = con.execute(
        "SELECT player_id FROM match_players WHERE match_id = ? AND slot = ?",
        [match_id, slot],
    ).fetchone()

    if not existing or existing[0] is None:
        return False

    con.execute(
        "UPDATE match_players SET player_id = NULL WHERE match_id = ? AND slot = ?",
        [match_id, slot],
    )

    log.info("slot_unclaimed", match_id=match_id, slot=slot)
    return True


def delete_match(match_id: int, con: Connection) -> bool:
    """Delete a match and all associated data."""
    existing = con.execute("SELECT 1 FROM matches WHERE id = ?", [match_id]).fetchone()
    if not existing:
        return False

    con.execute("DELETE FROM mmr_history WHERE match_id = ?", [match_id])
    con.execute("DELETE FROM match_players WHERE match_id = ?", [match_id])
    con.execute("DELETE FROM matches WHERE id = ?", [match_id])
    log.info("match_deleted", match_id=match_id)
    return True
