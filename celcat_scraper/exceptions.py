"""Custom exceptions for the Celcat calendar API wrapper.

This module contains all custom exceptions that may be raised by the Celcat API wrapper.
Each exception provides specific error information to help diagnose issues.
"""


class CelcatError(Exception):
    """Base exception for all Celcat-related errors.

    All custom exceptions in this module inherit from this base class.
    """


class CelcatCannotConnectError(CelcatError):
    """Exception raised when connection to Celcat service fails.

    This may be due to network issues, server unavailability, or invalid URLs.
    """


class CelcatInvalidAuthError(CelcatError):
    """Exception raised when authentication credentials are invalid.

    This occurs when the provided username/password combination is incorrect.
    """
