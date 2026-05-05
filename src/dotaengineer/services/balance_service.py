"""Role-aware auto-balance team generator for fair 5v5 inhouse games.

Considers both MMR and per-role performance scores when splitting
10 players into two balanced teams of 5 with role assignments.
"""

from __future__ import annotations

from itertools import combinations, permutations

from pydantic import BaseModel

from dotaengineer.db import Connection
from dotaengineer.elo import expected_score

ROLES = ["pos1", "pos2", "pos3", "pos4", "pos5"]
ROLE_LABELS = {
    "pos1": "Carry",
    "pos2": "Mid",
    "pos3": "Offlane",
    "pos4": "Support",
    "pos5": "Hard Supp",
}


class BalancedTeam(BaseModel):
    players: list[dict]  # [{id, display_name, mmr, role, role_label, role_score}]
    total_mmr: int
    avg_mmr: float
    total_role_score: float


class BalanceResult(BaseModel):
    team_a: BalancedTeam
    team_b: BalancedTeam
    mmr_difference: int
    role_score_difference: float
    predicted_win_a: float
    predicted_win_b: float


def _build_role_matrix(
    player_ids: list[int], con: Connection
) -> tuple[list[dict], dict[int, dict[str, float]]]:
    """Fetch player data and build role score matrix.

    Returns:
        players: list of {id, display_name, mmr}
        role_matrix: {player_id: {pos1: score, pos2: score, ...}}
    """
    placeholders = ", ".join(["?"] * len(player_ids))
    rows = con.execute(
        f"SELECT id, display_name, mmr FROM players WHERE id IN ({placeholders})",
        player_ids,
    ).fetchall()
    players = [{"id": r[0], "display_name": r[1], "mmr": r[2]} for r in rows]

    # Fetch role performance in a single query — avg stats per player per role
    role_matrix: dict[int, dict[str, float]] = {
        p["id"]: {r: 0.0 for r in ROLES} for p in players
    }
    role_rows = con.execute(
        f"""
        SELECT mp.player_id, mp.role, count(*) as games,
               avg((mp.kills + mp.assists)::NUMERIC
                   / GREATEST(mp.deaths, 1)) as kda,
               avg(mp.gpm) as gpm,
               avg(mp.hero_damage) as dmg,
               avg(mp.hero_healing) as heal,
               avg(mp.obs_wards_placed + mp.sentry_wards_placed) as wards,
               avg(mp.assists) as ast
        FROM match_players mp
        WHERE mp.player_id IN ({placeholders})
          AND mp.role IS NOT NULL
        GROUP BY mp.player_id, mp.role
        """,
        player_ids,
    ).fetchall()

    # Find group maxes for normalization
    max_vals = {"kda": 1, "gpm": 1, "dmg": 1, "heal": 1, "wards": 1, "ast": 1}
    for row in role_rows:
        _, _, _, kda, gpm, dmg, heal, wards, ast = row
        max_vals["kda"] = max(max_vals["kda"], float(kda or 0))
        max_vals["gpm"] = max(max_vals["gpm"], float(gpm or 0))
        max_vals["dmg"] = max(max_vals["dmg"], float(dmg or 0))
        max_vals["heal"] = max(max_vals["heal"], float(heal or 0))
        max_vals["wards"] = max(max_vals["wards"], float(wards or 0))
        max_vals["ast"] = max(max_vals["ast"], float(ast or 0))

    # Score each player-role: weighted by role type, normalized 0-100
    for row in role_rows:
        pid, role, games, kda, gpm, dmg, heal, wards, ast = row
        if pid not in role_matrix or role not in ROLES:
            continue
        kda_n = float(kda or 0) / max_vals["kda"] * 100
        gpm_n = float(gpm or 0) / max_vals["gpm"] * 100
        dmg_n = float(dmg or 0) / max_vals["dmg"] * 100
        heal_n = float(heal or 0) / max(max_vals["heal"], 1) * 100
        wards_n = float(wards or 0) / max(max_vals["wards"], 1) * 100
        ast_n = float(ast or 0) / max(max_vals["ast"], 1) * 100

        if role in ("pos1", "pos2"):
            score = gpm_n * 0.35 + dmg_n * 0.30 + kda_n * 0.35
        elif role == "pos3":
            score = kda_n * 0.25 + dmg_n * 0.25 + ast_n * 0.30 + gpm_n * 0.20
        else:
            score = wards_n * 0.25 + ast_n * 0.30 + heal_n * 0.15 + kda_n * 0.30
        role_matrix[pid][role] = round(min(score, 100), 1)

    return players, role_matrix


def _optimal_role_assignment(
    team: list[dict], role_matrix: dict[int, dict[str, float]]
) -> tuple[float, list[tuple[dict, str, float]]]:
    """Find the role assignment that maximizes total role score for a team.

    Brute-forces all 5! = 120 permutations (fast for 5 players).

    Returns:
        best_total: total role score
        assignments: [(player_dict, role, role_score), ...]
    """
    best_total = -1.0
    best_assign: list[tuple[dict, str, float]] = []

    for perm in permutations(ROLES):
        total = 0.0
        assign = []
        for player, role in zip(team, perm):
            score = role_matrix.get(player["id"], {}).get(role, 0.0)
            total += score
            assign.append((player, role, score))
        if total > best_total:
            best_total = total
            best_assign = assign

    return best_total, best_assign


def _build_team(
    assignments: list[tuple[dict, str, float]], total_role_score: float
) -> BalancedTeam:
    """Build a BalancedTeam from role assignments."""
    players = []
    for player, role, score in assignments:
        players.append({
            "id": player["id"],
            "display_name": player["display_name"],
            "mmr": player["mmr"],
            "role": role,
            "role_label": ROLE_LABELS.get(role, role),
            "role_score": round(score, 1),
        })
    # Sort by role order (pos1 first)
    role_order = {r: i for i, r in enumerate(ROLES)}
    players.sort(key=lambda p: role_order.get(p["role"], 9))

    total_mmr = sum(p["mmr"] for p in players)
    avg_mmr = total_mmr / len(players) if players else 0

    return BalancedTeam(
        players=players,
        total_mmr=total_mmr,
        avg_mmr=round(avg_mmr),
        total_role_score=round(total_role_score, 1),
    )


def balance_teams(
    player_ids: list[int], con: Connection, top_n: int = 5
) -> list[BalanceResult]:
    """Find the top N fairest team splits for exactly 10 players.

    Considers both MMR balance and role performance.
    For each of C(10,5) = 252 team splits, finds optimal role
    assignment per team (5! = 120 permutations each), then ranks
    by combined MMR + role score difference.

    Returns list of BalanceResult sorted by quality (best first).
    """
    if len(player_ids) != 10:
        return []

    players, role_matrix = _build_role_matrix(player_ids, con)
    if len(players) != 10:
        return []

    # Find max possible values for normalization
    all_mmr = [p["mmr"] for p in players]
    max_mmr_diff = max(all_mmr) * 5 - min(all_mmr) * 5  # theoretical max
    max_mmr_diff = max(max_mmr_diff, 1)

    # All role scores for normalization
    all_scores = [
        s for pid_scores in role_matrix.values() for s in pid_scores.values()
    ]
    max_role_diff = max(all_scores) * 5 if all_scores else 1
    max_role_diff = max(max_role_diff, 1)

    # Evaluate all C(10,5) = 252 splits
    configs: list[tuple[float, BalanceResult]] = []

    for combo in combinations(range(10), 5):
        team_a_players = [players[i] for i in combo]
        b_indices = set(range(10)) - set(combo)
        team_b_players = [players[i] for i in b_indices]

        # Optimal role assignment per team
        score_a, assign_a = _optimal_role_assignment(
            team_a_players, role_matrix
        )
        score_b, assign_b = _optimal_role_assignment(
            team_b_players, role_matrix
        )

        team_a = _build_team(assign_a, score_a)
        team_b = _build_team(assign_b, score_b)

        mmr_diff = abs(team_a.total_mmr - team_b.total_mmr)
        role_diff = abs(score_a - score_b)

        # Normalized combined score (lower = better)
        mmr_norm = mmr_diff / max_mmr_diff
        role_norm = role_diff / max_role_diff
        combined = mmr_norm + role_norm

        win_a = expected_score(team_a.avg_mmr, team_b.avg_mmr)

        result = BalanceResult(
            team_a=team_a,
            team_b=team_b,
            mmr_difference=mmr_diff,
            role_score_difference=round(role_diff, 1),
            predicted_win_a=round(win_a * 100, 1),
            predicted_win_b=round((1 - win_a) * 100, 1),
        )
        configs.append((combined, result))

    # Sort by combined score (best first), take top N
    configs.sort(key=lambda x: x[0])
    return [r for _, r in configs[:top_n]]
