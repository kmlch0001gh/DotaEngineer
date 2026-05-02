"""Match data models for the cafe stats tracker."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MatchPlayerCreate(BaseModel):
    slot: int = Field(ge=0, le=9)
    hero_id: int
    team: Literal["radiant", "dire"]
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    last_hits: int = 0
    denies: int = 0
    gpm: int = 0
    xpm: int = 0
    net_worth: int = 0
    hero_damage: int = 0
    tower_damage: int = 0
    hero_healing: int = 0
    level: int = 0
    items: list[str] = Field(default_factory=list)


class MatchCreate(BaseModel):
    played_at: datetime = Field(default_factory=datetime.now)
    duration_seconds: int | None = None
    radiant_win: bool
    game_mode: str = "captains_mode"
    radiant_score: int = 0
    dire_score: int = 0
    notes: str = ""
    players: list[MatchPlayerCreate] = Field(min_length=2, max_length=10)
    bans: list[int] = Field(default_factory=list)  # hero IDs banned during draft
    purchase_log: dict[str, list[dict]] = Field(default_factory=dict)
    # hero_final_items: {hero_short_name: [item_name, ...]} from entity state
    hero_final_items: dict[str, list[str]] = Field(default_factory=dict)
    source: str = "manual"
    replay_file: str | None = None


class MatchPlayer(BaseModel):
    id: int
    match_id: int
    slot: int
    hero_id: int
    hero_name: str
    team: str
    player_id: int | None = None
    player_name: str | None = None
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    last_hits: int = 0
    denies: int = 0
    gpm: int = 0
    xpm: int = 0
    net_worth: int = 0
    hero_damage: int = 0
    tower_damage: int = 0
    hero_healing: int = 0
    level: int = 0
    items_json: str = "[]"

    @property
    def final_items(self) -> list[str]:
        import json

        try:
            return json.loads(self.items_json)
        except (json.JSONDecodeError, TypeError):
            return []

    won: bool = False

    @property
    def kda(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"


class CafeMatch(BaseModel):
    id: int
    replay_file: str | None = None
    played_at: datetime
    duration_seconds: int | None = None
    radiant_win: bool
    game_mode: str = "captains_mode"
    radiant_score: int = 0
    dire_score: int = 0
    source: str = "manual"
    notes: str = ""
    created_at: datetime | None = None
    players: list[MatchPlayer] = Field(default_factory=list)

    @property
    def duration_display(self) -> str:
        if not self.duration_seconds:
            return "--:--"
        m, s = divmod(self.duration_seconds, 60)
        return f"{m}:{s:02d}"

    @property
    def winner(self) -> str:
        return "Radiant" if self.radiant_win else "Dire"

    @property
    def radiant_players(self) -> list[MatchPlayer]:
        return [p for p in self.players if p.team == "radiant"]

    @property
    def dire_players(self) -> list[MatchPlayer]:
        return [p for p in self.players if p.team == "dire"]

    @property
    def all_claimed(self) -> bool:
        return all(p.player_id is not None for p in self.players)

    @property
    def claimed_count(self) -> int:
        return sum(1 for p in self.players if p.player_id is not None)


class ClaimRequest(BaseModel):
    player_id: int
    pin: str | None = None
