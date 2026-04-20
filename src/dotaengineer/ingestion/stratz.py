"""Stratz GraphQL API client.

Docs: https://stratz.com/api
Token: https://stratz.com/api (requires login)
Better for: ranked bracket filtering, draft analysis, laning stats.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from dotaengineer.config import settings
from dotaengineer.ingestion.base import RateLimiter

logger = structlog.get_logger()

STRATZ_GQL_URL = "https://api.stratz.com/graphql"


class StratzClient:
    """GraphQL client for Stratz."""

    def __init__(self) -> None:
        self._token = settings.stratz_api_token
        self._limiter = RateLimiter(settings.stratz_requests_per_minute)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "StratzClient":
        self._client = httpx.AsyncClient(
            base_url=STRATZ_GQL_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def query(self, gql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self._client, "Use as async context manager"
        await self._limiter.acquire()
        response = await self._client.post(
            "",
            json={"query": gql, "variables": variables or {}},
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    # ── Pre-built queries ──────────────────────────────────────────────────────

    async def get_hero_stats_by_bracket(
        self, bracket: str = "IMMORTAL"
    ) -> dict[str, Any]:
        """
        bracket options: HERALD, GUARDIAN, CRUSADER, ARCHON, LEGEND, ANCIENT, DIVINE, IMMORTAL
        Returns win rate, pick rate, ban rate per hero at that bracket.
        """
        gql = """
        query HeroStatsByBracket($bracket: RankBracket!) {
          heroStats {
            winWeek(bracketBasicIds: [$bracket]) {
              heroId
              winCount
              matchCount
              bandWidth
            }
          }
        }
        """
        return await self.query(gql, {"bracket": bracket})

    async def get_hero_vs_hero(
        self, hero_id: int, bracket: str = "IMMORTAL"
    ) -> dict[str, Any]:
        """Head-to-head win rates for a hero vs all others at a bracket."""
        gql = """
        query HeroVsHero($heroId: Short!, $bracket: RankBracket!) {
          heroStats {
            heroVsHeroMatchup(heroId: $heroId, bracketBasicIds: [$bracket], take: 120) {
              advantage {
                heroId
                vs {
                  heroId
                  winCount
                  matchCount
                  synergy
                }
              }
            }
          }
        }
        """
        return await self.query(gql, {"heroId": hero_id, "bracket": bracket})

    async def get_player_matches(
        self, steam_id: int, take: int = 50, skip: int = 0
    ) -> dict[str, Any]:
        gql = """
        query PlayerMatches($steamId: Long!, $take: Int!, $skip: Int!) {
          player(steamAccountId: $steamId) {
            matches(request: {
              take: $take
              skip: $skip
              lobbyTypeIds: [7]
            }) {
              id
              didRadiantWin
              durationSeconds
              startDateTime
              players(steamAccountId: $steamId) {
                heroId
                isRadiant
                kills
                deaths
                assists
                networth
                goldPerMinute
                experiencePerMinute
                lane
                laneOutcome
                numLastHits
                numDenies
                item0Id
                item1Id
                item2Id
                item3Id
                item4Id
                item5Id
                role
                roleBasic
                stats {
                  campStack
                }
                imp
              }
            }
          }
        }
        """
        return await self.query(gql, {"steamId": steam_id, "take": take, "skip": skip})

    async def get_draft_stats(
        self, hero_ids: list[int], bracket: str = "IMMORTAL"
    ) -> dict[str, Any]:
        """Win rate when specific hero combination is drafted together."""
        gql = """
        query DraftStats($heroIds: [Short]!, $bracket: RankBracket!) {
          heroStats {
            matchUp(
              heroId: $heroIds
              bracketBasicIds: [$bracket]
              take: 100
            ) {
              heroId
              matchCount
              winCount
            }
          }
        }
        """
        return await self.query(gql, {"heroIds": hero_ids, "bracket": bracket})

    async def get_laning_stats(
        self, hero_id: int, bracket: str = "IMMORTAL"
    ) -> dict[str, Any]:
        """Laning phase performance metrics for a hero at bracket."""
        gql = """
        query LaningStats($heroId: Short!, $bracket: RankBracket!) {
          heroStats {
            laneOutcome(heroId: $heroId, bracketBasicIds: [$bracket]) {
              heroId
              isRadiant
              laneType
              matchCount
              winCount
              stompWinCount
              stompLossCount
            }
          }
        }
        """
        return await self.query(gql, {"heroId": hero_id, "bracket": bracket})
