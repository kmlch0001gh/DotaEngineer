"""Role-aware auto-balance team generator for fair 5v5 inhouse games.

Each player selects one or more roles they can play. The algorithm
uses the real role_service scoring to find team splits where each
team has all 5 roles covered, maximizing balance in MMR + role score.
"""

from __future__ import annotations

from itertools import combinations

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
    players: list[dict]
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


def _build_team(players_with_roles: list[dict]) -> BalancedTeam:
    role_order = {r: i for i, r in enumerate(ROLES)}
    players_with_roles.sort(key=lambda p: role_order.get(p["role"], 9))
    total_mmr = sum(p["mmr"] for p in players_with_roles)
    avg_mmr = total_mmr / len(players_with_roles) if players_with_roles else 0
    total_role = sum(p["role_score"] for p in players_with_roles)
    return BalancedTeam(
        players=players_with_roles,
        total_mmr=total_mmr,
        avg_mmr=round(avg_mmr),
        total_role_score=round(total_role, 1),
    )


def _best_role_assignment(
    team: list[dict],
    allowed_roles: dict[int, list[str]],
    role_scores: dict[int, dict[str, float]],
) -> tuple[float, list[dict]] | None:
    """Find optimal role assignment for a team of 5 via backtracking.

    Each player can only be assigned a role from their allowed_roles.
    Each role must be assigned exactly once. Returns (total_score, players_with_roles)
    or None if no valid assignment exists.
    """
    best = [None, -1.0]  # [assignment, score]

    def backtrack(idx: int, used_roles: set, current: list, score: float):
        if idx == 5:
            if score > best[1]:
                best[0] = list(current)
                best[1] = score
            return
        player = team[idx]
        pid = player["id"]
        for role in allowed_roles.get(pid, []):
            if role in used_roles:
                continue
            rs = role_scores.get(pid, {}).get(role, 0.0)
            current.append({
                **player,
                "role": role,
                "role_label": ROLE_LABELS.get(role, role),
                "role_score": round(rs, 1),
            })
            used_roles.add(role)
            backtrack(idx + 1, used_roles, current, score + rs)
            used_roles.discard(role)
            current.pop()

    backtrack(0, set(), [], 0.0)
    if best[0] is None:
        return None
    return best[1], best[0]


def balance_teams(
    player_roles: dict[int, list[str]],
    con: Connection,
    top_n: int = 5,
) -> list[BalanceResult]:
    """Find top N fairest team splits for exactly 10 players.

    Args:
        player_roles: {player_id: [role1, role2, ...]} — allowed roles per player
        con: database connection
        top_n: number of results to return
    """
    if len(player_roles) != 10:
        return []

    player_ids = list(player_roles.keys())

    placeholders = ", ".join(["?"] * len(player_ids))
    rows = con.execute(
        f"SELECT id, display_name, mmr FROM players WHERE id IN ({placeholders})",
        player_ids,
    ).fetchall()
    players_map = {r[0]: {"id": r[0], "display_name": r[1], "mmr": r[2]} for r in rows}
    if len(players_map) != 10:
        return []

    from dotaengineer.services.role_service import get_role_scores_batch

    role_scores = get_role_scores_batch(player_ids, con)

    players = [players_map[pid] for pid in player_ids]

    # Normalization
    all_mmr = [p["mmr"] for p in players]
    max_mmr_diff = max(max(all_mmr) * 5 - min(all_mmr) * 5, 1)
    all_rs = [
        role_scores.get(pid, {}).get(r, 0.0)
        for pid in player_ids
        for r in player_roles[pid]
    ]
    max_role_diff = max(max(all_rs) * 5 if all_rs else 1, 1)

    configs: list[tuple[float, BalanceResult]] = []

    for combo in combinations(range(10), 5):
        # Skip mirror: only consider combos where player 0 is in team_a
        if 0 not in combo:
            continue
        team_a_raw = [players[i] for i in combo]
        team_b_raw = [players[i] for i in set(range(10)) - set(combo)]

        result_a = _best_role_assignment(team_a_raw, player_roles, role_scores)
        if result_a is None:
            continue
        result_b = _best_role_assignment(team_b_raw, player_roles, role_scores)
        if result_b is None:
            continue

        score_a, assigned_a = result_a
        score_b, assigned_b = result_b

        team_a = _build_team(assigned_a)
        team_b = _build_team(assigned_b)

        mmr_diff = abs(team_a.total_mmr - team_b.total_mmr)
        role_diff = abs(score_a - score_b)

        combined = mmr_diff / max_mmr_diff + role_diff / max_role_diff

        win_a = expected_score(team_a.avg_mmr, team_b.avg_mmr)

        configs.append((combined, BalanceResult(
            team_a=team_a,
            team_b=team_b,
            mmr_difference=mmr_diff,
            role_score_difference=round(role_diff, 1),
            predicted_win_a=round(win_a * 100, 1),
            predicted_win_b=round((1 - win_a) * 100, 1),
        )))

    configs.sort(key=lambda x: x[0])
    return [r for _, r in configs[:top_n]]
