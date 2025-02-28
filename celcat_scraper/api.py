"""API interaction module for Celcat calendar.

This module provides functions for interacting with Celcat calendar API endpoints.
"""

import logging
from datetime import date, datetime
from typing import Dict, Any, List, Optional

import aiohttp
from aiohttp import ClientConnectorError, ClientResponse, ClientSession

from .config import CelcatConstants
from .exceptions import CelcatCannotConnectError, CelcatInvalidAuthError
from .types import EventData
from .utils import retry_on_network_error

_LOGGER = logging.getLogger(__name__)

async def validate_response(response: ClientResponse, expected_type: str = None) -> Any:
    """Validate server response and return appropriate data type."""
    if response.status != 200:
        error_text = await response.text(encoding='latin1')
        raise CelcatCannotConnectError(
            f"Server returned status {response.status}: {error_text[:200]}"
        )

    if expected_type == "json":
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise CelcatCannotConnectError("Expected JSON response but got different content type")
        return await response.json()

    return await response.text()


async def handle_error_response(response: ClientResponse) -> None:
    """Handle error responses with appropriate exceptions."""
    error_msg = await response.text()
    if response.status == 401:
        raise CelcatInvalidAuthError("Authentication failed")
    elif response.status == 403:
        raise CelcatInvalidAuthError("Access forbidden")
    elif response.status == 429:
        retry_after = int(response.headers.get("Retry-After", 30))
        raise CelcatCannotConnectError(f"Rate limited. Retry after {retry_after} seconds")
    else:
        raise CelcatCannotConnectError(f"HTTP {response.status}: {error_msg}")


async def get_calendar_raw_data(
    session: ClientSession,
    url: str,
    federation_ids: str,
    start_date: date,
    end_date: date
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
        "federationIds[]": federation_ids
    }

    url_calendar_data = url + "/Home/GetCalendarData"
    try:
        async with session.post(url_calendar_data, data=calendar_data) as calendar_response:
            _LOGGER.debug(f"Raw calendar data : {await calendar_response.text()}")

            if calendar_response.status == 200:
                if "application/json" in calendar_response.headers.get("Content-Type", ""):
                    return await calendar_response.json()
                else:
                    error_text = await calendar_response.text()
                    raise CelcatCannotConnectError(
                        f"Expected JSON response but got: {error_text[:200]}"
                    )
            else:
                raise CelcatCannotConnectError("Couldn't retrieve GetCalendarData")
    except ClientConnectorError as exc:
        raise CelcatCannotConnectError("Could not reach specified url") from exc


async def get_side_bar_event_raw_data(
    session: ClientSession,
    url: str,
    event_id: str
) -> dict:
    """Fetch detailed event data by ID."""
    sidebar_data = {
        "eventid": event_id
    }

    url_sidebar_data = url + "/Home/GetSideBarEvent"
    try:
        async with session.post(url_sidebar_data, data=sidebar_data) as sidebar_response:
            if sidebar_response.status == 200:
                if "application/json" in sidebar_response.headers.get("Content-Type", ""):
                    return await sidebar_response.json()
                else:
                    raise CelcatCannotConnectError("Couldn't convert GetSideBarEvent to json")
            else:
                raise CelcatCannotConnectError("Couldn't retrieve GetSideBarEvent")
    except ClientConnectorError as exc:
        raise CelcatCannotConnectError("Could not reach specified url") from exc


@retry_on_network_error()
async def fetch_with_retry(
    session: ClientSession,
    method: str,
    url: str,
    rate_limiter: Any,
    semaphore: Any,
    timeout: Any,
    **kwargs
) -> Any:
    """Make HTTP requests with retry logic."""
    await rate_limiter.acquire()

    async with semaphore:
        for attempt in range(CelcatConstants.MAX_RETRIES):
            try:
                kwargs.setdefault("timeout", timeout)
                kwargs.setdefault("compress", True)

                async with session.request(method, url, **kwargs) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            data = await response.json()
                        else:
                            data = await response.text()

                        rate_limiter.reset_backoff()
                        return data

                    await handle_error_response(response)

            except aiohttp.ClientError as exc:
                rate_limiter.increase_backoff()
                if attempt == CelcatConstants.MAX_RETRIES - 1:
                    raise CelcatCannotConnectError(f"Failed after {CelcatConstants.MAX_RETRIES} attempts") from exc
                await asyncio.sleep(min(2 ** attempt, 10))
