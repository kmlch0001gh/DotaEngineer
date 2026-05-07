"""Steam Web API client for Dota 2.

Endpoint: https://api.steampowered.com
Auth: API key (get from https://steamcommunity.com/dev/apikey)
Docs: https://steamapi.xpaw.me/
"""

from __future__ import annotations

import time

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.steampowered.com"
MIN_DELAY = 0.5


class SteamClient:
    """Synchronous Steam Web API client for Dota 2 data."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._last_request = 0.0
        self._client = httpx.Client(timeout=30.0)

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < MIN_DELAY:
            time.sleep(MIN_DELAY - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._rate_limit()
        url = f"{BASE_URL}{path}"
        p = dict(params or {})
        p["key"] = self._api_key
        resp = self._client.get(url, params=p)
        resp.raise_for_status()
        return resp.json()

    def get_match_details(self, match_id: int) -> dict:
        """Get detailed match data."""
        data = self._get(
            "/IDOTA2Match_570/GetMatchDetails/v1",
            {"match_id": match_id},
        )
        return data.get("result", {})

    def get_match_history(
        self,
        account_id: int | None = None,
        hero_id: int | None = None,
        matches_requested: int = 25,
    ) -> list[dict]:
        """Get match history for a player or hero."""
        params: dict = {"matches_requested": matches_requested}
        if account_id:
            params["account_id"] = account_id
        if hero_id:
            params["hero_id"] = hero_id
        data = self._get(
            "/IDOTA2Match_570/GetMatchHistory/v1", params
        )
        return data.get("result", {}).get("matches", [])

    def get_live_league_games(self) -> list[dict]:
        """Get currently live league/tournament games."""
        data = self._get(
            "/IDOTA2Match_570/GetLiveLeagueGames/v1"
        )
        return data.get("result", {}).get("games", [])

    def get_top_live_games(self, partner: int = 0) -> list[dict]:
        """Get top live games by spectator count."""
        data = self._get(
            "/IDOTA2Match_570/GetTopLiveGame/v1",
            {"partner": partner},
        )
        return data.get("game_list", [])

    def get_team_info(
        self, start_at_team_id: int = 0, teams_requested: int = 100
    ) -> list[dict]:
        """Get professional team info."""
        data = self._get(
            "/IDOTA2Match_570/GetTeamInfoByTeamID/v1",
            {
                "start_at_team_id": start_at_team_id,
                "teams_requested": teams_requested,
            },
        )
        return data.get("result", {}).get("teams", [])

    def test_connection(self) -> bool:
        """Test if the API key is valid."""
        try:
            data = self._get(
                "/IDOTA2Match_570/GetTopLiveGame/v1",
                {"partner": 0},
            )
            return "game_list" in data
        except Exception as e:
            log.error("steam_connection_failed", error=str(e))
            return False

    def close(self) -> None:
        self._client.close()
