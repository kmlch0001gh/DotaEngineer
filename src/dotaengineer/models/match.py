"""Pydantic models for raw OpenDota / Stratz match data."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerSlot(BaseModel):
    account_id: int | None = None
    hero_id: int
    player_slot: int  # 0-4 Radiant, 128-132 Dire
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    last_hits: int = 0
    denies: int = 0
    gold_per_min: int = 0
    xp_per_min: int = 0
    net_worth: int = 0
    hero_damage: int = 0
    tower_damage: int = 0
    hero_healing: int = 0
    level: int = 0
    item_0: int = 0
    item_1: int = 0
    item_2: int = 0
    item_3: int = 0
    item_4: int = 0
    item_5: int = 0
    backpack_0: int = 0
    backpack_1: int = 0
    backpack_2: int = 0
    item_neutral: int = 0
    # Timing benchmarks
    benchmarks: dict[str, Any] | None = None
    # Lane assignment
    lane: int | None = None          # 1=safe, 2=mid, 3=off
    lane_role: int | None = None     # 1=safe, 2=mid, 3=off, 4=jungle
    is_roaming: bool | None = None
    # Performance vs peers at same MMR
    rank_tier: int | None = None

    @property
    def is_radiant(self) -> bool:
        return self.player_slot < 128

    @property
    def kda(self) -> float:
        return (self.kills + self.assists) / max(self.deaths, 1)


class Match(BaseModel):
    match_id: int
    start_time: int  # Unix timestamp
    duration: int    # seconds
    radiant_win: bool
    game_mode: int
    lobby_type: int
    avg_mmr: int | None = None
    radiant_score: int = 0
    dire_score: int = 0
    players: list[PlayerSlot] = Field(default_factory=list)
    patch: int | None = None
    region: int | None = None
    # Draft order (for captains mode / ranked all pick)
    picks_bans: list[dict[str, Any]] | None = None

    @property
    def duration_minutes(self) -> float:
        return self.duration / 60

    def get_player(self, account_id: int) -> PlayerSlot | None:
        return next((p for p in self.players if p.account_id == account_id), None)


class HeroStats(BaseModel):
    """Hero win rates and pick rates at a given MMR bracket."""

    hero_id: int
    hero_name: str
    localized_name: str
    primary_attr: str
    attack_type: str
    roles: list[str]
    # Stats at MMR bracket
    games: int = 0
    wins: int = 0
    pick_rate: float = 0.0
    ban_rate: float = 0.0
    # KDA / farm averages at high MMR
    avg_kills: float = 0.0
    avg_deaths: float = 0.0
    avg_assists: float = 0.0
    avg_gpm: float = 0.0
    avg_xpm: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / max(self.games, 1)
