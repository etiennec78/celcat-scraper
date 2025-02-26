"""Utility functions and classes for Celcat scraper.

This module provides helper functions and classes for handling
rate limiting, retries, and other common operations.
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable

from aiohttp import ClientConnectorError

from .exceptions import CelcatCannotConnectError

class RateLimiter:
    """Rate limiter for API requests with adaptive backoff."""
    def __init__(self, calls_per_second: float = 2.0):
        self.delay = 1.0 / calls_per_second
        self.last_call = 0.0
        self._backoff_factor = 1.0

    async def acquire(self):
        """Wait until rate limit allows next request."""
        now = time.monotonic()
        delay = self.delay * self._backoff_factor
        elapsed = now - self.last_call
        if (elapsed < delay):
            await asyncio.sleep(delay - elapsed)
        self.last_call = time.monotonic()

    def increase_backoff(self):
        """Increase backoff factor on failure."""
        self._backoff_factor = min(self._backoff_factor * 1.5, 4.0)

    def reset_backoff(self):
        """Reset backoff factor on success."""
        self._backoff_factor = 1.0


def retry_on_network_error(retries: int = 3, delay: float = 1.0):
    """Retry failed network operations with exponential backoff."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (ClientConnectorError, CelcatCannotConnectError) as exc:
                    last_exception = exc
                    if attempt < retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator
