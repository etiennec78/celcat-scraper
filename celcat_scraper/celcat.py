"""Asynchronous scraper for Celcat Calendar.

This module provides a complete async interface for interacting with Celcat Calendar.

Classes:
    CelcatConstants: Configuration constants
    CelcatScraperAsync: Main scraper implementation
    CelcatConfig: Scraper configuration
"""

from __future__ import annotations
from aiohttp import ClientConnectorError, ClientResponse, ClientSession, ClientTimeout
import asyncio
from bs4 import BeautifulSoup
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, date
from functools import wraps
import html
import logging
import time
from typing import Any, Dict, List, Optional, TypedDict
from urllib.parse import urlparse

from .exceptions import (
    CelcatCannotConnectError,
    CelcatError,
    CelcatInvalidAuthError,
)

_LOGGER = logging.getLogger(__name__)

class CelcatConstants:
    """Constants for Celcat scraper configuration."""
    MAX_RETRIES = 3
    CONCURRENT_REQUESTS = 5
    COMPRESSION_TYPES = ['gzip', 'deflate', 'br']
    CONNECTION_POOL_SIZE = 100
    CONNECTION_KEEP_ALIVE = 120

class EventData(TypedDict):
    """Type definition for event data."""
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
    notes: List[str]
    status: str
    mark: Any

@dataclass
class CelcatConfig:
    """Configuration for Celcat scraper.
    
    Attributes:
        url: Base URL for Celcat service
        username: Login username
        password: Login password
        include_holidays: Whether to include holidays in the calendar
        rate_limit: Minimum seconds between requests
    """
    url: str
    username: str
    password: str
    include_holidays: bool = True
    rate_limit: float = 0.5

class RateLimiter:
    """Rate limiter for API requests with adaptive backoff."""
    def __init__(self, calls_per_second: float = 2.0):
        self.delay = 1.0 / calls_per_second
        self.last_call = 0.0
        self._backoff_factor = 1.0

    async def acquire(self):
        """Wait until rate limit allows next request."""
        now = time.monotonic()
        delay = self.delay * self._backoff_factor
        elapsed = now - self.last_call
        if (elapsed < delay):
            await asyncio.sleep(delay - elapsed)
        self.last_call = time.monotonic()

    def increase_backoff(self):
        """Increase backoff factor on failure."""
        self._backoff_factor = min(self._backoff_factor * 1.5, 4.0)

    def reset_backoff(self):
        """Reset backoff factor on success."""
        self._backoff_factor = 1.0

def retry_on_network_error(retries: int = 3, delay: float = 1.0):
    """Retry failed network operations with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (ClientConnectorError, CelcatCannotConnectError) as exc:
                    last_exception = exc
                    if attempt < retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator

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
        self.federation_ids: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.logged_in: bool = False
        
        self._rate_limiter = RateLimiter(1/config.rate_limit)
        self._timeout = ClientTimeout(total=30)
        self._semaphore = asyncio.Semaphore(CelcatConstants.CONCURRENT_REQUESTS)
        self._conn_kwargs = {
            'limit': CelcatConstants.CONNECTION_POOL_SIZE,
            'enable_cleanup_closed': True
        }
        self._headers = {
            'Accept-Encoding': ', '.join(CelcatConstants.COMPRESSION_TYPES),
            'Connection': 'keep-alive',
            'Keep-Alive': str(CelcatConstants.CONNECTION_KEEP_ALIVE)
        }

    async def __aenter__(self) -> CelcatScraperAsync:
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

        config.url = config.url.rstrip('/')

    @asynccontextmanager
    async def _session_context(self) -> ClientSession:
        """Manage session lifecycle with proper connection settings."""
        if not self.session:
            self.session = ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=CelcatConstants.CONNECTION_POOL_SIZE,
                    enable_cleanup_closed=True,
                    force_close=False,
                    keepalive_timeout=CelcatConstants.CONNECTION_KEEP_ALIVE
                ),
                headers=self._headers,
                timeout=self._timeout
            )
        try:
            yield self.session
        finally:
            if not self.session.closed:
                await self._cleanup_session()

    async def _cleanup_session(self) -> None:
        """Clean up and close the aiohttp session."""
        if self.session:
            with suppress(Exception):
                await self.session.close()
            self.session = None
            self.logged_in = False

    async def close(self) -> None:
        """Close scraper and clean up resources."""
        _LOGGER.info('Closing Celcat scraper session')
        await self._cleanup_session()

    async def login(self) -> bool:
        """Authenticate to Celcat.

        Returns:
            bool: True if login was successful.

        Raises:
            CelcatCannotConnectError: If connection fails
            CelcatInvalidAuthError: If credentials are invalid
        """
        _LOGGER.debug("Initiating authentication with Celcat service")
        
        try:
            self.session = ClientSession()
            url_login_page = f"{self.config.url}/calendar/LdapLogin"

            async with self.session.get(url_login_page) as response:
                page_content = await self._validate_response(response)
                soup = BeautifulSoup(page_content, "html.parser")
                token_element = soup.find("input", {"name": "__RequestVerificationToken"})
                
                if not token_element or "value" not in token_element.attrs:
                    raise CelcatCannotConnectError("Could not retrieve CSRF token")

                login_data = {
                    "Name": self.config.username,
                    "Password": self.config.password,
                    "__RequestVerificationToken": token_element["value"]
                }

                async with self.session.post(
                    f"{self.config.url}/calendar/LdapLogin/Logon",
                    data=login_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                ) as response:
                    page_content = await self._validate_response(response)
                    return await self._process_login_response(response.url, page_content)

        except Exception as exc:
            await self._cleanup_session()
            if isinstance(exc, (CelcatError, ValueError)):
                raise
            raise CelcatCannotConnectError("Failed to connect to Celcat service") from exc

    async def _process_login_response(self, response_url: str, page_content: str) -> bool:
        """Process login response and extract federation IDs."""
        soup = BeautifulSoup(page_content, 'html.parser')
        login_button = soup.find('a', class_='logInOrOut')
        
        if not login_button or not login_button.span:
            raise CelcatInvalidAuthError("Could not determine login state")
            
        login_button_state = login_button.span.text

        if login_button_state == 'Log Out':
            federation_ids = next(
                (param.split('=')[1] for param in str(response_url).split('&') 
                 if param.startswith('FederationIds=')), 
                None
            )

            if federation_ids is None:
                raise CelcatCannotConnectError('Federation ids could not be retrieved')
                
            self.federation_ids = federation_ids
            self.logged_in = True
            _LOGGER.debug("Successfully logged in to Celcat")
            return True
        
        raise CelcatInvalidAuthError("Login failed - invalid credentials")

    @retry_on_network_error()
    async def _fetch_with_retry(self, method: str, url: str, **kwargs) -> Any:
        """Make HTTP requests with retry logic."""
        await self._rate_limiter.acquire()
        
        async with self._semaphore:
            for attempt in range(CelcatConstants.MAX_RETRIES):
                try:
                    kwargs.setdefault('timeout', self._timeout)
                    kwargs.setdefault('compress', True)
                    
                    async with self._session_context() as session:
                        async with session.request(method, url, **kwargs) as response:
                            if response.status == 200:
                                content_type = response.headers.get('Content-Type', '')
                                if 'application/json' in content_type:
                                    data = await response.json()
                                else:
                                    data = await response.text()
                                
                                self._rate_limiter.reset_backoff()
                                return data
                            
                            await self._handle_error_response(response)
                            
                except aiohttp.ClientError as exc:
                    self._rate_limiter.increase_backoff()
                    if attempt == CelcatConstants.MAX_RETRIES - 1:
                        raise CelcatCannotConnectError(f"Failed after {CelcatConstants.MAX_RETRIES} attempts") from exc
                    await asyncio.sleep(min(2 ** attempt, 10))

    async def _validate_response(self, response: ClientResponse, expected_type: str = None) -> Any:
        """Validate server response and return appropriate data type."""
        if response.status != 200:
            error_text = await response.text()
            raise CelcatCannotConnectError(
                f"Server returned status {response.status}: {error_text[:200]}"
            )

        if expected_type == "json":
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise CelcatCannotConnectError("Expected JSON response but got different content type")
            return await response.json()
        
        return await response.text()

    async def _handle_error_response(self, response: ClientResponse) -> None:
        """Handle error responses with appropriate exceptions."""
        error_msg = await response.text()
        if response.status == 401:
            raise CelcatInvalidAuthError("Authentication failed")
        elif response.status == 403:
            raise CelcatInvalidAuthError("Access forbidden")
        elif response.status == 429:
            retry_after = int(response.headers.get('Retry-After', 30))
            raise CelcatCannotConnectError(f"Rate limited. Retry after {retry_after} seconds")
        else:
            raise CelcatCannotConnectError(f"HTTP {response.status}: {error_msg}")

    async def _get_calendar_raw_data(self, start: date, end: date) -> Dict[str, Any]:
        """Fetch raw calendar data for given time period."""
        _LOGGER.info('Getting calendar raw data')

        if not self.logged_in:
            await self.login()

        if start > end:
            raise ValueError("Start time cannot be more recent than end time")

        calendar_data = {
            'start': start.strftime('%Y-%m-%d'),
            'end': end.strftime('%Y-%m-%d'),
            'resType': '104',
            'calView': 'month',
            'federationIds[]': self.federation_ids
        }

        url_calendar_data = self.config.url + '/calendar/Home/GetCalendarData'
        try:
            async with self.session.post(url_calendar_data, data=calendar_data) as calendar_response:

                _LOGGER.debug(f'Raw calendar data : {await calendar_response.text()}')

                if calendar_response.status == 200:
                    if 'application/json' in calendar_response.headers.get('Content-Type', ''):
                        return await calendar_response.json()
                    else:
                        error_text = await calendar_response.text()
                        raise CelcatCannotConnectError(
                            f"Expected JSON response but got: {error_text[:200]}"
                        )
                else:
                    raise CelcatCannotConnectError("Couldn't retrieve GetCalendarData")
        except ClientConnectorError as exc:
            raise CelcatCannotConnectError('Could not reach specified url') from exc

    async def _get_side_bar_event_raw_data(self, event_id: str) -> dict:
        """Fetch detailed event data by ID."""
        if not self.logged_in:
            await self.login()

        sidebar_data = {
            'eventid': event_id
        }

        url_sidebar_data = self.config.url + '/calendar/Home/GetSideBarEvent'
        try:
            async with self.session.post(url_sidebar_data, data=sidebar_data) as sidebar_response:
                if sidebar_response.status == 200:
                    if 'application/json' in sidebar_response.headers.get('Content-Type', ''):
                        return await sidebar_response.json()
                    else:
                        raise CelcatCannotConnectError("Couldn't convert GetSideBarEvent to json")
                else:
                    raise CelcatCannotConnectError("Couldn't retrieve GetSideBarEvent")
        except ClientConnectorError as exc:
            raise CelcatCannotConnectError('Could not reach specified url') from exc

    async def _process_event(self, event: dict) -> EventData:
        """Convert raw event data into EventData object."""
        try:
            event_start = datetime.fromisoformat(event['start'])
            event_end = (
                event_start.replace(hour=23, minute=59, second=59)
                if event['allDay']
                else datetime.fromisoformat(event['end'])
            )

            cleaned_sites = list({site.title() for site in (event.get('sites') or []) if site})

            processed_event: EventData = {
                'id': str(event['id']),
                'start': event_start,
                'end': event_end,
                'all_day': bool(event.get('allDay', False)),
                'category': str(event.get('eventCategory', '')),
                'course': '',
                'rooms': [],
                'professors': [],
                'modules': list(event.get('modules', [])),
                'department': str(event.get('department', '')),
                'sites': cleaned_sites,
                'faculty': str(event.get('faculty', '')),
                'notes': [],
                'status': str(event.get('registerStatus', None)),
                'mark': event.get('studentMark', None),
            }

            event_data = await self._get_side_bar_event_raw_data(event['id'])

            for element in event_data['elements']:
                if element['entityType'] == 100 and processed_event['course'] == '':
                    processed_event['course'] = element['content'].replace(f' [{element['federationId']}]', '').replace(f' {event['eventCategory']}', '').title()
                elif element['entityType'] == 101:
                    processed_event['professors'].append(element['content'].title())
                elif element['entityType'] == 102:
                    processed_event['rooms'].append(element['content'].title())
                elif element['isNotes'] and element['content'] is not None:
                    processed_event['notes'].append(element['content'])

            return processed_event
        except Exception as exc:
            _LOGGER.error(f"Failed to process event {event['id']}: {exc}")
            raise

    async def _process_event_batch(self, events: List[dict]) -> List[EventData]:
        """Process multiple events concurrently."""
        async def process_single_event(event: dict) -> Optional[EventData]:
            try:
                if not event['allDay'] or self.config.include_holidays:
                    return await self._process_event(event)
            except Exception as exc:
                _LOGGER.error(f"Failed to process event {event.get('id')}: {exc}")
            return None

        tasks = [process_single_event(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if r is not None and not isinstance(r, Exception)]

    @staticmethod
    def serialize_events(events: List[EventData], file_path: str) -> None:
        """Serialize events to JSON file.
        
        Args:
            events: List of EventData to serialize
            file_path: Path where to save the JSON file
        """
        import json

        def datetime_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(events, f, default=datetime_handler, ensure_ascii=False, indent=2)

    @staticmethod
    def deserialize_events(file_path: str) -> List[EventData]:
        """Deserialize events from JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            List of EventData objects
        """
        import json
        from pathlib import Path

        if not Path(file_path).exists():
            return []

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for event in data:
            event['start'] = datetime.fromisoformat(event['start'])
            event['end'] = datetime.fromisoformat(event['end'])
            
        return data

    async def get_calendar_events(
        self,
        start: date,
        end: date,
        previous_events: Optional[List[EventData]] = None
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
        
        calendar_raw_data = await self._get_calendar_raw_data(start, end)
        calendar_raw_data.sort(key=lambda x: x['start'])
        
        if not previous_events:
            _LOGGER.info(f'Finished processing new events with {len(calendar_raw_data)} requests')
            return await self._process_event_batch(calendar_raw_data)
            
        _LOGGER.info('Comparing remote and local calendar to optimize requests')
        
        final_events = []
        previous_events = previous_events.copy()
        total_requests = 0

        start_datetime = datetime.combine(start, datetime.min.time())
        end_datetime = datetime.combine(end, datetime.max.time())

        out_of_range_events = [event for event in previous_events
                                if event['end'] < start_datetime or event['start'] > end_datetime]

        if out_of_range_events:
            in_range_events = [event for event in previous_events
                                if event['end'] >= start_datetime and event['start'] <= end_datetime]
        else:
            in_range_events = previous_events

        for raw_event in calendar_raw_data:
            event_start = datetime.fromisoformat(raw_event['start'])
            
            if raw_event['allDay']:
                if not self.config.include_holidays:
                    continue
                event_end = event_start.replace(hour=23, minute=59, second=59)
            else:
                event_end = datetime.fromisoformat(raw_event['end'])

            matching_event = None
            for prev_event in previous_events:
                if (raw_event['id'] == prev_event['id'] and
                    event_start == prev_event['start'].replace(tzinfo=None) and 
                    event_end == prev_event['end'].replace(tzinfo=None) and
                    prev_event['rooms'] and prev_event['rooms'][0].lower() in html.unescape(raw_event['description']).lower()):
                    matching_event = prev_event
                    in_range_events.remove(prev_event)
                    break

            if matching_event:
                final_events.append(matching_event)
                _LOGGER.debug('Event data recycled')
            else:
                processed_event = await self._process_event(raw_event)
                final_events.append(processed_event)
                total_requests += 1
                _LOGGER.debug('Event data requested')

        final_events.extend(out_of_range_events)

        _LOGGER.info(f'Finished processing events with {total_requests} requests')
        return sorted(final_events, key=lambda x: x['start'])
