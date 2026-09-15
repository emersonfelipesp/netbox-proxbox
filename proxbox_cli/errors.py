"""Typed failures exposed by the Proxbox CLI."""

from __future__ import annotations


class CliError(Exception):
    """Base class for failures that have a stable CLI exit status."""

    exit_code = 1


class ConfigurationError(CliError):
    """Raised when CLI configuration is missing or invalid."""

    exit_code = 2


class MissingApiKeyError(ConfigurationError):
    """Raised when a protected backend rejects an unauthenticated request."""


class TransportError(CliError):
    """Base class for HTTP transport-policy failures."""


class ResponseTooLargeError(TransportError):
    """Raised when a response exceeds the configured streaming byte limit."""


class RedirectRefusedError(TransportError):
    """Raised when the backend attempts an HTTP redirect."""
