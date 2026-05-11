"""Translate ``requests`` exceptions into actionable plugin error messages.

When a FastAPI endpoint is misconfigured for the proxbox-api `*-nginx` image
(HTTPS-only, self-signed mkcert cert), the underlying ``requests`` exception is
opaque — typically a ``400`` body of "The plain HTTP request was sent to HTTPS
port" or an ``SSLError`` for the unrecognised CA. The functions here surface a
remediation hint so the operator can fix the FastAPI endpoint without reading
the proxbox-api docs first.
"""

from __future__ import annotations

import requests

_HTTPS_ON_HTTP_HINT = (
    "The proxbox-api backend appears to be HTTPS-only "
    "(e.g. the '*-nginx' image). Enable 'Use HTTPS' on the FastAPI endpoint."
)
_SELF_SIGNED_HINT = (
    "Could not verify the proxbox-api TLS certificate. If the backend "
    "uses a self-signed certificate (e.g. the bundled mkcert cert in the "
    "'*-nginx' image), uncheck 'Verify SSL' on the FastAPI endpoint."
)
_PLAIN_HTTP_NEEDLES = (
    "plain HTTP request was sent to HTTPS port",
    "plain_http_on_https_port",
)


def translate_request_exception(exc: BaseException) -> str:
    """Return a human-friendly explanation of ``exc``, falling back to ``str(exc)``.

    Recognised cases:

    * ``HTTPError`` 400 with body indicating plain HTTP on TLS port → suggest
      enabling ``Use HTTPS``.
    * ``SSLError`` (or any 'CERTIFICATE_VERIFY' / self-signed substring) →
      suggest unchecking ``Verify SSL``.
    """
    if isinstance(exc, requests.exceptions.SSLError):
        return f"{exc}. {_SELF_SIGNED_HINT}"

    text = str(exc)
    if any(needle in text for needle in _PLAIN_HTTP_NEEDLES):
        return f"{text}. {_HTTPS_ON_HTTP_HINT}"

    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 400:
        body = ""
        try:
            body = response.text or ""
        except Exception:  # noqa: BLE001 - body access is best-effort
            body = ""
        if any(needle in body for needle in _PLAIN_HTTP_NEEDLES):
            return f"{text}. {_HTTPS_ON_HTTP_HINT}"

    return text
