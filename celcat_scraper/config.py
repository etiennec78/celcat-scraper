"""Configuration classes for Celcat scraper.

This module provides configuration classes used to customize
the behavior of the Celcat scraper.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Set

from aiohttp import ClientSession


class CelcatConstants:
    """Constants for Celcat scraper configuration."""

    MAX_RETRIES = 3
    CONCURRENT_REQUESTS = 5
    TIMEOUT = 30
    COMPRESSION_TYPES = ["gzip", "deflate", "br"]
    CONNECTION_POOL_SIZE = 100
    CONNECTION_KEEP_ALIVE = 120


class FilterType(Enum):
    """Available filter types for Celcat data."""

    COURSE_TITLE = "course_title"
    COURSE_STRIP_MODULES = "course_strip_modules"
    COURSE_STRIP_CATEGORY = "course_strip_category"
    COURSE_STRIP_PUNCTUATION = "course_strip_punctuation"
    COURSE_GROUP_SIMILAR = "course_group_similar"
    COURSE_STRIP_REDUNDANT = "course_strip_redundant"
    PROFESSORS_TITLE = "professors_title"
    ROOMS_TITLE = "rooms_title"
    ROOMS_STRIP_AFTER_NUMBER = "rooms_strip_after_number"
    SITES_TITLE = "sites_title"
    SITES_REMOVE_DUPLICATES = "sites_remove_duplicates"


@dataclass
class CelcatFilterConfig:
    """Configuration for Celcat data filter.

    Attributes:
        filters: Set of filters to apply
        course_remembered_strips: List of previously stripped strings to be reapplied in subsequent filter instances
        course_replacements: Dictionary of strings to replace in course names
    """

    filters: Set[FilterType] = field(default_factory=set)
    course_remembered_strips: List[str] = field(default_factory=list)
    course_replacements: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def with_defaults(cls) -> "CelcatFilterConfig":
        """Create a filter config with default settings."""
        return cls(
            filters={
                FilterType.COURSE_TITLE,
                FilterType.COURSE_STRIP_MODULES,
                FilterType.COURSE_STRIP_CATEGORY,
                FilterType.PROFESSORS_TITLE,
                FilterType.ROOMS_TITLE,
                FilterType.SITES_TITLE,
                FilterType.SITES_REMOVE_DUPLICATES,
            }
        )


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
    filter_config: CelcatFilterConfig = field(default_factory=CelcatFilterConfig.with_defaults)
    include_holidays: bool = True
    rate_limit: float = 0.5
    session: Optional[ClientSession] = None
