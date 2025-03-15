"""Event data filter for Celcat calendar.

This module provides functionality to clean and standardize calendar event data
retrieved from Celcat.
It offers various filtering options for each event attribute to facilitate classification.
"""

import logging
import re
from typing import Dict, Any, List, Set
from collections import OrderedDict

from .config import CelcatFilterConfig, FilterType

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

        if FilterType.COURSE_STRIP_REDUNDANT in self.config.filters:
            await self._strip_redundant_courses(events)

        if FilterType.COURSE_GROUP_SIMILAR in self.config.filters:
            await self._group_similar_courses(events)

        if self.config.course_replacements:
            await self._replace_courses(events, self.config.course_replacements)

    async def _filter_course(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to a course name.

        Args:
            event: Event dictionary containing course information
        """
        if FilterType.COURSE_STRIP_MODULES in self.config.filters and event.get(
            "modules"
        ):
            for module in event["modules"]:
                event["course"] = re.sub(
                    re.escape(f" [{module}]"),
                    "",
                    event["course"],
                    flags=re.IGNORECASE,
                )

        if FilterType.COURSE_STRIP_CATEGORY in self.config.filters and event.get(
            "category"
        ):
            event["course"] = re.sub(
                re.escape(f" {event['category']}"),
                "",
                event["course"],
                flags=re.IGNORECASE,
            )

        if FilterType.COURSE_STRIP_PUNCTUATION in self.config.filters:
            event["course"] = re.sub(r"[.,:;!?]", "", event["course"])

        if FilterType.COURSE_TITLE in self.config.filters:
            event["course"] = event["course"].title()

    async def _filter_professors(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to professor names.

        Args:
            event: Event dictionary containing professor information
        """
        if FilterType.PROFESSORS_TITLE in self.config.filters:
            for i in range(len(event["professors"])):
                event["professors"][i] = event["professors"][i].title()

    async def _filter_rooms(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to room names.

        Args:
            event: Event dictionary containing room information
        """
        if FilterType.ROOMS_STRIP_AFTER_NUMBER in self.config.filters:
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

        if FilterType.ROOMS_TITLE in self.config.filters:
            for i in range(len(event["rooms"])):
                event["rooms"][i] = event["rooms"][i].title()

    async def _filter_sites(self, event: Dict[str, Any]) -> None:
        """Apply configured filters to site names.

        Args:
            event: Event dictionary containing site information
        """
        if FilterType.SITES_REMOVE_DUPLICATES in self.config.filters:
            event["sites"] = list(OrderedDict.fromkeys(event["sites"]))

        if FilterType.SITES_TITLE in self.config.filters:
            for i in range(len(event["sites"])):
                event["sites"][i] = event["sites"][i].title()

    async def _strip_redundant_courses(self, events: List[Dict[str, Any]]) -> None:
        """Remove redundant parts from course names across all events.

        Args:
            events: List of event dictionaries
        """
        new_strips = None
        while new_strips != []:
            new_strips = await self._find_new_course_strips(
                events, self.config.course_remembered_strips
            )
            self.config.course_remembered_strips += new_strips
            await self._strip_courses(events, self.config.course_remembered_strips)

    async def _find_new_course_strips(
        self, events: List[Dict[str, Any]], previous_strips: List[str]
    ) -> List[str]:
        """Find new parts of course names that can be stripped.

        Args:
            events: List of event dictionaries
            previous_strips: List of previously identified strips

        Returns:
            List of new words that could be stripped from course names
        """
        courses = await self._get_courses_names(events)
        new_strips = []
        for i in range(len(courses) - 1):
            for j in range(i + 1, len(courses)):
                strips = await self._find_course_strips(
                    courses[i], courses[j]
                ) or await self._find_course_strips(courses[j], courses[i])
                for strip in strips:
                    if strip not in previous_strips and strip not in new_strips:
                        new_strips.append(strip)

        _LOGGER.debug(f"New items to strip: {new_strips}")
        return new_strips

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

    async def _find_course_strips(
        self, smaller_course: str, longer_course: str
    ) -> List[str]:
        """Find parts of the longer course name that can be stripped.

        Args:
            smaller_course: The shorter course name
            longer_course: The longer course name

        Returns:
            List of words that could be stripped from course names
        """
        smaller = smaller_course.lower()
        longer = longer_course.lower()

        if smaller in longer:
            while smaller in longer:
                start = longer.index(smaller)
                end = start + len(smaller)

                while start > 0 and longer[start] != " ":
                    start -= 1
                while end < len(longer) and longer[end] != " ":
                    end += 1

                longer = longer[:start] + longer[end:]
            return longer.split()
        return []

    async def _strip_courses(
        self, events: List[Dict[str, Any]], items_to_strip: List[str]
    ) -> None:
        """Remove specified items from course names.

        Args:
            events: List of event dictionaries
            items_to_strip: List of words to remove from course names
        """
        if self.config.course_strip_redundant:
            _LOGGER.debug(f"Items to strip: {items_to_strip}")
            for event in events:
                pattern_parts = [
                    r"\b" + re.escape(item) + r"\b" for item in items_to_strip
                ]
                pattern = re.compile("|".join(pattern_parts), re.IGNORECASE)
                result = pattern.sub("", event["course"])
                event["course"] = re.sub(r"\s+", " ", result).strip()

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
