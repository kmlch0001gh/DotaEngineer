"""Role-based performance scoring for the cafe.

Calculates a 0-100 score per player per match based on role-specific
weighted metrics. Metrics are normalized per minute of game time,
then scaled against the best value in the cafe's history.
"""

from __future__ import annotations

from dotaengineer.db import Connection

# Role formulas: {metric_name: weight}
# Metrics ending in _inv are inverted (lower = better)
ROLE_WEIGHTS = {
    "pos1": {  # Carry
        "gpm": 0.25,
        "hero_damage_pm": 0.20,
        "last_hits_pm": 0.15,
        "net_worth": 0.15,
        "kda_ratio": 0.15,
        "tower_damage": 0.10,
    },
    "pos2": {  # Mid
        "hero_damage_pm": 0.25,
        "xpm": 0.20,
        "gpm": 0.20,
        "kda_ratio": 0.20,
        "tower_damage": 0.10,
        "denies_pm": 0.05,
    },
    "pos3": {  # Offlane
        "damage_taken_pm": 0.20,
        "stun_duration": 0.20,
        "assists_pm": 0.20,
        "hero_damage_pm": 0.15,
        "deaths_inv": 0.15,
        "tower_damage": 0.10,
    },
    "pos4": {  # Support (unified with pos5)
        "wards_placed": 0.18,
        "assists_pm": 0.18,
        "wards_destroyed": 0.15,
        "hero_healing_pm": 0.12,
        "gold_spent_support": 0.12,
        "stun_duration": 0.10,
        "hero_damage_pm": 0.08,
        "deaths_inv": 0.07,
    },
    "pos5": {  # Support (same as pos4)
        "wards_placed": 0.18,
        "assists_pm": 0.18,
        "wards_destroyed": 0.15,
        "hero_healing_pm": 0.12,
        "gold_spent_support": 0.12,
        "stun_duration": 0.10,
        "hero_damage_pm": 0.08,
        "deaths_inv": 0.07,
    },
}


def _extract_metrics(row: dict, duration_mins: float) -> dict[str, float]:
    """Extract normalized metrics from a match_players row."""
    dm = max(duration_mins, 1)
    deaths = max(row.get("deaths", 0), 1)

    return {
        "gpm": row.get("gpm", 0),
        "xpm": row.get("xpm", 0),
        "hero_damage_pm": row.get("hero_damage", 0) / dm,
        "tower_damage": row.get("tower_damage", 0),
        "last_hits_pm": row.get("last_hits", 0) / dm,
        "denies_pm": row.get("denies", 0) / dm,
        "net_worth": row.get("net_worth", 0),
        "kda_ratio": (row.get("kills", 0) + row.get("assists", 0)) / deaths,
        "assists_pm": row.get("assists", 0) / dm,
        "deaths_inv": 1.0 / deaths,  # lower deaths = higher score
        "damage_taken_pm": row.get("damage_taken", 0) / dm,
        "stun_duration": row.get("stun_duration", 0),
        "wards_placed": row.get("obs_wards_placed", 0) + row.get("sentry_wards_placed", 0),
        "wards_destroyed": row.get("wards_destroyed", 0),
        "hero_healing_pm": row.get("hero_healing", 0) / dm,
        "gold_spent_support": row.get("gold_spent_support", 0),
    }


def _get_max_metrics(role: str, con: Connection) -> dict[str, float]:
    """Get the best (max) value for each metric across all matches for a role."""
    rows = con.execute(
        """
        SELECT mp.*, m.duration_seconds
        FROM match_players mp
        JOIN matches m ON m.id = mp.match_id
        WHERE mp.role = ?
        """,
        [role],
    ).fetchall()

    if not rows:
        return {}

    cols = [desc[0] for desc in con.description]
    maxes: dict[str, float] = {}

    for r in rows:
        d = dict(zip(cols, r))
        dm = max((d.get("duration_seconds") or 1) / 60, 1)
        metrics = _extract_metrics(d, dm)
        for k, v in metrics.items():
            if k not in maxes or v > maxes[k]:
                maxes[k] = v

    return maxes


def calculate_role_score(
    player_stats: dict, duration_mins: float, role: str, con: Connection
) -> float:
    """Calculate a 0-100 role performance score for a single match.

    Args:
        player_stats: dict with match_players columns
        duration_mins: game duration in minutes
        role: one of pos1-pos5
        con: database connection

    Returns:
        Score from 0 to 100
    """
    weights = ROLE_WEIGHTS.get(role)
    if not weights:
        return 0

    metrics = _extract_metrics(player_stats, duration_mins)
    maxes = _get_max_metrics(role, con)

    if not maxes:
        return 50  # no historical data, return neutral

    score = 0.0
    for metric, weight in weights.items():
        val = metrics.get(metric, 0)
        best = maxes.get(metric, 1)
        if best <= 0:
            best = 1
        normalized = min(val / best, 1.0) * 100
        score += normalized * weight

    return round(score, 1)


METRIC_LABELS = {
    "gpm": "GPM",
    "xpm": "XPM",
    "hero_damage_pm": "Hero DMG/min",
    "tower_damage": "Tower DMG",
    "last_hits_pm": "Last Hits/min",
    "denies_pm": "Denies/min",
    "net_worth": "Net Worth",
    "kda_ratio": "KDA Ratio",
    "assists_pm": "Assists/min",
    "deaths_inv": "Supervivencia",
    "damage_taken_pm": "DMG Recibido/min",
    "stun_duration": "Stun (seg)",
    "wards_placed": "Wards Placed",
    "wards_destroyed": "Dewards",
    "hero_healing_pm": "Healing/min",
    "gold_spent_support": "Gold Support",
}


def get_role_score_breakdown(player_id: int, role: str, con: Connection) -> list[dict]:
    """Get detailed breakdown of a player's average role score.

    Returns list of: [{metric, label, weight_pct, avg_value, best_value,
                       normalized, contribution}, ...]
    """
    weights = ROLE_WEIGHTS.get(role)
    if not weights:
        return []

    maxes = _get_max_metrics(role, con)
    if not maxes:
        return []

    # Get all matches for this player in this role
    rows = con.execute(
        """
        SELECT mp.*, m.duration_seconds
        FROM match_players mp
        JOIN matches m ON m.id = mp.match_id
        WHERE mp.player_id = ? AND mp.role = ?
        """,
        [player_id, role],
    ).fetchall()

    if not rows:
        return []

    cols = [desc[0] for desc in con.description]

    # Average metrics across all matches
    avg_metrics: dict[str, float] = {}
    count = 0
    for r in rows:
        d = dict(zip(cols, r))
        dm = max((d.get("duration_seconds") or 1) / 60, 1)
        metrics = _extract_metrics(d, dm)
        for k, v in metrics.items():
            avg_metrics[k] = avg_metrics.get(k, 0) + v
        count += 1

    for k in avg_metrics:
        avg_metrics[k] /= count

    # Build breakdown
    breakdown = []
    for metric, weight in weights.items():
        val = avg_metrics.get(metric, 0)
        best = maxes.get(metric, 1)
        if best <= 0:
            best = 1
        normalized = min(val / best, 1.0) * 100
        contribution = normalized * weight

        breakdown.append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric, metric),
                "weight_pct": round(weight * 100),
                "avg_value": round(val, 1),
                "best_value": round(best, 1),
                "normalized": round(normalized, 1),
                "contribution": round(contribution, 1),
            }
        )

    breakdown.sort(key=lambda x: x["contribution"], reverse=True)
    return breakdown


def get_best_per_role(con: Connection, limit: int = 3) -> dict[str, list[dict]]:
    """Get top players for each role based on average score.

    Returns: {role: [{player_id, display_name, avg_score, games}, ...]}
    """
    result = {}
    for role in ["pos1", "pos2", "pos3", "pos4", "pos5"]:
        rows = con.execute(
            """
            SELECT mp.player_id, p.display_name,
                   count(*) as games
            FROM match_players mp
            JOIN players p ON p.id = mp.player_id
            WHERE mp.role = ? AND mp.player_id IS NOT NULL
            GROUP BY mp.player_id, p.display_name
            HAVING count(*) >= 1
            """,
            [role],
        ).fetchall()

        if not rows:
            result[role] = []
            continue

        # Calculate actual role scores for each player
        cols = [desc[0] for desc in con.description]
        role_players = []

        for r in rows:
            d = dict(zip(cols, r))
            pid = d["player_id"]

            # Get all matches for this player in this role
            match_rows = con.execute(
                """
                SELECT mp.*, m.duration_seconds
                FROM match_players mp
                JOIN matches m ON m.id = mp.match_id
                WHERE mp.player_id = ? AND mp.role = ?
                """,
                [pid, role],
            ).fetchall()
            mcols = [desc[0] for desc in con.description]

            scores = []
            for mr in match_rows:
                md = dict(zip(mcols, mr))
                dm = max((md.get("duration_seconds") or 1) / 60, 1)
                s = calculate_role_score(md, dm, role, con)
                scores.append(s)

            avg_score = sum(scores) / len(scores) if scores else 0

            role_players.append(
                {
                    "player_id": pid,
                    "display_name": d["display_name"],
                    "games": d["games"],
                    "avg_score": round(avg_score, 1),
                }
            )

        role_players.sort(key=lambda x: x["avg_score"], reverse=True)
        result[role] = role_players[:limit]

    return result


def get_player_role_stats(player_id: int, con: Connection) -> list[dict]:
    """Get role performance breakdown for a player.

    Returns: [{role, games, avg_score, best_score}, ...]
    """
    roles = con.execute(
        """
        SELECT role, count(*) as games
        FROM match_players
        WHERE player_id = ? AND role IS NOT NULL
        GROUP BY role
        ORDER BY games DESC
        """,
        [player_id],
    ).fetchall()

    result = []
    for role, games in roles:
        match_rows = con.execute(
            """
            SELECT mp.*, m.duration_seconds
            FROM match_players mp
            JOIN matches m ON m.id = mp.match_id
            WHERE mp.player_id = ? AND mp.role = ?
            """,
            [player_id, role],
        ).fetchall()
        mcols = [desc[0] for desc in con.description]

        scores = []
        for mr in match_rows:
            md = dict(zip(mcols, mr))
            dm = max((md.get("duration_seconds") or 1) / 60, 1)
            s = calculate_role_score(md, dm, role, con)
            scores.append(s)

        avg = sum(scores) / len(scores) if scores else 0
        best = max(scores) if scores else 0

        result.append(
            {
                "role": role,
                "games": games,
                "avg_score": round(avg, 1),
                "best_score": round(best, 1),
            }
        )

    return result
