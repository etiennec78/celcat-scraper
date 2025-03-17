"""Authentication handling for Celcat calendar.

This module provides authentication functionality for Celcat calendar,
including login processes and session management.
"""

import logging
from typing import Tuple, Optional

from aiohttp import ClientSession
from bs4 import BeautifulSoup

from .exceptions import CelcatCannotConnectError, CelcatInvalidAuthError, CelcatError

_LOGGER = logging.getLogger(__name__)


async def authenticate(
    session: ClientSession, url: str, username: str, password: str
) -> Tuple[bool, Optional[str]]:
    """Authenticate to Celcat.

    Args:
        session: The aiohttp session
        url: Base URL for Celcat service
        username: Login username
        password: Login password

    Returns:
        Tuple of (success, federation_ids)

    Raises:
        CelcatCannotConnectError: If connection fails
        CelcatInvalidAuthError: If credentials are invalid
    """
    _LOGGER.debug("Initiating authentication with Celcat service")

    try:
        url_login_page = f"{url}/LdapLogin"

        async with session.get(url_login_page) as response:
            if response.status != 200:
                error_text = await response.text(encoding="latin1")
                raise CelcatCannotConnectError(
                    f"Server returned status {response.status}: {error_text[:200]}"
                )

            page_content = await response.text()
            soup = BeautifulSoup(page_content, "html.parser")
            token_element = soup.find("input", {"name": "__RequestVerificationToken"})

            if not token_element or "value" not in token_element.attrs:
                raise CelcatCannotConnectError("Could not retrieve CSRF token")

            login_data = {
                "Name": username,
                "Password": password,
                "__RequestVerificationToken": token_element["value"],
            }

            async with session.post(
                f"{url}/LdapLogin/Logon",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text(encoding="latin1")
                    raise CelcatCannotConnectError(
                        f"Server returned status {response.status}: {error_text[:200]}"
                    )

                page_content = await response.text()
                return _process_login_response(response.url, page_content)

    except Exception as exc:
        if isinstance(exc, (CelcatError, ValueError)):
            raise
        raise CelcatCannotConnectError("Failed to connect to Celcat service") from exc


def _process_login_response(
    response_url, page_content: str
) -> Tuple[bool, Optional[str]]:
    """Process login response and extract federation IDs.

    Returns:
        Tuple of (success, federation_ids)
    """
    soup = BeautifulSoup(page_content, "html.parser")
    login_button = soup.find("a", class_="logInOrOut")

    if not login_button or not login_button.span:
        raise CelcatInvalidAuthError("Could not determine login state")

    login_button_state = login_button.span.text

    if login_button_state == "Log Out":
        federation_ids = next(
            (
                param.split("=")[1]
                for param in str(response_url).split("&")
                if param.startswith("FederationIds=")
            ),
            None,
        )

        if federation_ids is None:
            _LOGGER.debug(
                "FederationIds could not be retrieved. Trying to extract from page"
            )
            extracted = soup.find("span", class_="small")
            if extracted:
                federation_ids = extracted.text.lstrip("-").strip()
                if not federation_ids.isdigit():
                    raise CelcatCannotConnectError(
                        f"Federation ids could not be extracted from '{federation_ids}'"
                    )
            else:
                raise CelcatCannotConnectError(
                    "Federation ids class could not be found"
                )

        _LOGGER.debug("Successfully logged in to Celcat")
        return True, federation_ids

    raise CelcatInvalidAuthError("Login failed - invalid credentials")
