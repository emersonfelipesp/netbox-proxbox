"""Async aiohttp HTTP client for the proxbox-api."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

import aiohttp
from pydantic import BaseModel, Field

from proxbox_cli.config import Config
from proxbox_cli.errors import (
    CliError,
    MissingApiKeyError,
    RedirectRefusedError,
    ResponseTooLargeError,
)

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type QueryValue = str | int | float | bool


class ApiResponse(BaseModel):
    """ApiResponse implementation."""

    status: int
    text: str
    headers: dict[str, str] = Field(default_factory=dict)
    redaction_secret: str | None = Field(default=None, exclude=True, repr=False)

    def json_data(self) -> JSONValue:
        """Parse JSON after redacting the exact configured API key."""
        parsed: JSONValue = json.loads(self.text)
        return _redact_json_value(parsed, self.redaction_secret)

    def text_for_output(self) -> str:
        """Return response text with the exact configured API key redacted."""
        return _redact_text(self.text, self.redaction_secret)

    def is_ok(self) -> bool:
        """Handle is ok."""
        return 200 <= self.status < 300


class ProxboxApiClient:
    """Simple async HTTP client targeting a proxbox-api instance."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        path = path if path.startswith("/") else f"/{path}"
        return f"{base}{path}"

    def _headers(self) -> dict[str, str]:
        """Build request headers without creating a command-line secret surface."""
        headers = {"Accept": "application/json"}
        if self.config.api_key:
            headers["X-Proxbox-API-Key"] = self.config.api_key
        return headers

    def _response(
        self, status: int, text: str, headers: dict[str, str] | None = None
    ) -> ApiResponse:
        """Attach the configured redaction secret to a response."""
        return ApiResponse(
            status=status,
            text=text,
            headers=headers or {},
            redaction_secret=self.config.api_key,
        )

    async def _read_text(self, response: aiohttp.ClientResponse) -> str:
        """Read and decode a response without exceeding the configured byte cap."""
        body = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            remaining = self.config.max_response_bytes - len(body)
            if len(chunk) > remaining:
                raise ResponseTooLargeError(
                    "Response from "
                    f"{_hostname(str(response.url))} exceeded max_response_bytes "
                    f"({self.config.max_response_bytes} bytes)."
                )
            body.extend(chunk)
        return body.decode(response.charset or "utf-8", errors="replace")

    def _check_response(self, status: int, url: str) -> None:
        """Classify redirect and missing-authentication responses."""
        if 300 <= status < 400:
            raise RedirectRefusedError(
                f"Backend redirect from {_hostname(url)} refused (HTTP {status}); "
                "redirects are not permitted."
            )
        if status == 401 and not self.config.api_key:
            raise MissingApiKeyError(
                "proxbox-api requires authentication. Set PROXBOX_API_KEY for "
                "the selected PROXBOX_URL, or store api_key with its matching "
                "base_url in the Proxbox CLI config file."
            )

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, QueryValue] | None = None,
        payload: JSONValue | None = None,
    ) -> ApiResponse:
        """Handle request."""
        url = self._url(path)
        try:
            return await self._send(method, url, query=query, payload=payload)
        except CliError as exc:
            raise _redacted_cli_error(exc, self.config.api_key) from None
        except (aiohttp.ClientError, TimeoutError) as exc:
            return self._response(503, f"Connection error: {exc}")
        except OSError as exc:
            return self._response(503, f"Network error: {exc}")

    def _timeout(self) -> aiohttp.ClientTimeout:
        """Apply the same finite bound to total, connect, and read time."""
        return aiohttp.ClientTimeout(
            total=self.config.timeout,
            sock_connect=self.config.timeout,
            sock_read=self.config.timeout,
        )

    async def _send(
        self,
        method: str,
        url: str,
        *,
        query: Mapping[str, QueryValue] | None,
        payload: JSONValue | None,
    ) -> ApiResponse:
        """Dispatch one bounded request with redirects disabled."""
        async with aiohttp.ClientSession(timeout=self._timeout()) as session:
            async with session.request(
                method,
                url,
                params=query,
                json=payload,
                headers=self._headers(),
                allow_redirects=False,
            ) as response:
                self._check_response(response.status, url)
                text = await self._read_text(response)
                return self._response(response.status, text, dict(response.headers))

    async def get(
        self, path: str, *, query: Mapping[str, QueryValue] | None = None
    ) -> ApiResponse:
        """Handle get."""
        return await self.request("GET", path, query=query)

    async def post(self, path: str, *, payload: JSONValue | None = None) -> ApiResponse:
        """Handle post."""
        return await self.request("POST", path, payload=payload)

    async def put(self, path: str, *, payload: JSONValue | None = None) -> ApiResponse:
        """Handle put."""
        return await self.request("PUT", path, payload=payload)

    async def delete(self, path: str) -> ApiResponse:
        """Handle delete."""
        return await self.request("DELETE", path)


def _hostname(url: str) -> str:
    """Return only the host identity for transport-policy messages."""
    return urlsplit(url).hostname or "configured backend"


def _redact_text(value: str, secret: str | None) -> str:
    """Replace every exact occurrence of the configured secret."""
    return value.replace(secret, "[REDACTED]") if secret else value


def _redact_json_value(value: JSONValue, secret: str | None) -> JSONValue:
    """Redact exact secret occurrences after JSON escape decoding."""
    if isinstance(value, str):
        return _redact_text(value, secret)
    if isinstance(value, list):
        return [_redact_json_value(item, secret) for item in value]
    if isinstance(value, dict):
        return {
            _redact_text(key, secret): _redact_json_value(item, secret)
            for key, item in value.items()
        }
    return value


def _redacted_cli_error(exc: CliError, secret: str | None) -> CliError:
    """Rebuild a typed CLI error without an echoed configured secret."""
    return type(exc)(_redact_text(str(exc), secret))
