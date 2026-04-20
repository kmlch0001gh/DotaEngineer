"""Base HTTP client with rate limiting and retry logic."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, requests_per_minute: int) -> None:
        self._rate = requests_per_minute / 60.0  # per second
        self._tokens = float(requests_per_minute)
        self._max_tokens = float(requests_per_minute)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._max_tokens,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


class BaseAPIClient:
    """Async HTTP client with rate limiting, retries, and structured logging."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        requests_per_minute: int = 60,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._limiter = RateLimiter(requests_per_minute)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseAPIClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
            follow_redirects=True,
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
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._client, "Use as async context manager"
        await self._limiter.acquire()

        params = params or {}
        if self._api_key:
            params["api_key"] = self._api_key

        log = logger.bind(path=path, params=params)
        log.debug("api.request")

        response = await self._client.get(path, params=params)
        response.raise_for_status()

        log.debug("api.response", status=response.status_code)
        return response.json()
