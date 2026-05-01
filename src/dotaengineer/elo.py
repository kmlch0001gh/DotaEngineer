"""Team-based ELO rating system for cafe matches."""

from __future__ import annotations

import structlog

from dotaengineer.config import settings
from dotaengineer.db import Connection

log = structlog.get_logger()


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected win probability for team A given team ratings."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def k_factor(games_played: int) -> int:
    """Higher K during calibration (first N games) for faster convergence."""
    if games_played < settings.elo_calibration_games:
        return settings.elo_calibration_k
    return settings.elo_k_factor


def calculate_mmr_changes(match_id: int, con: Connection) -> list[dict]:
    """Calculate MMR changes for a match where players have claimed slots.

    Returns list of dicts: [{player_id, mmr_before, mmr_after, mmr_change}, ...]
    Only includes slots that have a claimed player_id.
    """
    rows = con.execute(
        """
        SELECT mp.player_id, mp.won, p.mmr, p.games_played, mp.team
        FROM match_players mp
        JOIN players p ON p.id = mp.player_id
        WHERE mp.match_id = ? AND mp.player_id IS NOT NULL
        ORDER BY mp.slot
        """,
        [match_id],
    ).fetchall()

    if not rows:
        return []

    radiant = [(r[0], r[2], r[3]) for r in rows if r[4] == "radiant"]
    dire = [(r[0], r[2], r[3]) for r in rows if r[4] == "dire"]

    if not radiant or not dire:
        return []

    avg_radiant = sum(mmr for _, mmr, _ in radiant) / len(radiant)
    avg_dire = sum(mmr for _, mmr, _ in dire) / len(dire)

    e_radiant = expected_score(avg_radiant, avg_dire)
    e_dire = 1.0 - e_radiant

    radiant_won = any(r[1] for r in rows if r[4] == "radiant")

    changes = []
    for player_id, mmr, games in radiant:
        k = k_factor(games)
        actual = 1.0 if radiant_won else 0.0
        delta = round(k * (actual - e_radiant))
        new_mmr = max(settings.elo_floor, mmr + delta)
        changes.append(
            {
                "player_id": player_id,
                "mmr_before": mmr,
                "mmr_after": new_mmr,
                "mmr_change": new_mmr - mmr,
            }
        )

    for player_id, mmr, games in dire:
        k = k_factor(games)
        actual = 1.0 if not radiant_won else 0.0
        delta = round(k * (actual - e_dire))
        new_mmr = max(settings.elo_floor, mmr + delta)
        changes.append(
            {
                "player_id": player_id,
                "mmr_before": mmr,
                "mmr_after": new_mmr,
                "mmr_change": new_mmr - mmr,
            }
        )

    return changes


def apply_mmr_changes(
    match_id: int,
    changes: list[dict],
    con: Connection,
) -> None:
    """Write MMR changes to mmr_history and update player MMR/stats."""
    for c in changes:
        # Check if already applied
        existing = con.execute(
            "SELECT 1 FROM mmr_history WHERE player_id = ? AND match_id = ?",
            [c["player_id"], match_id],
        ).fetchone()
        if existing:
            continue

        con.execute(
            """
            INSERT INTO mmr_history (player_id, match_id, mmr_before, mmr_after, mmr_change)
            VALUES (?, ?, ?, ?, ?)
            """,
            [c["player_id"], match_id, c["mmr_before"], c["mmr_after"], c["mmr_change"]],
        )
        con.execute(
            "UPDATE players SET mmr = ?, updated_at = current_timestamp WHERE id = ?",
            [c["mmr_after"], c["player_id"]],
        )

    log.info("mmr_changes_applied", match_id=match_id, player_count=len(changes))


def update_player_stats(match_id: int, con: Connection) -> None:
    """Update games_played, wins, losses for all claimed players in a match."""
    claimed = con.execute(
        """
        SELECT mp.player_id, mp.won
        FROM match_players mp
        WHERE mp.match_id = ? AND mp.player_id IS NOT NULL
        """,
        [match_id],
    ).fetchall()

    for player_id, won in claimed:
        if won:
            con.execute(
                """UPDATE players SET
                    games_played = games_played + 1,
                    wins = wins + 1,
                    updated_at = current_timestamp
                WHERE id = ?""",
                [player_id],
            )
        else:
            con.execute(
                """UPDATE players SET
                    games_played = games_played + 1,
                    losses = losses + 1,
                    updated_at = current_timestamp
                WHERE id = ?""",
                [player_id],
            )


def process_match_elo(match_id: int, con: Connection) -> list[dict]:
    """Full ELO processing for a match: calculate, apply, update stats.

    Returns the list of MMR changes applied.
    """
    changes = calculate_mmr_changes(match_id, con)
    if changes:
        apply_mmr_changes(match_id, changes, con)
        update_player_stats(match_id, con)
    return changes


def recalculate_all(con: Connection) -> int:
    """Wipe all MMR data and recalculate from scratch in chronological order.

    Returns number of matches processed.
    """
    # Reset all players to starting MMR
    con.execute(
        """UPDATE players SET
            mmr = ?, games_played = 0, wins = 0, losses = 0,
            updated_at = current_timestamp""",
        [settings.elo_starting_mmr],
    )
    con.execute("DELETE FROM mmr_history")

    # Replay all matches in order
    match_ids = con.execute("SELECT id FROM matches ORDER BY played_at ASC").fetchall()

    count = 0
    for (match_id,) in match_ids:
        changes = calculate_mmr_changes(match_id, con)
        if changes:
            apply_mmr_changes(match_id, changes, con)
            update_player_stats(match_id, con)
            count += 1

    log.info("elo_recalculated", matches_processed=count)
    return count
