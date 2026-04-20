"""Draft analysis engine.

Answers the key question for 8k MMR drafts:
  - Given the enemy picks so far, what is my best available hero?
  - What is the synergy score of my current draft?
  - What should I ban to disrupt the enemy draft the most?

Uses pre-computed matchup matrices from DuckDB (populated by meta pipeline).
"""

from __future__ import annotations

import duckdb
import polars as pl
import structlog

from dotaengineer.config import settings

logger = structlog.get_logger()


class DraftAnalyzer:
    """Stateless analyzer that reads matchup data from DuckDB."""

    def __init__(self) -> None:
        self._db_path = settings.duckdb_path

    def _con(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self._db_path, read_only=True)

    # ── Core queries ───────────────────────────────────────────────────────────

    def get_counters(
        self,
        enemy_hero_ids: list[int],
        top_n: int = 10,
        min_matches: int = 500,
    ) -> pl.DataFrame:
        """Return top N heroes that counter the given enemy lineup.

        Score = average win rate advantage vs each enemy hero.
        Filters to heroes with enough sample size at high MMR.
        """
        if not enemy_hero_ids:
            raise ValueError("Provide at least one enemy hero")

        enemy_tuple = tuple(enemy_hero_ids)
        con = self._con()

        df = con.execute(f"""
            SELECT
                hero_id,
                hero_name,
                AVG(win_rate_advantage) AS avg_advantage,
                AVG(win_rate)           AS avg_win_rate,
                MIN(matchup_count)      AS min_sample
            FROM hero_matchups_immortal
            WHERE enemy_hero_id IN {enemy_tuple}
              AND hero_id NOT IN {enemy_tuple}
              AND matchup_count >= {min_matches}
            GROUP BY hero_id, hero_name
            ORDER BY avg_advantage DESC
            LIMIT {top_n}
        """).pl()

        con.close()
        return df

    def get_synergies(
        self,
        allied_hero_ids: list[int],
        top_n: int = 10,
        min_matches: int = 500,
    ) -> pl.DataFrame:
        """Return top N heroes that synergize with the current allied draft."""
        if not allied_hero_ids:
            raise ValueError("Provide at least one allied hero")

        allied_tuple = tuple(allied_hero_ids)
        con = self._con()

        df = con.execute(f"""
            SELECT
                hero_id,
                hero_name,
                AVG(synergy_score)   AS avg_synergy,
                AVG(duo_win_rate)    AS avg_duo_win_rate,
                MIN(duo_match_count) AS min_sample
            FROM hero_duos_immortal
            WHERE ally_hero_id IN {allied_tuple}
              AND hero_id NOT IN {allied_tuple}
              AND duo_match_count >= {min_matches}
            GROUP BY hero_id, hero_name
            ORDER BY avg_synergy DESC
            LIMIT {top_n}
        """).pl()

        con.close()
        return df

    def get_best_pick(
        self,
        my_team: list[int],
        enemy_team: list[int],
        pool: list[int] | None = None,
        top_n: int = 5,
    ) -> pl.DataFrame:
        """Combined score: counter-pick advantage + team synergy.

        pool: restrict to specific hero IDs (your hero pool).
        Returns ranked DataFrame with breakdown.
        """
        counters = self.get_counters(enemy_team, top_n=50)
        synergies = self.get_synergies(my_team, top_n=50) if my_team else None

        all_heroes = set(counters["hero_id"].to_list())
        already_picked = set(my_team + enemy_team)
        available = all_heroes - already_picked

        if pool:
            available &= set(pool)

        counters_filtered = counters.filter(pl.col("hero_id").is_in(list(available)))

        if synergies is not None:
            result = counters_filtered.join(
                synergies.select(["hero_id", "avg_synergy", "avg_duo_win_rate"]),
                on="hero_id",
                how="left",
            ).with_columns(
                # Weighted score: 60% counter, 40% synergy
                combined_score=(
                    pl.col("avg_advantage") * 0.6
                    + pl.col("avg_synergy").fill_null(0) * 0.4
                )
            ).sort("combined_score", descending=True)
        else:
            result = counters_filtered.with_columns(
                combined_score=pl.col("avg_advantage")
            ).sort("combined_score", descending=True)

        return result.head(top_n)

    def get_ban_recommendations(
        self,
        my_team_roles: list[str] | None = None,
        patch: str | None = None,
        top_n: int = 5,
    ) -> pl.DataFrame:
        """Heroes to ban based on current meta win rate + pick rate at immortal.

        Prioritizes: high win rate AND high pick rate (contested picks).
        Optional filter by roles that are strong vs my typical playstyle.
        """
        con = self._con()

        role_filter = ""
        if my_team_roles:
            roles_str = ", ".join(f"'{r}'" for r in my_team_roles)
            role_filter = f"AND primary_role IN ({roles_str})"

        df = con.execute(f"""
            SELECT
                hero_id,
                hero_name,
                immortal_win_rate,
                immortal_pick_rate,
                -- Priority = win rate * sqrt(pick_rate) to weight contested picks
                (immortal_win_rate * SQRT(immortal_pick_rate)) AS ban_priority_score
            FROM hero_meta_immortal
            WHERE immortal_win_rate > 0.52
              AND immortal_pick_rate > 0.05
              {role_filter}
            ORDER BY ban_priority_score DESC
            LIMIT {top_n}
        """).pl()

        con.close()
        return df

    def analyze_draft(
        self,
        radiant: list[int],
        dire: list[int],
    ) -> dict:
        """Full draft evaluation: score both teams, identify advantage."""
        con = self._con()

        def team_score(team: list[int], enemy: list[int]) -> float:
            if not team or not enemy:
                return 0.0
            t = tuple(team)
            e = tuple(enemy)
            row = con.execute(f"""
                SELECT AVG(win_rate_advantage) AS score
                FROM hero_matchups_immortal
                WHERE hero_id IN {t} AND enemy_hero_id IN {e}
            """).fetchone()
            return row[0] if row and row[0] else 0.0

        radiant_score = team_score(radiant, dire)
        dire_score = team_score(dire, radiant)
        net = radiant_score - dire_score

        con.close()
        return {
            "radiant_draft_advantage": round(radiant_score, 4),
            "dire_draft_advantage": round(dire_score, 4),
            "net_radiant_edge": round(net, 4),
            "favored": "Radiant" if net > 0 else "Dire" if net < 0 else "Even",
        }
