"""Utility functions and classes for Celcat scraper.

This module provides helper functions and classes for handling
rate limiting.
"""

import asyncio
import time


class RateLimiter:
    """Rate limiter for API requests with adaptive backoff."""

    def __init__(self, rate_limit: float = 2.0):
        self.delay = rate_limit
        self.last_call = 0.0
        self._backoff_factor = 1.0

    async def acquire(self):
        """Wait until rate limit allows next request."""
        now = time.monotonic()
        delay = self.delay * self._backoff_factor
        elapsed = now - self.last_call
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self.last_call = time.monotonic()

    def increase_backoff(self):
        """Increase backoff factor on failure."""
        self._backoff_factor = min(self._backoff_factor * 1.5, 4.0)

    def reset_backoff(self):
        """Reset backoff factor on success."""
        self._backoff_factor = 1.0
