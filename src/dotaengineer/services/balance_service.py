"""Auto-balance team generator for fair inhouse games."""

from __future__ import annotations

from itertools import combinations

from pydantic import BaseModel

from dotaengineer.db import Connection
from dotaengineer.elo import expected_score


class BalancedTeam(BaseModel):
    players: list[dict]  # [{id, display_name, mmr}, ...]
    total_mmr: int
    avg_mmr: float


class BalanceResult(BaseModel):
    team_a: BalancedTeam
    team_b: BalancedTeam
    mmr_difference: int
    predicted_win_a: float
    predicted_win_b: float


def balance_teams(player_ids: list[int], con: Connection) -> BalanceResult | None:
    """Find the fairest team split for given players.

    Uses brute-force for <=10 players (C(10,5) = 252 combinations).
    For more players, falls back to greedy partition.
    """
    if len(player_ids) < 2:
        return None

    # Fetch player data
    placeholders = ", ".join(["?"] * len(player_ids))
    rows = con.execute(
        f"SELECT id, display_name, mmr FROM players WHERE id IN ({placeholders})",
        player_ids,
    ).fetchall()

    players = [{"id": r[0], "display_name": r[1], "mmr": r[2]} for r in rows]
    if len(players) < 2:
        return None

    n = len(players)
    team_size = n // 2

    if n <= 12:
        # Brute force: try all combinations
        best_diff = float("inf")
        best_a_indices = None

        for combo in combinations(range(n), team_size):
            a_mmr = sum(players[i]["mmr"] for i in combo)
            b_indices = set(range(n)) - set(combo)
            b_mmr = sum(players[i]["mmr"] for i in b_indices)
            diff = abs(a_mmr - b_mmr)
            if diff < best_diff:
                best_diff = diff
                best_a_indices = set(combo)

        team_a_players = [players[i] for i in sorted(best_a_indices)]
        team_b_players = [players[i] for i in range(n) if i not in best_a_indices]
    else:
        # Greedy partition for larger groups
        sorted_players = sorted(players, key=lambda p: p["mmr"], reverse=True)
        team_a_players = []
        team_b_players = []
        sum_a = 0
        sum_b = 0

        for p in sorted_players:
            if len(team_a_players) >= team_size:
                team_b_players.append(p)
                sum_b += p["mmr"]
            elif len(team_b_players) >= (n - team_size):
                team_a_players.append(p)
                sum_a += p["mmr"]
            elif sum_a <= sum_b:
                team_a_players.append(p)
                sum_a += p["mmr"]
            else:
                team_b_players.append(p)
                sum_b += p["mmr"]

    total_a = sum(p["mmr"] for p in team_a_players)
    total_b = sum(p["mmr"] for p in team_b_players)
    avg_a = total_a / len(team_a_players) if team_a_players else 0
    avg_b = total_b / len(team_b_players) if team_b_players else 0

    win_a = expected_score(avg_a, avg_b)

    return BalanceResult(
        team_a=BalancedTeam(players=team_a_players, total_mmr=total_a, avg_mmr=round(avg_a)),
        team_b=BalancedTeam(players=team_b_players, total_mmr=total_b, avg_mmr=round(avg_b)),
        mmr_difference=abs(total_a - total_b),
        predicted_win_a=round(win_a * 100, 1),
        predicted_win_b=round((1 - win_a) * 100, 1),
    )
