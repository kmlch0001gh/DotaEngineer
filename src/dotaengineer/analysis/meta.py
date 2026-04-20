"""Meta analysis at immortal/divine bracket.

Answers:
  - Which heroes are currently overtuned (high WR + high PR)?
  - How did win rates shift after the last patch?
  - Which heroes are "sleeper" picks (high WR, low PR, low ban rate)?
  - Role meta: which positions are strongest in the current meta?
"""

from __future__ import annotations

import duckdb
import polars as pl

from dotaengineer.config import settings


class MetaAnalyzer:
    def __init__(self) -> None:
        self._db_path = settings.duckdb_path

    def _con(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self._db_path, read_only=True)

    def tier_list(
        self,
        min_pick_rate: float = 0.03,
        min_matches: int = 200,
    ) -> pl.DataFrame:
        """
        S/A/B/C tier classification at immortal bracket.
        S: WR > 54%, PR > 8%
        A: WR > 52%, PR > 5%
        B: WR 49-52%
        C: WR < 49%
        """
        con = self._con()
        df = con.execute(f"""
            SELECT
                hero_id,
                hero_name,
                primary_attr,
                primary_role,
                ROUND(immortal_win_rate, 3)  AS win_rate,
                ROUND(immortal_pick_rate, 3) AS pick_rate,
                ROUND(immortal_ban_rate, 3)  AS ban_rate,
                immortal_matches,
                CASE
                    WHEN immortal_win_rate > 0.54 AND immortal_pick_rate > 0.08 THEN 'S'
                    WHEN immortal_win_rate > 0.52 AND immortal_pick_rate > 0.05 THEN 'A'
                    WHEN immortal_win_rate BETWEEN 0.49 AND 0.52 THEN 'B'
                    ELSE 'C'
                END AS tier,
                -- Contest rate: pick + ban
                ROUND(immortal_pick_rate + immortal_ban_rate, 3) AS contest_rate
            FROM hero_meta_immortal
            WHERE immortal_matches >= {min_matches}
              AND immortal_pick_rate >= {min_pick_rate}
            ORDER BY tier, win_rate DESC
        """).pl()
        con.close()
        return df

    def sleeper_picks(
        self,
        max_pick_rate: float = 0.06,
        min_win_rate: float = 0.52,
    ) -> pl.DataFrame:
        """Heroes with strong win rates but low pick/ban = under-explored."""
        con = self._con()
        df = con.execute(f"""
            SELECT
                hero_id,
                hero_name,
                primary_role,
                ROUND(immortal_win_rate, 3)  AS win_rate,
                ROUND(immortal_pick_rate, 3) AS pick_rate,
                ROUND(immortal_ban_rate, 3)  AS ban_rate,
                immortal_matches             AS sample_size
            FROM hero_meta_immortal
            WHERE immortal_win_rate >= {min_win_rate}
              AND immortal_pick_rate <= {max_pick_rate}
              AND immortal_ban_rate <= 0.05
              AND immortal_matches >= 100
            ORDER BY immortal_win_rate DESC
        """).pl()
        con.close()
        return df

    def patch_delta(self, patch_a: str, patch_b: str) -> pl.DataFrame:
        """Win rate change between two patches — identify buffs/nerfs impact."""
        con = self._con()
        df = con.execute(f"""
            SELECT
                a.hero_id,
                a.hero_name,
                ROUND(a.win_rate, 3)                     AS wr_patch_a,
                ROUND(b.win_rate, 3)                     AS wr_patch_b,
                ROUND(b.win_rate - a.win_rate, 3)        AS wr_delta,
                ROUND(b.pick_rate - a.pick_rate, 3)      AS pr_delta
            FROM hero_meta_by_patch a
            JOIN hero_meta_by_patch b
                ON a.hero_id = b.hero_id
                AND a.patch = '{patch_a}'
                AND b.patch = '{patch_b}'
            ORDER BY ABS(wr_delta) DESC
        """).pl()
        con.close()
        return df

    def role_meta(self) -> pl.DataFrame:
        """Average win rate and avg pick rate grouped by primary role."""
        con = self._con()
        df = con.execute("""
            SELECT
                primary_role,
                COUNT(*)                               AS hero_count,
                ROUND(AVG(immortal_win_rate), 3)       AS avg_win_rate,
                ROUND(AVG(immortal_pick_rate), 3)      AS avg_pick_rate,
                ROUND(AVG(immortal_ban_rate), 3)       AS avg_ban_rate,
                -- Best hero per role
                FIRST(hero_name ORDER BY immortal_win_rate DESC) AS top_hero
            FROM hero_meta_immortal
            WHERE immortal_matches >= 200
            GROUP BY primary_role
            ORDER BY avg_win_rate DESC
        """).pl()
        con.close()
        return df
