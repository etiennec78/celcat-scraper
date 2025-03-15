"""Main Celcat scraper implementation.

This module provides the main scraper class for interacting with Celcat calendar.
"""

import asyncio
import html
import json
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from aiohttp import ClientSession, TCPConnector

from .api import CelcatAPI
from .filter import CelcatFilter
from .auth import authenticate
from .config import CelcatConfig, CelcatConstants
from .exceptions import CelcatCannotConnectError, CelcatError
from .types import EventData

_LOGGER = logging.getLogger(__name__)


class CelcatScraperAsync:
    """Asynchronous scraper for interacting with Celcat calendar.

    The scraper handles authentication, rate limiting, and data retrieval
    from Celcat calendar systems. It implements connection pooling, automatic
    retries, and adaptive rate limiting for optimal performance.

    Example:
        async with CelcatScraperAsync(config) as scraper:
            events = await scraper.get_calendar_events(
                start=date.today(),
                end=start + timedelta(days=7)
            )
    """

    def __init__(self, config: CelcatConfig) -> None:
        """Initialize the Celcat scraper.

        Args:
            config: Configuration for Celcat scraper including URL and credentials
        """
        self._validate_config(config)
        self.config = config
        self.filter = CelcatFilter(config.filter_config)
        self.api = CelcatAPI(config)
        self.federation_ids: Optional[str] = None
        self.session: Optional[ClientSession] = config.session
        self._external_session = bool(config.session)
        self.logged_in: bool = False

        self._headers = {
            "Accept-Encoding": ", ".join(CelcatConstants.COMPRESSION_TYPES),
            "Connection": "keep-alive",
            "Keep-Alive": str(CelcatConstants.CONNECTION_KEEP_ALIVE),
        }

    async def __aenter__(self) -> "CelcatScraperAsync":
        """Async context manager entry with automatic login."""
        if not self.logged_in:
            await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    @staticmethod
    def _validate_config(config: CelcatConfig) -> None:
        """Ensure configuration parameters are valid."""
        if not all([config.url, config.username, config.password]):
            raise ValueError("All configuration parameters must be non-empty strings")

        parsed_url = urlparse(config.url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")

        config.url = config.url.rstrip("/")

    @asynccontextmanager
    async def _session_context(self) -> ClientSession:
        """Manage session lifecycle with proper connection settings."""
        if not self.session:
            self.session = ClientSession(
                connector=TCPConnector(
                    limit=CelcatConstants.CONNECTION_POOL_SIZE,
                    enable_cleanup_closed=True,
                    force_close=False,
                    keepalive_timeout=CelcatConstants.CONNECTION_KEEP_ALIVE,
                ),
                headers=self._headers,
                timeout=self._timeout,
            )
        try:
            yield self.session
        finally:
            if not self._external_session and not self.session.closed:
                await self._cleanup_session()

    async def _cleanup_session(self) -> None:
        """Clean up and close the aiohttp session."""
        if self.session and not self._external_session:
            with suppress(Exception):
                await self.session.close()
            self.session = None
            self.logged_in = False

    async def close(self) -> None:
        """Close scraper and clean up resources."""
        if not self.session:
            return

        if self._external_session and self.logged_in:
            try:
                logout_url = self.config.url + "/Login/Logout"
                _LOGGER.info(f"Sending logout request to {logout_url}")
                async with self.session.get(logout_url) as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully logged out from Celcat")
                    else:
                        _LOGGER.warning(f"Logout returned status {response.status}")
                self.logged_in = False
            except Exception as e:
                _LOGGER.error(f"Failed to properly logout from Celcat: {e}")
        else:
            _LOGGER.info("Closing Celcat scraper session")
            await self._cleanup_session()

    async def login(self) -> bool:
        """Authenticate to Celcat.

        Returns:
            bool: True if login was successful.

        Raises:
            CelcatCannotConnectError: If connection fails
            CelcatInvalidAuthError: If credentials are invalid
        """
        try:
            async with self._session_context() as session:
                success, federation_ids = await authenticate(
                    session, self.config.url, self.config.username, self.config.password
                )

                self.federation_ids = federation_ids
                self.logged_in = True
                return True

        except Exception as exc:
            await self._cleanup_session()
            if isinstance(exc, (CelcatError, ValueError)):
                raise
            raise CelcatCannotConnectError(
                "Failed to connect to Celcat service"
            ) from exc

    async def _process_event(self, event: dict) -> EventData:
        """Convert raw event data into EventData object."""
        try:
            event_start = datetime.fromisoformat(event["start"])
            event_end = (
                event_start.replace(hour=23, minute=59, second=59)
                if event["allDay"]
                else datetime.fromisoformat(event["end"])
            )

            processed_event: EventData = {
                "id": event["id"],
                "start": event_start,
                "end": event_end,
                "all_day": event.get("allDay", False),
                "category": event.get("eventCategory", "") or "",
                "course": "",
                "rooms": [],
                "professors": [],
                "modules": event.get("modules", []) or [],
                "department": event.get("department", "") or "",
                "sites": event.get("sites", []) or [],
                "faculty": event.get("faculty", "") or "",
                "notes": "",
            }

            event_data = await self.api.get_side_bar_event_raw_data(
                self.session, self.config.url, event["id"]
            )

            for element in event_data["elements"]:
                if element["entityType"] == 100 and processed_event["course"] == "":
                    processed_event["course"] = element["content"]
                elif element["entityType"] == 101:
                    processed_event["professors"].append(element["content"])
                elif element["entityType"] == 102:
                    processed_event["rooms"].append(element["content"])
                elif element["isNotes"] and element.get("content"):
                    processed_event["notes"] = element["content"]

            return processed_event
        except Exception as exc:
            _LOGGER.error(f"Failed to process event {event['id']}: {exc}")
            raise

    async def _process_event_batch(self, events: List[dict]) -> List[EventData]:
        """Process multiple events concurrently."""

        async def process_single_event(event: dict) -> Optional[EventData]:
            try:
                if not event["allDay"] or self.config.include_holidays:
                    return await self._process_event(event)
            except Exception as exc:
                _LOGGER.error(f"Failed to process event {event.get('id')}: {exc}")
            return None

        tasks = [process_single_event(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        _LOGGER.info(f"Finished processing new events with {len(events)} requests")
        events = [r for r in results if r is not None and not isinstance(r, Exception)]

        await self.filter.filter_events(events)
        return events

    @staticmethod
    def serialize_events(events: List[EventData], file_path: str) -> None:
        """Serialize events to JSON file.

        Args:
            events: List of EventData to serialize
            file_path: Path where to save the JSON file
        """

        def datetime_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(events, f, default=datetime_handler, ensure_ascii=False, indent=2)

    @staticmethod
    def deserialize_events(file_path: str) -> List[EventData]:
        """Deserialize events from JSON file.

        Args:
            file_path: Path to the JSON file

        Returns:
            List of EventData objects
        """
        if not Path(file_path).exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for event in data:
            event["start"] = datetime.fromisoformat(event["start"])
            event["end"] = datetime.fromisoformat(event["end"])

        return data

    async def get_calendar_events(
        self, start: date, end: date, previous_events: Optional[List[EventData]] = None
    ) -> List[EventData]:
        """Get calendar events for a specified time period.

        This method efficiently retrieves calendar events by:
        - Using connection pooling for better performance
        - Implementing automatic retries for network errors
        - Caching and reusing previous event data when possible
        - Using adaptive rate limiting to prevent server overload

        Args:
            start: Start date
            end: End date
            previous_events: Optional cached events for optimization

        Returns:
            List of calendar events with full details

        Raises:
            CelcatCannotConnectError: On connection issues
            CelcatInvalidAuthError: On authentication failure
            ValueError: If start date is after end date
        """
        if start > end:
            raise ValueError("Start time cannot be more recent than end time")

        if not self.logged_in:
            await self.login()

        _LOGGER.info("Retrieving calendar events for period %s to %s", start, end)

        calendar_raw_data = await self.api.get_calendar_raw_data(
            self.session, self.config.url, self.federation_ids, start, end
        )
        calendar_raw_data.sort(key=lambda x: x["start"])

        if not previous_events:
            return await self._process_event_batch(calendar_raw_data)

        _LOGGER.info("Comparing remote and local calendar to optimize requests")

        final_events = []
        previous_events = previous_events.copy()
        total_requests = 0

        start_datetime = datetime.combine(start, datetime.min.time())
        end_datetime = datetime.combine(end, datetime.max.time())

        out_of_range_events = []
        in_range_events = []
        for event in previous_events:
            if event["all_day"] and not self.config.include_holidays:
                continue
            elif event["end"] < start_datetime or event["start"] > end_datetime:
                out_of_range_events.append(event)
            else:
                in_range_events.append(event)

        for raw_event in calendar_raw_data:
            event_start = datetime.fromisoformat(raw_event["start"])

            if raw_event["allDay"]:
                if not self.config.include_holidays:
                    continue
                event_end = event_start.replace(hour=23, minute=59, second=59)
            else:
                event_end = datetime.fromisoformat(raw_event["end"])

            matching_event = None
            for prev_event in in_range_events:
                if (
                    raw_event["id"] == prev_event["id"]
                    and (
                        (raw_event["allDay"] and prev_event["all_day"])
                        or (
                            event_start == prev_event["start"]
                            and event_end == prev_event["end"]
                        )
                    )
                    and (raw_event["eventCategory"] == prev_event["category"])
                    and (raw_event["modules"] or [] == prev_event["modules"])
                    and (
                        prev_event["all_day"]
                        or (
                            prev_event["rooms"]
                            and prev_event["rooms"][0].lower()
                            in html.unescape(raw_event["description"]).lower()
                        )
                    )
                ):
                    matching_event = prev_event
                    in_range_events.remove(prev_event)
                    break

            if matching_event:
                final_events.append(matching_event)
                _LOGGER.debug("Event data recycled")
            else:
                processed_event = await self._process_event(raw_event)
                final_events.append(processed_event)
                total_requests += 1
                _LOGGER.debug("Event data requested")

        final_events.extend(out_of_range_events)
        _LOGGER.info(f"Finished processing events with {total_requests} requests")

        await self.filter.filter_events(final_events)
        return final_events
