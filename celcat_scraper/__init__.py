"""Asynchronous Python scraper for Celcat calendar API."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("celcat_scraper")
except PackageNotFoundError:
    __version__ = "unknown"

from .celcat import CelcatConfig, CelcatScraperAsync
from .exceptions import (
    CelcatError,
    CelcatCannotConnectError,
    CelcatInvalidAuthError
)

__all__ = ["CelcatConfig", "CelcatScraperAsync", "CelcatError", "CelcatCannotConnectError", "CelcatInvalidAuthError"]
