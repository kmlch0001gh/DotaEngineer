"""Player data models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlayerCreate(BaseModel):
    username: str = Field(min_length=2, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=30)


class Player(BaseModel):
    id: int
    username: str
    display_name: str
    mmr: int
    games_played: int
    wins: int
    losses: int
    is_active: bool
    created_at: datetime

    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    @property
    def win_rate_pct(self) -> str:
        return f"{self.win_rate * 100:.1f}%"


class HeroBreakdown(BaseModel):
    hero_id: int
    hero_name: str
    games: int
    wins: int
    losses: int
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_gpm: float

    @property
    def win_rate(self) -> float:
        if self.games == 0:
            return 0.0
        return self.wins / self.games

    @property
    def win_rate_pct(self) -> str:
        return f"{self.win_rate * 100:.1f}%"


class PlayerAchievements(BaseModel):
    double_kills: int = 0
    triple_kills: int = 0
    ultra_kills: int = 0
    rampage: int = 0
    killing_sprees: int = 0
    dominating: int = 0
    mega_kills: int = 0
    unstoppable: int = 0
    wicked_sick: int = 0
    monster_kill: int = 0
    godlike: int = 0
    beyond_godlike: int = 0
    courier_kills: int = 0
    roshan_kills: int = 0
    tormentor_kills: int = 0


class PlayerStats(BaseModel):
    player: Player
    avg_kills: float = 0.0
    avg_deaths: float = 0.0
    avg_assists: float = 0.0
    avg_gpm: float = 0.0
    favorite_hero: str | None = None
    current_streak: int = 0  # positive = win streak, negative = loss
    best_win_streak: int = 0
    hero_breakdown: list[HeroBreakdown] = Field(default_factory=list)
    achievements: PlayerAchievements = Field(default_factory=PlayerAchievements)
