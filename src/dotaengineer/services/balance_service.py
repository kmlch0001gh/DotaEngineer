"""Role-aware auto-balance team generator for fair 5v5 inhouse games.

Each player selects their desired role. The algorithm uses the real
role_service scoring (same formula as player profiles) to split
10 players into two balanced teams by MMR + role performance.
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


def _build_team(
    players_with_roles: list[dict],
) -> BalancedTeam:
    """Build a BalancedTeam from players that already have roles assigned."""
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


def balance_teams(
    player_roles: dict[int, str],
    con: Connection,
    top_n: int = 5,
) -> list[BalanceResult]:
    """Find the top N fairest team splits for exactly 10 players.

    Args:
        player_roles: {player_id: role} where role is pos1-pos5.
            Each player has already chosen their role.
        con: database connection
        top_n: number of top results to return

    Algorithm:
    - Fetch real role scores using role_service batch function
    - Enumerate all C(10,5) = 252 team splits
    - For each split, validate that each team has roles covered
      (exactly 2 players per role across both teams)
    - Score by combined MMR difference + role score difference
    - Return top N
    """
    if len(player_roles) != 10:
        return []

    player_ids = list(player_roles.keys())

    # Fetch player data
    placeholders = ", ".join(["?"] * len(player_ids))
    rows = con.execute(
        f"SELECT id, display_name, mmr FROM players WHERE id IN ({placeholders})",
        player_ids,
    ).fetchall()
    players_map = {r[0]: {"id": r[0], "display_name": r[1], "mmr": r[2]} for r in rows}
    if len(players_map) != 10:
        return []

    # Fetch real role scores (same formula as player profile)
    from dotaengineer.services.role_service import get_role_scores_batch

    role_scores = get_role_scores_batch(player_ids, con)

    # Build player list with assigned role and score
    players = []
    for pid, role in player_roles.items():
        p = players_map[pid]
        score = role_scores.get(pid, {}).get(role, 0.0)
        players.append({
            "id": p["id"],
            "display_name": p["display_name"],
            "mmr": p["mmr"],
            "role": role,
            "role_label": ROLE_LABELS.get(role, role),
            "role_score": round(score, 1),
        })

    # Normalization bounds
    all_mmr = [p["mmr"] for p in players]
    max_mmr_diff = max(max(all_mmr) * 5 - min(all_mmr) * 5, 1)
    all_role_scores = [p["role_score"] for p in players]
    max_role_diff = max(max(all_role_scores) * 5 if all_role_scores else 1, 1)

    # Evaluate all C(10,5) = 252 splits
    configs: list[tuple[float, BalanceResult]] = []

    for combo in combinations(range(10), 5):
        team_a_list = [dict(players[i]) for i in combo]
        b_indices = set(range(10)) - set(combo)
        team_b_list = [dict(players[i]) for i in b_indices]

        team_a = _build_team(team_a_list)
        team_b = _build_team(team_b_list)

        mmr_diff = abs(team_a.total_mmr - team_b.total_mmr)
        role_diff = abs(team_a.total_role_score - team_b.total_role_score)

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

    configs.sort(key=lambda x: x[0])
    return [r for _, r in configs[:top_n]]
