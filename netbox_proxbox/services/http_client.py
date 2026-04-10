"""HTTP client abstraction decoupling service code from the requests library."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from collections.abc import Generator, Iterator
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

import requests
import requests.exceptions

logger = logging.getLogger(__name__)


class HttpError(Exception):
    """Base exception for HTTP client errors."""

    def __init__(self, message: str, *, response: HttpResponse | None = None) -> None:
        super().__init__(message)
        self.response = response


class HttpConnectionError(HttpError):
    """Raised when the server is unreachable."""


class HttpTimeoutError(HttpError):
    """Raised when the request times out."""


class HttpSslError(HttpError):
    """Raised when SSL verification fails."""


class HttpResponse:
    """Wrapper around a raw HTTP response, decoupled from requests.Response."""

    __slots__ = ("_raw",)

    def __init__(self, raw: requests.Response) -> None:
        self._raw = raw

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def ok(self) -> bool:
        return self._raw.ok

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def url(self) -> str:
        return self._raw.url

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._raw.headers)

    def json(self) -> object:
        return self._raw.json()

    def raise_for_status(self) -> None:
        self._raw.raise_for_status()

    def iter_lines(self, *, decode_unicode: bool = False) -> Iterator[str]:
        return self._raw.iter_lines(decode_unicode=decode_unicode)

    def _as_requests_response(self) -> requests.Response:
        return self._raw


@runtime_checkable
class HttpClient(Protocol):
    """Protocol defining the HTTP client interface used throughout the plugin."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
        stream: bool = False,
    ) -> HttpResponse: ...

    def post(
        self,
        url: str,
        *,
        json: dict[str, object] | list[object] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse: ...

    def put(
        self,
        url: str,
        *,
        json: dict[str, object] | list[object] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse: ...

    def delete(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse: ...

    def stream_get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = (5, 3600),
    ) -> AbstractContextManager[HttpResponse]: ...


def _convert_exception(
    exc: requests.exceptions.RequestException,
) -> HttpError:
    """Convert a requests exception into the appropriate HttpError subclass."""
    response: HttpResponse | None = None
    raw = getattr(exc, "response", None)
    if raw is not None and isinstance(raw, requests.Response):
        response = HttpResponse(raw)

    if isinstance(exc, requests.exceptions.SSLError):
        return HttpSslError(str(exc), response=response)
    if isinstance(exc, requests.exceptions.Timeout):
        return HttpTimeoutError(str(exc), response=response)
    if isinstance(exc, requests.exceptions.ConnectionError):
        return HttpConnectionError(str(exc), response=response)
    return HttpError(str(exc), response=response)


class RequestsHttpClient:
    """Concrete HTTP client wrapping the requests library."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
        stream: bool = False,
    ) -> HttpResponse:
        try:
            resp = requests.get(
                url,
                params=params,
                headers=headers,
                verify=verify,
                timeout=timeout,
                stream=stream,
            )
        except requests.exceptions.RequestException as exc:
            raise _convert_exception(exc) from exc
        return HttpResponse(resp)

    def post(
        self,
        url: str,
        *,
        json: dict[str, object] | list[object] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse:
        try:
            resp = requests.post(
                url,
                json=json,
                headers=headers,
                verify=verify,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise _convert_exception(exc) from exc
        return HttpResponse(resp)

    def put(
        self,
        url: str,
        *,
        json: dict[str, object] | list[object] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse:
        try:
            resp = requests.put(
                url,
                json=json,
                headers=headers,
                verify=verify,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise _convert_exception(exc) from exc
        return HttpResponse(resp)

    def delete(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = 5,
    ) -> HttpResponse:
        try:
            resp = requests.delete(
                url,
                headers=headers,
                verify=verify,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise _convert_exception(exc) from exc
        return HttpResponse(resp)

    @contextmanager
    def stream_get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify: bool = True,
        timeout: float | tuple[int, int] = (5, 3600),
    ) -> Generator[HttpResponse, None, None]:
        """Context-managed streaming GET yielding an HttpResponse.

        Usage::

            client = get_default_http_client()
            with client.stream_get(url, ...) as resp:
                for line in resp.iter_lines(decode_unicode=True):
                    ...
        """
        try:
            raw_resp = requests.get(
                url,
                params=params,
                headers=headers,
                verify=verify,
                timeout=timeout,
                stream=True,
            )
        except requests.exceptions.RequestException as exc:
            raise _convert_exception(exc) from exc
        try:
            yield HttpResponse(raw_resp)
        finally:
            raw_resp.close()


def _to_requests_response(
    response: HttpResponse | requests.Response,
) -> requests.Response:
    """Coerce an HttpResponse back to requests.Response for error_utils compatibility."""
    if isinstance(response, requests.Response):
        return response
    return response._as_requests_response()


def _to_requests_exception(exc: HttpError) -> requests.exceptions.RequestException:
    """Coerce an HttpError back to requests.exceptions.RequestException for error_utils."""
    if isinstance(exc, requests.exceptions.RequestException):
        return exc
    raw: requests.Response | None = None
    if exc.response is not None:
        raw = exc.response._as_requests_response()
    if isinstance(exc, HttpConnectionError):
        return requests.exceptions.ConnectionError(str(exc), response=raw)
    if isinstance(exc, HttpTimeoutError):
        return requests.exceptions.Timeout(str(exc), response=raw)
    if isinstance(exc, HttpSslError):
        return requests.exceptions.SSLError(str(exc), response=raw)
    return requests.exceptions.RequestException(str(exc), response=raw)


_default_client: RequestsHttpClient | None = None


def get_default_http_client() -> RequestsHttpClient:
    """Return the singleton default HTTP client instance."""
    global _default_client
    if _default_client is None:
        _default_client = RequestsHttpClient()
    return _default_client
