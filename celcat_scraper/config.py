"""Configuration classes for Celcat scraper.

This module provides configuration classes used to customize
the behavior of the Celcat scraper.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List

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
class CelcatFilterConfig:
    """Configuration for Celcat data filter.

    Attributes:
        course_title: Whether to convert course names to title case
        course_strip_modules: Whether to remove module codes from course names
        course_strip_category: Whether to remove category prefixes from course names
        course_strip_punctuation: Whether to remove punctuation from course names
        course_group_similar: Whether to group similar course names together
        course_strip_redundant: Whether to remove redundant elements found across multiple events
        course_remembered_strips: List of previously stripped strings to be reapplied in subsequent filter instances
        course_replacements: Dictionary of strings to replace in course names
        professors_title: Whether to convert professor names to title case
        rooms_title: Whether to convert room names to title case
        rooms_strip_after_number: Whether to remove text after room numbers
        sites_title: Whether to convert site names to title case
        sites_remove_duplicates: Whether to remove duplicate sites
    """

    course_title: bool = True
    course_strip_modules: bool = True
    course_strip_category: bool = True
    course_strip_punctuation: bool = False
    course_group_similar: bool = False
    course_strip_redundant: bool = False
    course_remembered_strips: Optional[List[str]] = field(default_factory=list)
    course_replacements: Optional[Dict[str, str]] = field(default_factory=dict)
    professors_title: bool = True
    rooms_title: bool = True
    rooms_strip_after_number: bool = False
    sites_title: bool = True
    sites_remove_duplicates: bool = True


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
    custom_filter: Optional[CelcatFilterConfig] = None
    include_holidays: bool = True
    rate_limit: float = 0.5
    session: Optional[ClientSession] = None
