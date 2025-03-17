"""API interaction module for Celcat calendar.

This module provides functions for interacting with Celcat calendar API endpoints.
"""

import logging
import asyncio
from datetime import date
from typing import Dict, Any, List

from aiohttp import ClientResponse, ClientSession, ClientError

from .config import CelcatConstants, CelcatConfig
from .exceptions import CelcatCannotConnectError, CelcatInvalidAuthError
from .utils import RateLimiter

_LOGGER = logging.getLogger(__name__)


class CelcatAPI:
    """Class for interacting with Celcat Calendar API."""

    def __init__(self, config: CelcatConfig):
        """Initialize the Celcat API client."""
        self.rate_limiter = RateLimiter(config.rate_limit)
        self.semaphore = asyncio.Semaphore(CelcatConstants.CONCURRENT_REQUESTS)
        self.timeout = CelcatConstants.TIMEOUT

    async def validate_response(
        self, response: ClientResponse, expected_type: str = None
    ) -> Any:
        """Validate server response and return appropriate data type."""
        if response.status != 200:
            error_text = await response.text(encoding="latin1")
            raise CelcatCannotConnectError(
                f"Server returned status {response.status}: {error_text[:200]}"
            )

        if expected_type == "json":
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise CelcatCannotConnectError(
                    "Expected JSON response but got different content type"
                )
            return await response.json()

        return await response.text()

    async def handle_error_response(self, response: ClientResponse) -> None:
        """Handle error responses with appropriate exceptions."""
        error_msg = await response.text()
        if response.status == 401:
            raise CelcatInvalidAuthError("Authentication failed")
        elif response.status == 403:
            raise CelcatInvalidAuthError("Access forbidden")
        elif response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 30))
            self.rate_limiter.increase_backoff()
            raise CelcatCannotConnectError(
                f"Rate limited. Retry after {retry_after} seconds"
            )
        else:
            raise CelcatCannotConnectError(f"HTTP {response.status}: {error_msg}")

    async def get_calendar_raw_data(
        self,
        session: ClientSession,
        url: str,
        federation_ids: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Fetch raw calendar data for given time period."""
        _LOGGER.info("Getting calendar raw data")

        if start_date > end_date:
            raise ValueError("Start time cannot be more recent than end time")

        calendar_data = {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "resType": "104",
            "calView": "month",
            "federationIds[]": federation_ids,
        }

        url_calendar_data = url + "/Home/GetCalendarData"

        return await self.fetch_with_retry(
            session, "POST", "json", url_calendar_data, data=calendar_data
        )

    async def get_side_bar_event_raw_data(
        self, session: ClientSession, url: str, event_id: str
    ) -> dict:
        """Fetch detailed event data by ID."""
        sidebar_data = {"eventid": event_id}

        url_sidebar_data = url + "/Home/GetSideBarEvent"

        return await self.fetch_with_retry(
            session, "POST", "json", url_sidebar_data, data=sidebar_data
        )

    async def fetch_with_retry(
        self,
        session: ClientSession,
        method: str,
        expected_type: str,
        url: str,
        **kwargs,
    ) -> Any:
        """Make HTTP requests with retry logic."""
        await self.rate_limiter.acquire()

        async with self.semaphore:
            for attempt in range(CelcatConstants.MAX_RETRIES):
                try:
                    kwargs.setdefault("timeout", self.timeout)

                    async with session.request(method, url, **kwargs) as response:
                        if response.status == 200:
                            content_type = response.headers.get("Content-Type", "")

                            if expected_type == "json":
                                if "application/json" in content_type:
                                    data = await response.json()
                                else:
                                    raise CelcatCannotConnectError(
                                        f"Expected JSON response but got different content type: {content_type}"
                                    )
                            else:
                                data = await response.text()

                            self.rate_limiter.reset_backoff()
                            return data

                        await self.handle_error_response(response)

                except ClientError as exc:
                    self.rate_limiter.increase_backoff()
                    if attempt == CelcatConstants.MAX_RETRIES - 1:
                        raise CelcatCannotConnectError(
                            f"Failed after {CelcatConstants.MAX_RETRIES} attempts"
                        ) from exc
                    await asyncio.sleep(min(2**attempt, 10))
