"""Celcat Calendar Scraper.

This package provides a complete interface for interacting with Celcat Calendar.
"""

from .config import CelcatConfig, CelcatConstants
from .exceptions import CelcatError, CelcatCannotConnectError, CelcatInvalidAuthError
from .scraper import CelcatScraperAsync
from .types import EventData

__all__ = [
    'CelcatConfig',
    'CelcatConstants',
    'CelcatScraperAsync',
    'EventData',
    'CelcatError',
    'CelcatCannotConnectError',
    'CelcatInvalidAuthError',
]
