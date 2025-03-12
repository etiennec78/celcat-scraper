"""Event data filter for Celcat calendar.

This module provides functionality to clean and standardize calendar event data
retrieved from Celcat.
It offers various filtering options for each event attribute to facilitate classification.
"""

import logging
import re
from typing import Dict, Any, List, Set

from .config import CelcatFilterConfig

_LOGGER = logging.getLogger(__name__)


class CelcatFilter:
    """Filter for processing and standardizing Celcat calendar events.

    This class provides methods to clean, standardize, and organize calendar
    event data from Celcat according to the provided configuration.
    """

    def __init__(self, config: CelcatFilterConfig) -> None:
        """Initialize the filter with the provided configuration.

        Args:
            config: Configuration object containing filter settings
        """
        self.config = config

    async def filter_events(self, events: List[Dict[str, Any]]) -> None:
        """Apply all configured filters to the event list.

        This is the main entry point for filtering events. It applies all
        individual filters based on the configuration settings.

        Args:
            events: List of event dictionaries to filter
        """
        _LOGGER.info("Filtering Celcat events")

        for event in events:
            if event.get("course"):
                await self._filter_course(event)

            if event.get("professors"):
                await self._filter_professors(event)

            if event.get("rooms"):
                await self._filter_rooms(event)

            if event.get("sites"):
                await self._filter_sites(event)

        if self.config.course_group_similar:
            await self._group_similar_courses(events)

        if self.config.course_replacements:
            await self._replace_courses(events, self.config.course_replacements)

    async def _filter_course(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to a course name.

        Args:
            event: Event dictionary containing course information
        """
        if self.config.course_strip_modules and event.get("course_module"):
            event["course"] = re.sub(
                re.escape(f" [{event['course_module']}]"),
                "",
                event["course"],
                flags=re.IGNORECASE,
            )

        if self.config.course_strip_category and event.get("category"):
            event["course"] = re.sub(
                re.escape(f" {event['category']}"),
                "",
                event["course"],
                flags=re.IGNORECASE,
            )

        if self.config.course_strip_punctuation:
            event["course"] = re.sub(r"[.,:;!?]", "", event["course"])

        if self.config.course_title:
            event["course"] = event["course"].title()

    async def _filter_professors(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to professor names.

        Args:
            event: Event dictionary containing professor information
        """
        if self.config.professors_title:
            for i in range(len(event["professors"])):
                event["professors"][i] = event["professors"][i].title()

    async def _filter_rooms(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to room names.

        Args:
            event: Event dictionary containing room information
        """
        if self.config.rooms_strip_after_number:
            for i in range(len(event["rooms"])):
                letter = 0
                while (
                    letter < len(event["rooms"][i])
                    and not event["rooms"][i][letter].isnumeric()
                ):
                    letter += 1
                while (
                    letter < len(event["rooms"][i])
                    and not event["rooms"][i][letter].isalpha()
                ):
                    letter += 1
                event["rooms"][i] = event["rooms"][i][:letter].rstrip()

        if self.config.rooms_title:
            for i in range(len(event["rooms"])):
                event["rooms"][i] = event["rooms"][i].title()

    async def _filter_sites(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to site names.

        Args:
            event: Event dictionary containing site information
        """
        if self.config.sites_title:
            for i in range(len(event["sites"])):
                event["sites"][i] = event["sites"][i].title()

    async def _get_courses_names(
        self,
        events: List[Dict[str, Any]],
    ) -> List[str]:
        """Extract unique course names from all events.

        Args:
            events: List of event dictionaries

        Returns:
            List of unique course names
        """
        courses: Set[str] = set()

        for event in events:
            if event.get("course") and event["course"] not in courses:
                courses.add(event["course"])

        return list(courses)

    async def _group_similar_courses(self, events: List[Dict[str, Any]]) -> None:
        """Group similar course names together.

        Args:
            events: List of event dictionaries
        """
        courses = await self._get_courses_names(events)
        replacements = {}

        for i in range(len(courses) - 1):
            courses_corresponding = []
            shortest_course = courses[i]
            for j in range(len(courses)):
                if shortest_course in courses[j]:
                    courses_corresponding.append(courses[j])
                elif courses[j] in shortest_course:
                    courses_corresponding.append(shortest_course)
                    shortest_course = courses[j]

            for course in courses_corresponding:
                replacements[course] = shortest_course

        await self._replace_courses(events, replacements)

    async def _replace_courses(
        self, events: List[Dict[str, Any]], replacements: Dict[str, str]
    ) -> None:
        """Replace course names according to the provided mapping.

        Args:
            events: List of event dictionaries
            replacements: Dictionary mapping old course names to new ones
        """
        for event in events:
            if event.get("course") and event["course"] in replacements:
                event["course"] = replacements[event["course"]]
