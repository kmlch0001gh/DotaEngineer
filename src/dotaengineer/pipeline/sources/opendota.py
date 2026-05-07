"""OpenDota REST API client with rate limiting.

Free tier: 50,000 calls/month, 60 requests/minute.
Docs: https://docs.opendota.com/
"""

from __future__ import annotations

import time

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.opendota.com/api"
MIN_DELAY = 1.1  # seconds between requests (60 req/min limit)


class OpenDotaClient:
    """Synchronous OpenDota API client with automatic rate limiting."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._last_request = 0.0
        self._client = httpx.Client(timeout=30.0)

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < MIN_DELAY:
            time.sleep(MIN_DELAY - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        self._rate_limit()
        url = f"{BASE_URL}{path}"
        p = dict(params or {})
        if self._api_key:
            p["api_key"] = self._api_key
        resp = self._client.get(url, params=p)
        resp.raise_for_status()
        return resp.json()

    def hero_stats(self) -> list[dict]:
        """Get hero stats across all brackets.

        Returns list of hero objects with bracket-specific win/pick data.
        Fields: id, localized_name, pro_pick, pro_win, pro_ban,
                1_pick, 1_win, 2_pick, 2_win, ..., 8_pick, 8_win
        Brackets: 1=Herald, 2=Guardian, ..., 7=Divine, 8=Immortal
        """
        return self._get("/heroStats")

    def hero_matchups(self, hero_id: int) -> list[dict]:
        """Get hero matchup data (counters).

        Returns [{hero_id, games_played, wins}] for each opponent hero.
        """
        return self._get(f"/heroes/{hero_id}/matchups")

    def hero_item_popularity(self, hero_id: int) -> dict:
        """Get popular items per game phase for a hero.

        Returns {start_game_items, early_game_items, mid_game_items,
                 late_game_items} with {item_id: count}.
        """
        return self._get(f"/heroes/{hero_id}/itemPopularity")

    def pro_players(self) -> list[dict]:
        """Get list of verified professional players.

        Returns [{account_id, name, team_name, country_code, ...}]
        """
        return self._get("/proPlayers")

    def pro_matches(self, less_than_match_id: int | None = None) -> list[dict]:
        """Get recent professional matches.

        Returns [{match_id, duration, radiant_win, league_name, ...}]
        """
        params = {}
        if less_than_match_id:
            params["less_than_match_id"] = less_than_match_id
        return self._get("/proMatches", params)

    def player(self, account_id: int) -> dict:
        """Get player profile."""
        return self._get(f"/players/{account_id}")

    def player_recent_matches(
        self, account_id: int, limit: int = 20
    ) -> list[dict]:
        """Get player's recent matches."""
        return self._get(f"/players/{account_id}/recentMatches")

    def player_heroes(self, account_id: int) -> list[dict]:
        """Get player's hero stats."""
        return self._get(f"/players/{account_id}/heroes")

    def constants(self, resource: str) -> dict | list:
        """Get game constants (heroes, items, abilities, etc.)."""
        return self._get(f"/constants/{resource}")

    def close(self) -> None:
        self._client.close()
