"""OpenDota API client.

Docs: https://docs.opendota.com/
Free tier: 2000 req/day without key, 50k/month with free key.
"""

from __future__ import annotations

from typing import Any

from dotaengineer.config import settings
from dotaengineer.ingestion.base import BaseAPIClient
from dotaengineer.models.match import Match, HeroStats


class OpenDotaClient(BaseAPIClient):
    BASE_URL = "https://api.opendota.com/api"

    def __init__(self) -> None:
        super().__init__(
            base_url=self.BASE_URL,
            api_key=settings.opendota_api_key or None,
            requests_per_minute=settings.opendota_requests_per_minute,
        )

    # ── Match data ─────────────────────────────────────────────────────────────

    async def get_match(self, match_id: int) -> Match:
        data = await self._get(f"/matches/{match_id}")
        return Match.model_validate(data)

    async def get_player_matches(
        self,
        account_id: int,
        limit: int = 100,
        significant: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch recent ranked matches for a player."""
        params: dict[str, Any] = {
            "limit": limit,
            "lobby_type": 7,  # ranked
        }
        if significant:
            params["significant"] = 1
        return await self._get(f"/players/{account_id}/matches", params)

    async def get_player_heroes(self, account_id: int) -> list[dict[str, Any]]:
        """Hero performance summary for a player."""
        return await self._get(f"/players/{account_id}/heroes")

    async def get_player_peers(self, account_id: int) -> list[dict[str, Any]]:
        """Players frequently played with."""
        return await self._get(f"/players/{account_id}/peers")

    async def get_player_wl(
        self, account_id: int, limit: int = 100
    ) -> dict[str, int]:
        """Win/loss count for recent matches."""
        return await self._get(
            f"/players/{account_id}/wl", {"limit": limit, "lobby_type": 7}
        )

    # ── Meta data ──────────────────────────────────────────────────────────────

    async def get_hero_stats(self) -> list[dict[str, Any]]:
        """All heroes with aggregate stats (all brackets)."""
        return await self._get("/heroStats")

    async def get_heroes(self) -> list[dict[str, Any]]:
        """Hero metadata (names, attributes, roles)."""
        return await self._get("/heroes")

    async def get_hero_matchups(self, hero_id: int) -> list[dict[str, Any]]:
        """Win rate of hero_id against every other hero."""
        return await self._get(f"/heroes/{hero_id}/matchups")

    async def get_hero_duos(self, hero_id: int) -> list[dict[str, Any]]:
        """Win rate of hero_id alongside every other hero."""
        return await self._get(f"/heroes/{hero_id}/duos")

    async def get_public_matches(
        self,
        min_rank: int = 70,  # 70 = Immortal, 80 = top 1000
        less_than_match_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Stream of recent public matches at high rank.

        min_rank tiers:
          10=Herald, 20=Guardian, 30=Crusader, 40=Archon, 50=Legend,
          60=Ancient, 70=Divine, 80=Immortal
        """
        params: dict[str, Any] = {"min_rank": min_rank}
        if less_than_match_id:
            params["less_than_match_id"] = less_than_match_id
        return await self._get("/publicMatches", params)

    async def get_distributions(self) -> dict[str, Any]:
        """MMR distribution across all players."""
        return await self._get("/distributions")

    # ── Pro data ───────────────────────────────────────────────────────────────

    async def get_pro_matches(self, less_than_match_id: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if less_than_match_id:
            params["less_than_match_id"] = less_than_match_id
        return await self._get("/proMatches", params)

    async def get_pro_players(self) -> list[dict[str, Any]]:
        return await self._get("/proPlayers")

    # ── Item data ─────────────────────────────────────────────────────────────

    async def get_items(self) -> dict[str, Any]:
        return await self._get("/constants/items")

    async def get_item_timings(
        self, hero_id: int, item: str
    ) -> list[dict[str, Any]]:
        """Win rate by timing of item purchase on a hero."""
        return await self._get(
            "/scenarios/itemTimings",
            {"hero_id": hero_id, "item": item},
        )

    async def get_lane_roles(self, hero_id: int, lane_role: int) -> list[dict[str, Any]]:
        """Win rate of hero in a given lane role at different game durations."""
        return await self._get(
            "/scenarios/laneRoles",
            {"hero_id": hero_id, "lane_role": lane_role},
        )
