"""Streamlit dashboard — DotaEngineer.

Run with:  streamlit run src/dotaengineer/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from dotaengineer.analysis.draft import DraftAnalyzer
from dotaengineer.analysis.meta import MetaAnalyzer
from dotaengineer.analysis.player_performance import PlayerPerformanceAnalyzer
from dotaengineer.config import settings

st.set_page_config(
    page_title="DotaEngineer",
    page_icon="⚔️",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("DotaEngineer")
st.sidebar.caption(f"Account: {settings.my_steam_id or 'not set'}")

page = st.sidebar.radio(
    "Section",
    ["Meta Tierlist", "Draft Tool", "My Performance", "Farm Efficiency"],
)

# ── Cache heavy queries ────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_tier_list() -> pl.DataFrame:
    return MetaAnalyzer().tier_list()


@st.cache_data(ttl=3600)
def load_sleepers() -> pl.DataFrame:
    return MetaAnalyzer().sleeper_picks()


@st.cache_data(ttl=3600)
def load_hero_pool() -> pl.DataFrame:
    return PlayerPerformanceAnalyzer().hero_pool_summary()


@st.cache_data(ttl=3600)
def load_farm_efficiency() -> pl.DataFrame:
    return PlayerPerformanceAnalyzer().farm_efficiency()


@st.cache_data(ttl=3600)
def load_duration_splits() -> pl.DataFrame:
    return PlayerPerformanceAnalyzer().win_loss_by_duration()


# ── Pages ──────────────────────────────────────────────────────────────────────

if page == "Meta Tierlist":
    st.title("Immortal Meta — Hero Tier List")

    tier_df = load_tier_list()
    sleepers = load_sleepers()

    col1, col2 = st.columns([3, 1])

    with col1:
        tier_filter = st.multiselect("Filter tiers", ["S", "A", "B", "C"], default=["S", "A"])
        role_filter = st.multiselect(
            "Filter roles",
            sorted(tier_df["primary_role"].unique().to_list()),
        )

        filtered = tier_df.filter(pl.col("tier").is_in(tier_filter))
        if role_filter:
            filtered = filtered.filter(pl.col("primary_role").is_in(role_filter))

        fig = px.scatter(
            filtered.to_pandas(),
            x="pick_rate",
            y="win_rate",
            color="tier",
            size="contest_rate",
            hover_name="hero_name",
            hover_data=["ban_rate", "primary_role"],
            color_discrete_map={"S": "#FFD700", "A": "#00C853", "B": "#2196F3", "C": "#9E9E9E"},
            title="Win Rate vs Pick Rate at Immortal",
            labels={"win_rate": "Win Rate", "pick_rate": "Pick Rate"},
        )
        fig.add_hline(y=0.5, line_dash="dash", line_color="red", opacity=0.4)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Sleeper Picks")
        st.caption("High WR, low PR/ban — underexplored")
        st.dataframe(
            sleepers.select(["hero_name", "win_rate", "pick_rate"]).to_pandas(),
            use_container_width=True,
            hide_index=True,
        )

elif page == "Draft Tool":
    st.title("Draft Tool — 8k Bracket")
    st.caption("Enter picked heroes to get counter-pick and synergy recommendations.")

    analyzer = DraftAnalyzer()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Enemy Team")
        enemy_input = st.text_input("Enemy hero IDs (comma separated)", placeholder="1, 2, 3")
    with col2:
        st.subheader("My Team")
        ally_input = st.text_input("Ally hero IDs (comma separated)", placeholder="4, 5")

    pool_input = st.text_input("My hero pool IDs (optional, comma separated)", "")

    def parse_ids(s: str) -> list[int]:
        return [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]

    if st.button("Analyze Draft"):
        enemy_ids = parse_ids(enemy_input)
        ally_ids = parse_ids(ally_input)
        pool_ids = parse_ids(pool_input) or None

        if not enemy_ids:
            st.warning("Enter at least one enemy hero ID.")
        else:
            try:
                picks = analyzer.get_best_pick(ally_ids, enemy_ids, pool=pool_ids)
                st.subheader("Best Picks")
                st.dataframe(picks.to_pandas(), use_container_width=True, hide_index=True)

                if enemy_ids and ally_ids:
                    draft_eval = analyzer.analyze_draft(ally_ids, enemy_ids)
                    col_r, col_d = st.columns(2)
                    col_r.metric("My Draft Advantage", f"{draft_eval['radiant_draft_advantage']:.3f}")
                    col_d.metric("Enemy Draft Advantage", f"{draft_eval['dire_draft_advantage']:.3f}")
                    st.info(f"Favored: **{draft_eval['favored']}** (net edge: {draft_eval['net_radiant_edge']:.3f})")
            except Exception as e:
                st.error(f"Error: {e}. Run the meta pipeline first to populate matchup tables.")

elif page == "My Performance":
    st.title("Personal Performance Analysis")

    if not settings.my_steam_id:
        st.warning("Set MY_STEAM_ID in your .env and run the player ingestion pipeline first.")
    else:
        hero_pool = load_hero_pool()

        st.subheader("Hero Pool — Win Rate vs Meta Baseline")
        fig = px.bar(
            hero_pool.sort("wr_vs_meta", descending=True).to_pandas(),
            x="hero_name",
            y="wr_vs_meta",
            color="wr_vs_meta",
            color_continuous_scale="RdYlGn",
            title="Your WR minus Immortal Meta WR (positive = above meta)",
            labels={"wr_vs_meta": "WR Delta vs Meta", "hero_name": "Hero"},
        )
        fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
        st.plotly_chart(fig, use_container_width=True)

        splits = load_duration_splits()
        st.subheader("Win Rate by Game Duration")
        st.bar_chart(splits.to_pandas().set_index("duration_bucket")["win_rate"])

elif page == "Farm Efficiency":
    st.title("Farm Efficiency vs Immortal Bracket")

    farm = load_farm_efficiency()

    st.subheader("GPM Delta vs Meta Avg per Hero")
    fig = px.bar(
        farm.sort("gpm_diff_vs_meta").to_pandas(),
        x="hero_name",
        y="gpm_diff_vs_meta",
        color="gpm_diff_vs_meta",
        color_continuous_scale="RdYlGn",
        title="Your GPM minus Meta Average GPM (negative = falling behind curve)",
    )
    fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        farm.select(["hero_name", "games", "avg_gpm", "meta_avg_gpm", "gpm_diff_vs_meta"]).to_pandas(),
        use_container_width=True,
        hide_index=True,
    )
