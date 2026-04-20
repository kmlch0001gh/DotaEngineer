"""Personal performance analysis.

Identifies where you are losing EV at 7600 MMR vs the 8k bracket average.
Focuses on:
  - Hero pool efficiency (which heroes are dragging your winrate)
  - Lane phase deficits (CS, tower damage, kill participation in lane)
  - Farm timing windows (when your net worth falls behind curve)
  - Role-specific KPIs for carry / mid / pos3 at high MMR
"""

from __future__ import annotations

import duckdb
import polars as pl
import structlog

from dotaengineer.config import settings

logger = structlog.get_logger()


class PlayerPerformanceAnalyzer:
    def __init__(self, account_id: int | None = None) -> None:
        self._account_id = account_id or settings.my_steam_id
        self._db_path = settings.duckdb_path

    def _con(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self._db_path, read_only=True)

    # ── Hero pool ──────────────────────────────────────────────────────────────

    def hero_pool_summary(self, min_games: int = 10) -> pl.DataFrame:
        """Win rate and KDA per hero vs meta win rate at immortal."""
        con = self._con()
        df = con.execute(f"""
            SELECT
                pm.hero_id,
                hm.hero_name,
                COUNT(*)                            AS games,
                SUM(pm.won::INT)                    AS wins,
                ROUND(AVG(pm.won::INT), 3)          AS personal_wr,
                ROUND(AVG((pm.kills + pm.assists) / GREATEST(pm.deaths, 1)), 2) AS kda,
                ROUND(AVG(pm.gpm), 0)               AS avg_gpm,
                ROUND(AVG(pm.xpm), 0)               AS avg_xpm,
                hmi.immortal_win_rate               AS meta_wr_immortal,
                ROUND(AVG(pm.won::INT) - hmi.immortal_win_rate, 3) AS wr_vs_meta
            FROM player_matches pm
            LEFT JOIN hero_meta_immortal hmi USING (hero_id)
            LEFT JOIN heroes hm USING (hero_id)
            WHERE pm.gpm > 0   -- exclude remakes
            GROUP BY pm.hero_id, hm.hero_name, hmi.immortal_win_rate
            HAVING COUNT(*) >= {min_games}
            ORDER BY games DESC
        """).pl()
        con.close()
        return df

    def worst_heroes(self, min_games: int = 10) -> pl.DataFrame:
        """Heroes where your win rate is most below the meta baseline."""
        return (
            self.hero_pool_summary(min_games)
            .sort("wr_vs_meta", descending=False)
            .head(10)
        )

    def best_heroes(self, min_games: int = 10) -> pl.DataFrame:
        """Heroes where you outperform the meta the most."""
        return (
            self.hero_pool_summary(min_games)
            .sort("wr_vs_meta", descending=True)
            .head(10)
        )

    # ── GPM / Farm efficiency ─────────────────────────────────────────────────

    def farm_efficiency(self) -> pl.DataFrame:
        """GPM percentile vs immortal bracket average per hero, per role."""
        con = self._con()
        df = con.execute("""
            SELECT
                pm.hero_id,
                hm.hero_name,
                pm.lane_role,
                COUNT(*)                               AS games,
                ROUND(AVG(pm.gpm), 0)                 AS avg_gpm,
                ROUND(AVG(pm.xpm), 0)                 AS avg_xpm,
                ROUND(AVG(pm.last_hits), 0)           AS avg_lh,
                ROUND(AVG(pm.net_worth), 0)           AS avg_networth,
                bm.immortal_avg_gpm                   AS meta_avg_gpm,
                ROUND(AVG(pm.gpm) - bm.immortal_avg_gpm, 0) AS gpm_diff_vs_meta
            FROM player_matches pm
            LEFT JOIN hero_benchmarks_immortal bm USING (hero_id)
            LEFT JOIN heroes hm USING (hero_id)
            WHERE pm.gpm > 0
            GROUP BY pm.hero_id, hm.hero_name, pm.lane_role, bm.immortal_avg_gpm
            HAVING COUNT(*) >= 5
            ORDER BY gpm_diff_vs_meta ASC
        """).pl()
        con.close()
        return df

    # ── Laning phase ──────────────────────────────────────────────────────────

    def laning_stats(self) -> pl.DataFrame:
        """Lane phase performance: CS at 10min, kill participation in lane."""
        con = self._con()
        df = con.execute("""
            SELECT
                hero_id,
                lane,
                lane_role,
                COUNT(*)                         AS games,
                ROUND(AVG(won::INT), 3)          AS win_rate,
                -- Proxy: last_hits correlates with lane dominance
                ROUND(AVG(last_hits), 0)         AS avg_total_lh,
                ROUND(AVG(denies), 0)            AS avg_total_denies,
                ROUND(AVG(kills), 2)             AS avg_kills,
                ROUND(AVG(deaths), 2)            AS avg_deaths,
                ROUND(AVG(hero_damage), 0)       AS avg_hero_dmg
            FROM player_matches
            WHERE lane IS NOT NULL AND gpm > 0
            GROUP BY hero_id, lane, lane_role
            HAVING COUNT(*) >= 5
            ORDER BY win_rate DESC
        """).pl()
        con.close()
        return df

    # ── Win/loss patterns ─────────────────────────────────────────────────────

    def win_loss_by_duration(self) -> pl.DataFrame:
        """Win rate split by game duration bucket: <25min, 25-40min, >40min."""
        con = self._con()
        df = con.execute("""
            SELECT
                CASE
                    WHEN duration_sec < 1500 THEN '<25min'
                    WHEN duration_sec < 2400 THEN '25-40min'
                    ELSE '>40min'
                END                             AS duration_bucket,
                COUNT(*)                        AS games,
                ROUND(AVG(won::INT), 3)         AS win_rate,
                ROUND(AVG(gpm), 0)              AS avg_gpm
            FROM player_matches
            WHERE gpm > 0
            GROUP BY duration_bucket
            ORDER BY MIN(duration_sec)
        """).pl()
        con.close()
        return df

    def recent_trend(self, last_n: int = 50) -> pl.DataFrame:
        """Rolling 10-game win rate over last N matches to see form."""
        con = self._con()
        df = con.execute(f"""
            WITH recent AS (
                SELECT
                    match_id,
                    start_time,
                    won,
                    hero_id,
                    gpm,
                    ROW_NUMBER() OVER (ORDER BY start_time DESC) AS rn
                FROM player_matches
                WHERE gpm > 0
                LIMIT {last_n}
            )
            SELECT
                rn,
                match_id,
                start_time,
                won,
                hero_id,
                gpm,
                AVG(won::INT) OVER (
                    ORDER BY start_time DESC
                    ROWS BETWEEN CURRENT ROW AND 9 FOLLOWING
                ) AS rolling_10_wr
            FROM recent
            ORDER BY start_time DESC
        """).pl()
        con.close()
        return df

    def full_report(self) -> dict[str, pl.DataFrame]:
        """Run all analyses and return as a dict of DataFrames."""
        return {
            "hero_pool": self.hero_pool_summary(),
            "worst_heroes": self.worst_heroes(),
            "best_heroes": self.best_heroes(),
            "farm_efficiency": self.farm_efficiency(),
            "laning": self.laning_stats(),
            "duration_splits": self.win_loss_by_duration(),
            "recent_trend": self.recent_trend(),
        }
