"""Stratz GraphQL API client.

Endpoint: https://api.stratz.com/graphql
Auth: Bearer token (get from https://stratz.com/api → My Tokens)
Rate limits: Default 2,000/hour, 10,000/day
Docs: https://stratz.com/api
"""

from __future__ import annotations

import time

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.stratz.com/graphql"
MIN_DELAY = 0.5  # 20 req/sec max


class StratzClient:
    """Synchronous Stratz GraphQL client with rate limiting."""

    def __init__(self, token: str):
        self._token = token
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "DotaEngineer/1.0",
            },
        )

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < MIN_DELAY:
            time.sleep(MIN_DELAY - elapsed)
        self._last_request = time.time()

    def _query(self, query: str, variables: dict | None = None) -> dict:
        self._rate_limit()
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self._client.post(BASE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            log.warning("stratz_graphql_errors", errors=data["errors"])
        return data.get("data", {})

    def hero_stats(self, bracket: str = "IMMORTAL") -> list[dict]:
        """Get hero win/pick/ban stats for a bracket.

        Brackets: HERALD, GUARDIAN, CRUSADER, ARCHON, LEGEND,
                  ANCIENT, DIVINE, IMMORTAL, PROFESSIONAL
        """
        query = """
        query HeroStats($bracket: RankBracket) {
            heroStats {
                stats(bracketBasicIds: [$bracket]) {
                    heroId
                    matchCount
                    winCount
                    banCount
                }
            }
        }
        """
        data = self._query(query, {"bracket": bracket})
        stats = data.get("heroStats", {}).get("stats", [])
        return stats

    def leaderboard(self, region: str = "AMERICAS") -> list[dict]:
        """Get MMR leaderboard for a region.

        Regions: AMERICAS, SE_ASIA, EUROPE, CHINA
        """
        query = """
        query Leaderboard($region: LeaderboardDivision!) {
            leaderboard {
                season(request: {
                    leaderBoardDivision: $region
                    take: 100
                }) {
                    steamAccountId
                    rank
                    seasonRankId
                }
            }
        }
        """
        data = self._query(query, {"region": region})
        season = data.get("leaderboard", {}).get("season", [])
        return season if isinstance(season, list) else []

    def player_matches(
        self, account_id: int, take: int = 20
    ) -> list[dict]:
        """Get recent matches for a player."""
        query = """
        query PlayerMatches($id: Long!, $take: Int) {
            player(steamAccountId: $id) {
                matches(request: { take: $take }) {
                    id
                    durationSeconds
                    didRadiantWin
                    players(steamAccountId: $id) {
                        heroId
                        isRadiant
                        kills
                        deaths
                        assists
                        goldPerMinute
                        experiencePerMinute
                    }
                }
            }
        }
        """
        data = self._query(query, {"id": account_id, "take": take})
        player = data.get("player", {})
        return player.get("matches", []) if player else []

    def hero_item_builds(
        self, hero_id: int, bracket: str = "IMMORTAL"
    ) -> dict:
        """Get item popularity for a hero at a bracket."""
        query = """
        query HeroItems($heroId: Short!, $bracket: RankBracket) {
            heroStats {
                itemBootPurchase(
                    heroId: $heroId
                    bracketBasicIds: [$bracket]
                ) {
                    itemId
                    matchCount
                    winsAverage
                }
                itemNeutral(
                    heroId: $heroId
                    bracketBasicIds: [$bracket]
                ) {
                    itemId
                    matchCount
                    winsAverage
                }
            }
        }
        """
        data = self._query(
            query, {"heroId": hero_id, "bracket": bracket}
        )
        return data.get("heroStats", {})

    def test_connection(self) -> bool:
        """Test if the token is valid."""
        try:
            query = "{ constants { gameVersions { id name } } }"
            data = self._query(query)
            return bool(data)
        except Exception as e:
            log.error("stratz_connection_failed", error=str(e))
            return False

    def close(self) -> None:
        self._client.close()
