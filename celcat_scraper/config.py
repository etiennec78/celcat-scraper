"""Configuration classes for Celcat scraper.

This module provides configuration classes used to customize
the behavior of the Celcat scraper.
"""

from dataclasses import dataclass
from typing import Optional

from aiohttp import ClientSession

class CelcatConstants:
    """Constants for Celcat scraper configuration."""
    MAX_RETRIES = 3
    CONCURRENT_REQUESTS = 5
    TIMEOUT = 30
    COMPRESSION_TYPES = ["gzip", "deflate", "br"]
    CONNECTION_POOL_SIZE = 100
    CONNECTION_KEEP_ALIVE = 120

@dataclass
class CelcatConfig:
    """Configuration for Celcat scraper.

    Attributes:
        url: Base URL for Celcat service
        username: Login username
        password: Login password
        include_holidays: Whether to include holidays in the calendar
        rate_limit: Minimum seconds between requests
        session: Optional aiohttp ClientSession to reuse
    """
    url: str
    username: str
    password: str
    include_holidays: bool = True
    rate_limit: float = 0.5
    session: Optional[ClientSession] = None
