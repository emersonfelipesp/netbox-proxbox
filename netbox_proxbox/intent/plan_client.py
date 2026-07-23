"""HTTP client for proxbox-api ``POST /intent/plan``.

Sub-PR D introduces the plan endpoint as the netbox-branching
merge_validator's only over-the-wire dependency. This module wraps the
HTTP call so the validator stays focused on diff classification.

The plan endpoint is read-only by contract — see
``proxbox_api/routes/intent/plan.py``. This client intentionally keeps
its surface minimal: a single ``call_plan_endpoint(payload)`` function
returning a typed ``PlanClientResult`` (or raising ``PlanClientError``
for transport-level failures the validator must surface to the
operator).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests
import requests.exceptions

from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.error_utils import extract_backend_error_detail

logger = logging.getLogger(__name__)


# Default request timeout for the plan validator. Plan calls are
# meant to be cheap (no Proxmox writes, no large fan-out); a tight
# ceiling keeps the merge UI responsive.
PLAN_REQUEST_TIMEOUT_SECONDS = 30


class PlanClientError(Exception):
    """Transport-level failure talking to ``POST /intent/plan``."""


@dataclass
class PlanClientResult:
    """Parsed response from ``POST /intent/plan``."""

    permitted: bool
    summary: str
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PlanClientResult":
        return cls(
            permitted=bool(payload.get("permitted", False)),
            summary=str(payload.get("summary", "")),
            verdicts=list(payload.get("verdicts") or []),
            raw=payload,
        )


def call_plan_endpoint(
    payload: dict[str, Any],
    *,
    endpoint_id: int | None = None,
    timeout: float = PLAN_REQUEST_TIMEOUT_SECONDS,
) -> PlanClientResult:
    """POST a plan request to the configured proxbox-api backend.

    Returns the parsed verdict. Raises ``PlanClientError`` if the
    backend is unreachable, unauthorized, or returns a non-2xx
    response — the merge_validator turns those into a non-permitting
    indicator so the operator gets a clear error rather than a silent
    pass.
    """
    context = get_fastapi_request_context(endpoint_id=endpoint_id)
    if context is None:
        raise PlanClientError(
            "No FastAPIEndpoint is configured; cannot validate merge intent."
        )

    http_url = context.http_url
    if not http_url:
        raise PlanClientError(
            "FastAPIEndpoint has no resolvable http_url; cannot reach proxbox-api."
        )

    url = f"{http_url.rstrip('/')}/intent/plan"
    headers = dict(context.headers or {})
    headers.setdefault("Content-Type", "application/json")

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=bool(context.verify_ssl),
            allow_redirects=False,
        )
    except requests.exceptions.SSLError as exc:
        raise PlanClientError(f"TLS error reaching {url}: {exc}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise PlanClientError(f"Cannot reach proxbox-api at {url}: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise PlanClientError(
            f"Plan request timed out after {timeout}s against {url}."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise PlanClientError(f"Plan request failed: {exc}") from exc

    if response.status_code >= 400:
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            detail, _status = extract_backend_error_detail(exc)
        else:
            detail = f"Backend returned HTTP {response.status_code} without a JSON error detail."
        raise PlanClientError(
            f"proxbox-api returned HTTP {response.status_code} for /intent/plan: "
            f"{detail}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise PlanClientError(
            f"proxbox-api returned a non-JSON body for /intent/plan: {exc}"
        ) from exc

    if not isinstance(body, dict):
        raise PlanClientError(
            f"proxbox-api returned an unexpected body for /intent/plan: {body!r}"
        )

    return PlanClientResult.from_payload(body)
