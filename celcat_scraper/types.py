"""Type definitions for Celcat scraper.

This module contains type definitions and data structures used
throughout the Celcat scraper.
"""

from datetime import datetime
from typing import List, TypedDict


class EventData(TypedDict):
    """Type definition for event data.

    Represents a calendar event with all its attributes.
    """

    id: str
    start: datetime
    end: datetime
    all_day: bool
    category: str
    course: str
    rooms: List[str]
    professors: List[str]
    modules: List[str]
    department: str
    sites: List[str]
    faculty: str
    notes: str
