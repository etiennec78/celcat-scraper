"""Celcat Calendar Scraper.

This package provides a complete interface for interacting with Celcat Calendar.
"""

from .config import CelcatConfig, CelcatFilterConfig, CelcatConstants, FilterType
from .exceptions import CelcatError, CelcatCannotConnectError, CelcatInvalidAuthError
from .scraper import CelcatScraperAsync
from .types import EventData

__all__ = [
    "CelcatConfig",
    "CelcatFilterConfig",
    "CelcatConstants",
    "FilterType",
    "CelcatScraperAsync",
    "EventData",
    "CelcatError",
    "CelcatCannotConnectError",
    "CelcatInvalidAuthError",
]
