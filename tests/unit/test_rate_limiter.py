"""Tests for the async rate limiter."""

import asyncio
import time

import pytest
from dotaengineer.ingestion.base import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_burst():
    limiter = RateLimiter(requests_per_minute=60)
    start = time.monotonic()
    # Should acquire 5 tokens immediately (bucket starts full)
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, "First 5 requests should be near-instant"


@pytest.mark.asyncio
async def test_rate_limiter_throttles():
    # 6 req/min = 1 per 10 seconds — too slow for a test.
    # Use 120 req/min = 2/sec, drain bucket, then measure throttling.
    limiter = RateLimiter(requests_per_minute=120)
    # Drain entire bucket (120 tokens)
    for _ in range(120):
        await limiter.acquire()

    # Next acquire should wait ~0.5s (1/2 per sec)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.3, "Should throttle after bucket is empty"
