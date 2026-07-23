"""Helpers to synchronize NetBox endpoint records to proxbox-api backend storage."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING

import requests
from django.db import DatabaseError
from django.utils.crypto import salted_hmac

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.services.endpoint_enabled import disabled_endpoint_detail
from netbox_proxbox.utils import get_ip_address_host
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)

if TYPE_CHECKING:
    from netbox_proxbox.models import NetBoxEndpoint

logger = logging.getLogger(__name__)

# HTTP budget for pushing an endpoint record into proxbox-api's own database.
# A cold backend (first request after a container start) needs noticeably longer
# than a warm one, and the old 10s/15s bounds turned that start-up latency into
# a failed preflight on the very first sync of a new install.  This is a ceiling,
# not a delay — a healthy backend answers in well under a second.
BACKEND_ENDPOINT_PUSH_TIMEOUT = 30

# Wall-clock ceiling for the sync-job preflight's Proxmox endpoint-push loop.
# The loop costs up to ``BACKEND_ENDPOINT_PUSH_TIMEOUT`` per endpoint, so on an
# estate with many endpoints and an unresponsive backend it could otherwise
# consume the entire RQ job timeout before a single stage ran.
#
# The budget is **soft**, and that distinction is load-bearing.  Past it, only
# endpoints the backend already holds are skipped — for those the push is a
# refresh, so its operational connection behavior is unchanged; only
# non-operational display metadata may lag. An endpoint the
# backend has *never* seen is always pushed, because skipping it strands the
# endpoint with no backend id at all and the run then fails outright.  Budgeting
# an endpoint into a guaranteed failure is strictly worse than spending the time.
PREFLIGHT_ENDPOINT_PUSH_BUDGET = 600.0

# Hard ceiling for the same loop.  The soft budget keeps pushing unregistered
# endpoints indefinitely, which is right when the backend is merely slow and wrong
# when it is hung.  Past this point everything is skipped.  Sized at 25% of the
# 7200 s ``PROXBOX_SYNC_JOB_TIMEOUT`` so a stuck backend still leaves three
# quarters of the job budget for the stages that can run.
PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING = 1800.0


def backend_holds_proxmox_endpoint(
    endpoint: ProxmoxEndpoint,
    existing_endpoints: list[dict[str, object]] | None,
) -> bool:
    """Return ``True`` when ``existing_endpoints`` already holds a *current* row.

    "Present" alone is not enough. This decides whether the preflight may skip a
    push once past ``PREFLIGHT_ENDPOINT_PUSH_BUDGET``, and skipping is only free
    when the push would have been a no-op refresh. A row whose stored connection
    target or pushed configuration has drifted still needs its push — otherwise
    the soft budget would preserve exactly the stale row
    ``resolve_backend_endpoint_ids()`` then refuses to sync against, turning a
    merely slow backend into a blocked endpoint.

    The row is located by ``proxmox_backend_name()`` — the same name the push
    itself matches on, so this check and ``sync_proxmox_endpoint_to_backend()``
    cannot drift apart — and then compared by ``_proxmox_row_is_current()``.

    ``None`` (the listing call itself failed) is treated as *not held*: unknown
    must never be the reason an endpoint is skipped into a fatal error.
    """
    if not existing_endpoints:
        return False
    row = _backend_row_for_endpoint(existing_endpoints, endpoint)
    return row is not None and _proxmox_row_is_current(endpoint, row)


def _disabled_endpoint_detail(endpoint: ProxmoxEndpoint) -> str | None:
    """Return a user-facing skip reason when a Proxmox endpoint is disabled."""
    return disabled_endpoint_detail(
        endpoint, kind="Proxmox endpoint", action="skipping"
    )


def proxmox_backend_name(endpoint: ProxmoxEndpoint) -> str:
    """Stable display name for proxbox-api including the NetBox primary key suffix."""
    base_name = (
        getattr(endpoint, "name", "") or "Proxmox Endpoint"
    ).strip() or "Proxmox Endpoint"
    endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", None))
    return f"{base_name} (nb:{endpoint_id})" if endpoint_id is not None else base_name


def _related_object_metadata(
    prefix: str, value: object | None
) -> dict[str, object | None]:
    """Return flat relation metadata for proxbox-api endpoint placement fields."""
    if value is None:
        return {
            f"{prefix}_id": None,
            f"{prefix}_slug": None,
            f"{prefix}_name": None,
        }
    return {
        f"{prefix}_id": getattr(value, "pk", getattr(value, "id", None)),
        f"{prefix}_slug": getattr(value, "slug", None),
        f"{prefix}_name": getattr(value, "name", None) or str(value),
    }


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _proxmox_backend_payload(endpoint: ProxmoxEndpoint) -> dict[str, object]:
    """JSON body for POST/PUT ``/proxmox/endpoints`` from a ``ProxmoxEndpoint`` row."""
    tuning = endpoint.effective_connection_tuning()
    return {
        "name": proxmox_backend_name(endpoint),
        "ip_address": get_ip_address_host(getattr(endpoint, "ip_address", None)),
        "domain": (getattr(endpoint, "domain", "") or "").strip() or None,
        "port": int(getattr(endpoint, "port", 8006) or 8006),
        "username": (getattr(endpoint, "username", "") or "root@pam").strip()
        or "root@pam",
        "password": (getattr(endpoint, "password", "") or "").strip() or None,
        "verify_ssl": bool(getattr(endpoint, "verify_ssl", False)),
        "timeout": tuning["timeout"],
        "max_retries": tuning["max_retries"],
        "retry_backoff": float(tuning["retry_backoff"]),
        "token_name": (getattr(endpoint, "token_name", "") or "").strip() or None,
        "token_value": (getattr(endpoint, "token_value", "") or "").strip() or None,
        # Push the transport access method so the proxbox-api backend can gate
        # its own SSH paths (cloud-image build / Azure VHD import). Unlike
        # allow_writes (a deliberate manual trust boundary), access_methods only
        # permits the SSH transport and never grants writes, so it is safe to
        # propagate automatically.
        "access_methods": (getattr(endpoint, "access_methods", "") or "api").strip()
        or "api",
        **_related_object_metadata("site", getattr(endpoint, "site", None)),
        **_related_object_metadata("tenant", getattr(endpoint, "tenant", None)),
    }


def sync_proxmox_endpoint_to_backend(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = BACKEND_ENDPOINT_PUSH_TIMEOUT,
    existing_endpoints: list[dict[str, object]] | None = None,
) -> tuple[bool, str | None, int | None]:
    """Ensure the selected NetBox Proxmox endpoint exists in proxbox-api backend DB.

    Pass ``existing_endpoints`` (from ``list_backend_proxmox_endpoints()``) when
    pushing several endpoints in a row: the listing is identical for all of them,
    and re-fetching it per endpoint doubles the worst-case HTTP time of a loop
    that already scales with endpoint count.
    """
    disabled_detail = _disabled_endpoint_detail(endpoint)
    if disabled_detail:
        return False, disabled_detail, None

    list_url = f"{base_url}/proxmox/endpoints"
    headers = auth_headers or {}
    payload = _proxmox_backend_payload(endpoint)

    try:
        if existing_endpoints is not None:
            endpoints: object = existing_endpoints
        else:
            list_response = requests.get(
                list_url,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )
            list_response.raise_for_status()
            endpoints, json_err = parse_requests_response_json(
                list_response, log_label="proxmox/endpoints"
            )
            if json_err:
                return (
                    False,
                    f"Failed to sync Proxmox endpoint to ProxBox backend: {json_err}",
                    None,
                )
        if not isinstance(endpoints, list):
            return (
                False,
                "ProxBox backend returned invalid endpoint list payload.",
                None,
            )

        endpoint_name = str(payload["name"])
        existing = next(
            (
                item
                for item in endpoints
                if isinstance(item, dict) and item.get("name") == endpoint_name
            ),
            None,
        )

        if existing and existing.get("id") is not None:
            response = requests.put(
                f"{list_url}/{existing['id']}",
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )
        else:
            response = requests.post(
                list_url,
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )

        response.raise_for_status()
        _record_pushed_proxmox_credential_fingerprint(endpoint, payload)
        return True, None, None

    except requests.exceptions.RequestException as exc:
        detail, http_status = extract_backend_error_detail(exc)
        return (
            False,
            f"Failed to sync Proxmox endpoint to ProxBox backend: {detail}",
            http_status,
        )


def _list_backend_proxmox_endpoints(
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[list[dict[str, object]] | None, str | None]:
    """GET ``/proxmox/endpoints`` and return the parsed list (or an error string)."""
    list_url = f"{base_url}/proxmox/endpoints"
    headers = auth_headers or {}
    try:
        list_response = requests.get(
            list_url,
            headers=headers,
            verify=backend_verify_ssl,
            timeout=timeout,
        )
        list_response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        return None, f"Failed to list Proxmox endpoints on ProxBox backend: {detail}"

    endpoints, json_err = parse_requests_response_json(
        list_response, log_label="proxmox/endpoints"
    )
    if json_err:
        return None, f"Failed to read Proxmox endpoint list: {json_err}"
    if not isinstance(endpoints, list):
        return None, "ProxBox backend returned invalid endpoint list payload."
    return [item for item in endpoints if isinstance(item, dict)], None


def list_backend_proxmox_endpoints(
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = BACKEND_ENDPOINT_PUSH_TIMEOUT,
) -> tuple[list[dict[str, object]] | None, str | None]:
    """Public three-way listing of the Proxmox endpoints proxbox-api holds.

    Same contract as ``list_backend_netbox_endpoints()``: ``(rows, None)`` on
    success — an empty list is a real answer — and ``(None, error)`` when the
    call failed. Intended to be fetched once and handed to repeated
    ``sync_proxmox_endpoint_to_backend()`` calls as ``existing_endpoints``.
    """
    return _list_backend_proxmox_endpoints(
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )


def _proxmox_connection_target(domain: str, ip_address: str) -> str:
    """Return the host proxbox-api would actually dial for these two fields.

    Mirrors the backend's own ``ProxmoxEndpoint.host`` property
    (``return self.domain or self.ip_address``): once a domain is set the stored
    address is a field nobody reads. Comparing the two fields side by side
    instead would reject our own row whenever its address changed — even though
    that address is never dialled — and accept a row that merely happens to share
    an address while dialling somebody else's vhost.
    """
    return domain or ip_address


def _proxmox_identity_host(row: dict[str, object]) -> tuple[str, str]:
    """Return the normalised ``(domain, ip_address)`` a backend row points at."""
    domain = str(row.get("domain") or "").strip().rstrip(".").lower()
    ip_address = str(row.get("ip_address") or "").split("/")[0].strip().lower()
    return domain, ip_address


def _proxmox_endpoint_identity(endpoint: ProxmoxEndpoint) -> tuple[str, str]:
    """Return the normalised ``(domain, ip_address)`` this endpoint points at.

    Deliberately read from the model rather than from
    ``_proxmox_backend_payload()``: that payload runs the address through
    ``get_ip_address_host()``, which substitutes ``"127.0.0.1"`` when no IP is
    linked so the backend always has something to dial. *Every* domain-only
    endpoint therefore pushes the identical loopback string, and comparing
    against it would make two unrelated endpoints look like the same host. Only
    an explicitly configured address is evidence; an absent one contributes
    nothing.
    """
    domain = str(getattr(endpoint, "domain", "") or "").strip().rstrip(".").lower()
    ip_obj = getattr(endpoint, "ip_address", None)
    if ip_obj is None:
        return domain, ""
    # NetBox stores the host on ``IPAddress.address``; accept a bare string too,
    # since that is what the plugin's own payload builder tolerates.
    raw_address = getattr(ip_obj, "address", None)
    ip_text = str(raw_address if raw_address is not None else ip_obj)
    return domain, ip_text.split("/")[0].strip().lower()


def _proxmox_endpoint_target(endpoint: ProxmoxEndpoint) -> tuple[str, int] | None:
    """Return the ``(host, port)`` this endpoint resolves to, or ``None``.

    ``None`` means "resolves no host", which reads as *not current* everywhere
    below. That fail-closed default costs nothing in practice:
    ``EndpointBase.clean()`` requires a domain or an IP address, so a validly
    saved row always resolves one.
    """
    host = _proxmox_connection_target(*_proxmox_endpoint_identity(endpoint))
    if not host:
        return None
    try:
        return host, int(getattr(endpoint, "port", 8006) or 8006)
    except (TypeError, ValueError):
        return None


def _proxmox_row_target(row: dict[str, object]) -> tuple[str, int] | None:
    """Return the ``(host, port)`` a backend row resolves to, or ``None``.

    ``port`` is required rather than checked opportunistically: proxbox-api
    declares it non-optional on the ``ProxmoxEndpointPublic`` model it returns
    from ``GET /proxmox/endpoints``, so a row without a parseable one is not
    something this backend produced. Same host on a different port is a
    different service.
    """
    host = _proxmox_connection_target(*_proxmox_identity_host(row))
    if not host:
        return None
    try:
        return host, int(row["port"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return None


def _describe_target(target: tuple[str, int]) -> str:
    """Human-readable ``host:port`` for a log line."""
    return f"{target[0]}:{target[1]}"


def _proxmox_targets_match(endpoint: ProxmoxEndpoint, row: dict[str, object]) -> bool:
    """Return ``True`` when a backend row still dials the same host as ``endpoint``."""
    want = _proxmox_endpoint_target(endpoint)
    return want is not None and want == _proxmox_row_target(row)


def _proxmox_row_is_current(endpoint: ProxmoxEndpoint, row: dict[str, object]) -> bool:
    """Return ``True`` when a backend row already reflects what a push would send.

    Compares the resolved connection target first, then the six pushed fields
    the backend both stores and returns, and finally the **credentials**, which
    it does not. The public proxbox-api response schema normalises request tuning
    as ``int`` / ``int`` / ``float``, matching this module's payload, so timeout,
    retry-count, and retry-back-off comparisons are stable. Their drift is
    operational: skipping a globally inherited timeout change can leave the
    backend session on the old value indefinitely. Site/tenant display metadata
    remains excluded from this soft-budget predicate. A false "not current"
    costs one extra push, bounded by the hard ceiling.

    The credentials are the one exclusion that was **not** safe.
    ``ProxmoxEndpointPublic`` withholds ``password``/``token_name``/
    ``token_value``, so a secret rotated *in place* — same host, same username,
    same access methods — looked identical to the row already stored, and the
    soft budget would skip precisely the push that was meant to deliver the new
    secret. The endpoint then keeps authenticating with the credential the
    operator has just revoked, and the whole point of rotating is that the old
    value stops working. The comparison is therefore **local**:
    :func:`proxmox_push_credentials_unchanged` against the fingerprint the last
    successful push recorded (migration 0074). ``payload`` is materialised here
    anyway for the field comparisons above, so this costs no extra decryption.
    """
    if not _proxmox_targets_match(endpoint, row):
        return False
    payload = _proxmox_backend_payload(endpoint)
    for key in ("username", "access_methods"):
        if str(row.get(key) or "").strip() != str(payload.get(key) or "").strip():
            return False
    if bool(row.get("verify_ssl")) != bool(payload.get("verify_ssl")):
        return False
    for key in ("timeout", "max_retries", "retry_backoff"):
        if row.get(key) != payload.get(key):
            return False
    return proxmox_push_credentials_unchanged(endpoint, payload)


def _backend_row_for_endpoint(
    endpoints: list[dict[str, object]], endpoint: ProxmoxEndpoint
) -> dict[str, object] | None:
    """Return the backend row stored under this endpoint's ``(nb:<pk>)`` name.

    Unlike the NetBox endpoint — a singleton the backend updates by position,
    whose name is free text — a Proxmox row's name embeds the plugin primary key
    (see :func:`proxmox_backend_name`), so *which* row belongs to this endpoint
    is never in doubt. The open question is whether that row is still **fresh**,
    which is what the target/currency checks above answer.
    """
    target_name = proxmox_backend_name(endpoint)
    return next(
        (
            item
            for item in endpoints
            if isinstance(item, dict) and item.get("name") == target_name
        ),
        None,
    )


def _resolve_backend_row_id(
    endpoints: list[dict[str, object]], endpoint: ProxmoxEndpoint
) -> tuple[int | None, str | None]:
    """Resolve ``endpoint`` to its backend id, or explain why it must not be used.

    A stale row is the dangerous case, and it is reachable: the endpoint push
    happens in the sync preflight, where a *failure* is only warned about. If the
    endpoint was retargeted in NetBox and that push failed, the backend still
    holds the **previous** host under this endpoint's name — and syncing through
    that id would reflect the old Proxmox host's inventory into NetBox under the
    new endpoint. Matching by name alone cannot see that, so the resolved
    connection target is checked too and a mismatch refuses the id.
    """
    target_name = proxmox_backend_name(endpoint)
    row = _backend_row_for_endpoint(endpoints, endpoint)
    if row is None:
        return None, (
            f"Proxmox endpoint '{target_name}' is not registered on the ProxBox "
            "backend yet; cannot scope sync to a single endpoint."
        )
    want = _proxmox_endpoint_target(endpoint)
    got = _proxmox_row_target(row)
    if want is None:
        return None, (
            f"Proxmox endpoint '{target_name}' resolves no host or port in "
            "NetBox, so its ProxBox backend row cannot be confirmed to point at "
            "it; set a domain or IP address on the endpoint."
        )
    if got is None:
        return None, (
            f"Proxmox endpoint '{target_name}' is registered on the ProxBox "
            "backend, but the stored row resolves no host or port, so it cannot "
            f"be confirmed to still point at {_describe_target(want)}. Refusing "
            "to use it so this endpoint is not synced from the wrong Proxmox "
            "host."
        )
    if want != got:
        return None, (
            f"Proxmox endpoint '{target_name}' is registered on the ProxBox "
            "backend, but the backend's stored copy points at "
            f"{_describe_target(got)} instead of {_describe_target(want)}. "
            "Refusing to use it so this endpoint is not synced from the wrong "
            "Proxmox host; re-run once the endpoint push to the backend "
            "succeeds."
        )
    backend_id = _int_or_none(row.get("id"))
    if backend_id is None:
        return None, (
            f"Proxmox endpoint '{target_name}' is registered on the ProxBox "
            "backend but carries no usable id; cannot scope sync to a single "
            "endpoint."
        )
    return backend_id, None


def resolve_backend_endpoint_id(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[int | None, str | None]:
    """Resolve a plugin ``ProxmoxEndpoint`` to its proxbox-api backend database id.

    The backend assigns its own autoincrement ids and stores each endpoint under
    the name produced by :func:`proxmox_backend_name` (which embeds the NetBox
    primary key as a ``(nb:<pk>)`` suffix). Plugin primary keys therefore do not
    match backend ids; scoped sync calls must translate the plugin endpoint to
    the backend id before sending ``proxmox_endpoint_ids``.

    The name locates the row; the **resolved connection target** decides whether
    it may be used (see :func:`_resolve_backend_row_id`). The singular resolver
    matters as much as the batch one: the Templates tab and the create-instance
    wizard both go through here, so a stale row would list one host's templates
    and provision onto another.

    Returns ``(backend_id, None)`` on success, or ``(None, error_message)`` when
    the endpoint cannot be resolved. Callers must treat ``None`` as fatal for the
    scoped request rather than silently syncing every endpoint.
    """
    disabled_detail = _disabled_endpoint_detail(endpoint)
    if disabled_detail:
        return None, disabled_detail

    endpoints, list_error = _list_backend_proxmox_endpoints(
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )
    if endpoints is None:
        return None, list_error

    return _resolve_backend_row_id(endpoints, endpoint)


def resolve_backend_endpoint_ids(
    endpoints: list[ProxmoxEndpoint],
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[dict[int, int], str | None]:
    """Batch-resolve plugin ``ProxmoxEndpoint`` rows to backend ids in one call.

    Returns ``({plugin_pk: backend_id}, error)``. Plugin endpoints with no
    **usable** backend row — never registered, or registered against a different
    connection target — are simply omitted from the map so the caller can detect
    and skip them per endpoint; ``error`` is only set when the backend list
    itself could not be fetched.

    The omission reason is logged here rather than returned, because every caller
    already fails loud on a missing pk and the map is the only value it can act
    on. ``sync_stages.py`` phrases its per-endpoint job-log message to cover both
    reasons.
    """
    endpoints = [
        endpoint for endpoint in endpoints if not _disabled_endpoint_detail(endpoint)
    ]
    if not endpoints:
        return {}, None

    backend_rows, list_error = _list_backend_proxmox_endpoints(
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )
    if backend_rows is None:
        return {}, list_error

    mapping: dict[int, int] = {}
    for endpoint in endpoints:
        pk = getattr(endpoint, "pk", getattr(endpoint, "id", None))
        if pk is None:
            continue
        backend_id, skip_reason = _resolve_backend_row_id(backend_rows, endpoint)
        if backend_id is None:
            logger.warning(f"Skipping Proxmox endpoint {pk}: {skip_reason}")
            continue
        mapping[int(pk)] = backend_id
    return mapping, None


def _netbox_endpoint_backend_payload(endpoint: NetBoxEndpoint) -> dict[str, object]:
    """JSON body for POST/PUT ``/netbox/endpoint`` from a ``NetBoxEndpoint`` row."""
    # Resolve IP address string — fall back to loopback when only a domain is set.
    ip_obj = getattr(endpoint, "ip_address", None)
    if ip_obj is not None:
        ip_address = str(ip_obj.address).split("/")[0]
    else:
        ip_address = "127.0.0.1"

    # Resolve token credentials from the endpoint model.
    token_version = getattr(endpoint, "effective_token_version", "v1") or "v1"
    token_key: str | None = None
    if token_version == "v2":
        # v2: secret goes in "token", key prefix goes in "token_key".
        token_value = (getattr(endpoint, "token_secret", "") or "").strip()
        raw_key = (getattr(endpoint, "token_key", "") or "").strip()
        # Fallback: if CharFields are empty but a FK token is linked, use its key.
        if not raw_key:
            token_obj = getattr(endpoint, "token", None)
            if token_obj is not None:
                raw_key = (getattr(token_obj, "key", "") or "").strip()
        token_key = raw_key or None
        if not token_value:
            logger.warning(
                "NetBoxEndpoint %s v2 token has no secret — backend will use an empty token",
                getattr(endpoint, "pk", None),
            )
    else:
        # v1: delegate to the model property which handles FK + plaintext fallback.
        token_value = (getattr(endpoint, "effective_token_value", None) or "") or ""
        if not token_value:
            logger.warning(
                "NetBoxEndpoint %s has no token configured — backend will use an empty token",
                getattr(endpoint, "pk", None),
            )

    payload: dict[str, object] = {
        "name": (getattr(endpoint, "name", "") or "NetBox Endpoint").strip()
        or "NetBox Endpoint",
        "ip_address": ip_address,
        "domain": (getattr(endpoint, "domain", "") or "").strip(),
        "port": int(getattr(endpoint, "port", 443) or 443),
        "verify_ssl": bool(getattr(endpoint, "verify_ssl", True)),
        "token_version": token_version,
        "token": token_value,
    }
    if token_key:
        payload["token_key"] = token_key
    return payload


def list_backend_netbox_endpoints(
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = BACKEND_ENDPOINT_PUSH_TIMEOUT,
) -> tuple[list[dict[str, object]] | None, str | None]:
    """GET ``/netbox/endpoint`` and return the parsed list (or an error string).

    The three-way outcome matters to callers: ``([], None)`` means the backend
    answered and definitively holds **no** NetBox endpoint (it therefore has no
    credentials to write to NetBox with), while ``(None, error)`` means we could
    not find out. Only the first case is safe to treat as a hard failure.
    """
    list_url = f"{base_url}/netbox/endpoint"
    headers = auth_headers or {}
    try:
        list_response = requests.get(
            list_url,
            headers=headers,
            verify=backend_verify_ssl,
            timeout=timeout,
        )
        list_response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        detail, _http_status = extract_backend_error_detail(exc)
        return None, f"Failed to list NetBox endpoints on ProxBox backend: {detail}"

    endpoints, json_err = parse_requests_response_json(
        list_response, log_label="netbox/endpoint"
    )
    if json_err:
        return None, f"Failed to read NetBox endpoint list: {json_err}"
    if not isinstance(endpoints, list):
        return None, "ProxBox backend returned invalid NetBox endpoint list payload."
    return [item for item in endpoints if isinstance(item, dict)], None


def _netbox_connection_target(domain: str, ip_address: str) -> str:
    """Return the host proxbox-api would actually dial for these two fields.

    This mirrors the backend's own ``NetBoxEndpoint.url`` property, which
    resolves ``host = self.domain if self.domain else self.ip_address`` (mask
    stripped) and never consults the address once a domain is set. Identity has
    to be decided on the same value the backend connects to: a stored record's
    unused field cannot make it a different NetBox, and cannot make it ours.
    """
    return domain or ip_address


def _netbox_identity_host(row: dict[str, object]) -> tuple[str, str]:
    """Return the ``(domain, ip_address)`` a NetBox endpoint record points at."""
    domain = str(row.get("domain") or "").strip().rstrip(".").lower()
    ip_address = str(row.get("ip_address") or "").split("/")[0].strip().lower()
    return domain, ip_address


def _netbox_endpoint_identity(endpoint: NetBoxEndpoint) -> tuple[str, str]:
    """Return the ``(domain, ip_address)`` that *identify* a local NetBox endpoint.

    Deliberately read from the model rather than from
    ``_netbox_endpoint_backend_payload()``: that payload substitutes
    ``"127.0.0.1"`` when the row has no linked IP so the backend still has
    something to dial, and **every** domain-only NetBox therefore produces the
    same loopback string. Treating it as identity would let one domain-only
    instance match another one's stored record on the fallback alone. Only an
    explicitly configured IP is evidence here; an absent one contributes
    nothing.
    """
    domain = str(getattr(endpoint, "domain", "") or "").strip().rstrip(".").lower()
    ip_obj = getattr(endpoint, "ip_address", None)
    ip_address = ""
    if ip_obj is not None:
        ip_address = (
            str(getattr(ip_obj, "address", "") or "").split("/")[0].strip().lower()
        )
    return domain, ip_address


def _netbox_row_is_current(endpoint: NetBoxEndpoint, row: dict[str, object]) -> bool:
    """Return ``True`` when a stored NetBox row still reflects our pushed trust config.

    Identity (target + port) proves the row describes *this* NetBox. It does not
    prove the row is **current**, and the two questions have different answers
    after a failed push: the operator may have just changed how proxbox-api is
    supposed to authenticate to us, or whether it must verify our certificate,
    and the push that carried that change is exactly the one that failed. The
    fallback would then continue with the backend writing to NetBox under the
    security posture the operator had already replaced.

    Only the pushed, security-relevant fields the backend also **returns** are
    comparable. ``NetBoxEndpointResponse`` declares ``token_version`` and
    ``verify_ssl`` (both required); it deliberately withholds ``token`` and
    ``token_key``, so a rotated *secret* under an unchanged scheme is invisible
    here — see the note in ``backend_holds_netbox_endpoint``. ``name`` is
    excluded on purpose: it is free text with no behavioural effect, and
    comparing it would fail an otherwise safe run over a cosmetic rename.

    Absent reads as drifted. Unlike the Proxmox-side twin — where "not current"
    costs one extra push — a ``False`` here *blocks* the run, so the asymmetry is
    deliberate: a row that cannot report the fields this backend declares
    mandatory is not a row we can vouch for after a failed push.
    """
    want_verify_ssl = bool(getattr(endpoint, "verify_ssl", True))
    want_token_version = str(
        getattr(endpoint, "effective_token_version", "v1") or "v1"
    ).strip()

    if "verify_ssl" not in row or "token_version" not in row:
        return False
    if bool(row.get("verify_ssl")) != want_verify_ssl:
        return False
    return str(row.get("token_version") or "").strip() == want_token_version


def backend_holds_netbox_endpoint(
    endpoint: NetBoxEndpoint,
    existing_endpoints: list[dict[str, object]] | None,
) -> bool:
    """Return ``True`` only when a stored row provably points at *this* NetBox.

    The NetBox endpoint is a **singleton** on proxbox-api: every push overwrites
    entry ``[0]`` rather than matching by name, so the mere *presence* of a row
    proves nothing about whose credentials it carries. It may have been written
    by a previous deployment, or by an entirely different NetBox instance
    pointed at the same backend. Since proxbox-api writes NetBox objects with
    whatever that row holds, treating "non-empty" as "usable" would let a sync
    keep writing to somewhere other than this NetBox.

    Identity is therefore the **connection target** — ``host:port``, where the
    host is what ``_netbox_connection_target()`` resolves — not the free-text
    ``name``, which an operator can set to anything and which carries no primary
    key (unlike the Proxmox side's ``"<name> (nb:<pk>)"``).

    Comparing the *resolved target* rather than each field in turn is what makes
    this exact in both directions. Field-by-field matching is wrong twice over:

    * It **accepts** rows it should not. A stored record with a blank ``domain``
      at our IP is a NetBox reached *by address*, which is a different service
      from ours reached by vhost name at the same address — but "our IP matched,
      the blank domain is not a conflict" let it through. The mirror case is a
      stored record naming *another* domain at our IP while we are IP-only:
      that record dials their vhost, not ours.
    * It **rejects** rows it should not. When a domain is set the backend never
      dials the address, so our own record with a since-changed IP is still
      ours, and requiring every declared field to agree would block a run that
      is perfectly safe.

    The port must be present and equal. proxbox-api declares ``port`` as a
    required field on its NetBox-endpoint response (and defaults it to 443 in
    the database), so a row that does not report one is not something this
    backend produced — and a stored port we cannot read is a service we cannot
    identify. Same host, different port is a different service.

    A listing holding **more than one** row is refused outright, whatever those
    rows say. The singleton is *positional*: the push overwrites entry ``[0]``,
    and entry ``[0]`` is what proxbox-api dials. A longer list means the
    contract this predicate rests on no longer describes the backend, and
    nothing in the response says which row wins. Matching anywhere in the list
    would then vouch for a row found at index 1 while a stale record at index 0
    — possibly another NetBox's — is the one actually driving the sync. That is
    the same cross-instance write the identity check exists to stop, reached by
    counting rows instead of by reading the wrong one.

    Fail-closed: anything that cannot be *proven* to match — an empty list, a
    failed listing call (``None``), more rows than the positional singleton
    admits, a row with no resolvable host, a different target, a missing or
    unparseable port — returns ``False``. Callers use this to decide whether to
    keep going after a failed push, so "unknown" must never read as "safe".
    """
    if not existing_endpoints:
        return False
    if len(existing_endpoints) > 1:
        return False

    want_target = _netbox_connection_target(*_netbox_endpoint_identity(endpoint))
    if not want_target:
        return False
    try:
        want_port = int(getattr(endpoint, "port", 443) or 443)
    except (TypeError, ValueError):
        return False

    for item in existing_endpoints:
        if not isinstance(item, dict):
            continue
        got_target = _netbox_connection_target(*_netbox_identity_host(item))
        if not got_target or got_target != want_target:
            continue
        try:
            if int(item["port"]) != want_port:  # type: ignore[arg-type]
                continue
        except (KeyError, TypeError, ValueError):
            continue
        # Identity selects the candidate, currency accepts it — and the guard
        # above has already reduced the list to the single position the backend
        # dials, so both questions are asked of the row that actually matters.
        # A row that is ours but drifted therefore ends the search at ``False``
        # rather than deferring to some later, better-looking duplicate.
        if _netbox_row_is_current(endpoint, item):
            return True

    return False


# Namespace for the pushed-credential HMAC. ``salted_hmac`` keys off NetBox's
# ``SECRET_KEY``, so the digest is non-reversible and is not comparable across
# installs — exactly the properties wanted for a value stored beside the
# credential it describes. The salt is the same mechanism Django uses for
# ``AbstractBaseUser.get_session_auth_hash()``.
_NETBOX_CREDENTIAL_FINGERPRINT_SALT = "netbox_proxbox.netbox_endpoint.pushed_credential"


def _fingerprint_material(values: tuple[str, ...]) -> str:
    """Encode credential fields so no two distinct tuples share one input.

    Each field is length-prefixed rather than separator-joined: a separator can
    be defeated by a field that *contains* it (nothing structurally stops a
    pasted secret from carrying any byte), letting two different tuples
    concatenate into the same material and a rotation to a colliding tuple
    compare as "unchanged". ``len()`` counts code points and the prefix ends at
    the first ``:``, so the encoding is injective for any field content.
    """
    return "".join(f"{len(value)}:{value}" for value in values)


def netbox_credential_fingerprint(payload: dict[str, object]) -> str:
    """Return a non-reversible fingerprint of the credentials in a push payload.

    Computed from the **payload** rather than from the model fields on purpose:
    the payload is literally what proxbox-api is being handed, so the recorded
    fingerprint cannot drift from what the backend actually stored. (Same
    reasoning as ``backend_holds_proxmox_endpoint()`` locating its row by
    ``proxmox_backend_name()`` — the name the push itself matches on.)
    """
    material = _fingerprint_material(
        tuple(
            str(payload.get(key) or "")
            for key in ("token_version", "token_key", "token")
        )
    )
    return salted_hmac(
        _NETBOX_CREDENTIAL_FINGERPRINT_SALT, material, algorithm="sha256"
    ).hexdigest()


def netbox_endpoint_credential_fingerprint(endpoint: NetBoxEndpoint) -> str:
    """Return the fingerprint of the credentials this endpoint *would* push now."""
    return netbox_credential_fingerprint(_netbox_endpoint_backend_payload(endpoint))


def netbox_push_credentials_unchanged(endpoint: NetBoxEndpoint) -> bool:
    """Return ``True`` when this endpoint's credentials still match its last push.

    ``_netbox_row_is_current()`` can only compare what proxbox-api gives back,
    and ``NetBoxEndpointResponse`` withholds ``token``/``token_key`` — so a token
    rotated *in place*, under an unchanged ``token_version``, is invisible to it.
    That is the residual this closes: the fingerprint is recorded locally by the
    push that succeeded, so a later failed push can tell "the backend holds the
    credentials we last sent" from "the backend holds credentials NetBox has
    since replaced".

    Fail-closed on an empty stored fingerprint. That covers a never-pushed
    endpoint and the upgrade window on an existing install, where the column
    exists but nothing has written it yet: the first run whose push *fails* then
    blocks instead of continuing, and the operator clears it by re-running once
    proxbox-api is reachable.

    Unlike ``_netbox_row_is_current()`` — which deliberately avoids
    ``_netbox_endpoint_backend_payload()`` because that helper warns and
    materialises the secret merely to answer a comparison — this check *cannot*
    be answered without materialising it, and it runs only on the already-failed
    push path.
    """
    stored = str(getattr(endpoint, "pushed_credential_fingerprint", "") or "").strip()
    if not stored:
        return False
    return hmac.compare_digest(stored, netbox_endpoint_credential_fingerprint(endpoint))


def _record_pushed_credential_fingerprint(
    endpoint: NetBoxEndpoint, payload: dict[str, object]
) -> None:
    """Persist the fingerprint of the credentials proxbox-api just accepted.

    Written with ``queryset.update()`` rather than ``save()``: ``NetBoxEndpoint``
    has a ``post_save`` handler that pushes the row to the backend, and saving
    from inside the push would re-enter it. (Same reason the Proxmox endpoint
    bulk enable/disable list actions use ``update()``.)

    A failure here is logged, never raised. The push itself succeeded, and the
    only consequence of a missing fingerprint is that a *later* failed push
    refuses to fall back on the backend's stored row — which is the fail-closed
    direction.
    """
    pk = getattr(endpoint, "pk", None)
    if pk is None:
        return
    fingerprint = netbox_credential_fingerprint(payload)
    try:
        type(endpoint).objects.filter(pk=pk).update(
            pushed_credential_fingerprint=fingerprint
        )
    except DatabaseError as exc:
        # Includes ProgrammingError when migration 0073 has not been applied yet.
        logger.warning(
            "Could not record pushed-credential fingerprint for NetBox endpoint %s: %s",
            pk,
            exc,
        )
        return
    endpoint.pushed_credential_fingerprint = fingerprint


# Separate namespace from the NetBox salt above so a Proxmox fingerprint can
# never be compared against a NetBox one, even if both ever landed in the same
# column by mistake.
_PROXMOX_CREDENTIAL_FINGERPRINT_SALT = (
    "netbox_proxbox.proxmox_endpoint.pushed_credential"
)


def proxmox_credential_fingerprint(payload: dict[str, object]) -> str:
    """Return a non-reversible fingerprint of the credentials in a push payload.

    Same construction as :func:`netbox_credential_fingerprint`, over the three
    credential keys ``_proxmox_backend_payload()`` sends: ``password``,
    ``token_name`` and ``token_value``. Computed from the payload for the same
    reason — it is literally what proxbox-api was handed, so the recorded
    fingerprint cannot drift from what the backend stored.
    """
    material = _fingerprint_material(
        tuple(
            str(payload.get(key) or "")
            for key in ("password", "token_name", "token_value")
        )
    )
    return salted_hmac(
        _PROXMOX_CREDENTIAL_FINGERPRINT_SALT, material, algorithm="sha256"
    ).hexdigest()


def proxmox_endpoint_credential_fingerprint(endpoint: ProxmoxEndpoint) -> str:
    """Return the fingerprint of the credentials this endpoint *would* push now."""
    return proxmox_credential_fingerprint(_proxmox_backend_payload(endpoint))


def proxmox_push_credentials_unchanged(
    endpoint: ProxmoxEndpoint, payload: dict[str, object]
) -> bool:
    """Return ``True`` when this endpoint's credentials still match its last push.

    Takes the already-materialised ``payload`` rather than deriving one, because
    the sole caller (:func:`_proxmox_row_is_current`) has just built it — there
    is no reason to decrypt the same secrets twice to answer one question.

    **This fails closed in the opposite direction from the NetBox twin, and the
    asymmetry is deliberate.** ``netbox_push_credentials_unchanged()`` gates a
    *fatal* preflight case, so an unknown there must block the run. This one
    gates only whether the soft push budget may **skip** a push, so unknown here
    means "push again": one extra request, bounded by
    ``PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING``, which is exactly the cost the
    surrounding docstring already accepts for a false "not current" — and it
    self-clears, because that push records the fingerprint.
    """
    stored = str(getattr(endpoint, "pushed_credential_fingerprint", "") or "").strip()
    if not stored:
        return False
    return hmac.compare_digest(stored, proxmox_credential_fingerprint(payload))


def proxmox_endpoint_credentials_rotated_since_last_push(
    endpoint: ProxmoxEndpoint,
) -> bool:
    """Return ``True`` when a recorded fingerprint no longer matches the endpoint.

    Attribution only — this never gates anything. A *failed* Proxmox push is
    non-fatal by design, but when the endpoint's credentials changed since the
    last successful push, that failure has a sharper meaning: proxbox-api is
    still holding the previous secret, so Proxmox reads for this endpoint will
    fail with an authentication error until a push succeeds. The preflight uses
    this to say so in the warning instead of leaving the operator to correlate
    a later stage's auth failure with a push warning themselves.

    Deliberately ``False`` when no fingerprint was ever recorded: that is the
    normal fresh state (or the pre-0074 upgrade window), not evidence of
    rotation.
    """
    stored = str(getattr(endpoint, "pushed_credential_fingerprint", "") or "").strip()
    if not stored:
        return False
    return not hmac.compare_digest(
        stored, proxmox_endpoint_credential_fingerprint(endpoint)
    )


def _record_pushed_proxmox_credential_fingerprint(
    endpoint: ProxmoxEndpoint, payload: dict[str, object]
) -> None:
    """Persist the fingerprint of the credentials proxbox-api just accepted.

    Written with ``queryset.update()`` rather than ``save()`` for the same
    reason as the NetBox twin: ``ProxmoxEndpoint`` has a ``post_save`` handler
    that pushes the row to the backend, and saving from inside the push would
    re-enter it.

    A failure here is logged, never raised. The push itself succeeded, and the
    only consequence of a missing fingerprint is that ``_proxmox_row_is_current()``
    reports "not current" and the next preflight spends one extra push — the
    fail-closed direction on this side.
    """
    pk = getattr(endpoint, "pk", None)
    if pk is None:
        return
    fingerprint = proxmox_credential_fingerprint(payload)
    try:
        type(endpoint).objects.filter(pk=pk).update(
            pushed_credential_fingerprint=fingerprint
        )
    except DatabaseError as exc:
        # Includes ProgrammingError when migration 0074 has not been applied yet.
        logger.warning(
            "Could not record pushed-credential fingerprint for Proxmox endpoint %s: %s",
            pk,
            exc,
        )
        return
    endpoint.pushed_credential_fingerprint = fingerprint


def sync_netbox_endpoint_to_backend(
    endpoint: NetBoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = BACKEND_ENDPOINT_PUSH_TIMEOUT,
) -> tuple[bool, str | None, int | None]:
    """Ensure the NetBox endpoint configuration exists in the proxbox-api backend DB.

    Performs GET /netbox/endpoint to check for an existing entry, then PUT to
    update it or POST to create it.  Returns (success, error_message, http_status).
    """
    disabled_detail = disabled_endpoint_detail(
        endpoint, kind="NetBox endpoint", action="skipping backend sync"
    )
    if disabled_detail:
        return False, disabled_detail, None

    list_url = f"{base_url}/netbox/endpoint"
    headers = auth_headers or {}
    payload = _netbox_endpoint_backend_payload(endpoint)

    try:
        list_resp = requests.get(
            list_url,
            headers=headers,
            verify=backend_verify_ssl,
            timeout=timeout,
        )
        if list_resp.status_code != 200:
            return (
                False,
                f"Failed to list NetBox endpoints on backend: HTTP {list_resp.status_code}",
                list_resp.status_code,
            )

        existing, json_err = parse_requests_response_json(
            list_resp, log_label="netbox/endpoint"
        )
        if json_err:
            return (
                False,
                f"Failed to sync NetBox endpoint to ProxBox backend: {json_err}",
                None,
            )
        if not isinstance(existing, list):
            return (
                False,
                "ProxBox backend returned invalid NetBox endpoint list payload.",
                None,
            )

        if existing:
            # Singleton — always update the first (and only) entry.
            endpoint_id = (
                existing[0].get("id") if isinstance(existing[0], dict) else None
            )
            if endpoint_id is None:
                return (
                    False,
                    "proxbox-api returned NetBox endpoint without id, cannot update",
                    None,
                )
            response = requests.put(
                f"{list_url}/{endpoint_id}",
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )
        else:
            response = requests.post(
                list_url,
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )

        if response.status_code in (200, 201):
            logger.info(
                "Synced NetBox endpoint '%s' to proxbox-api backend (HTTP %s)",
                payload.get("name"),
                response.status_code,
            )
            _record_pushed_credential_fingerprint(endpoint, payload)
            return True, None, None

        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            detail, _http_status = extract_backend_error_detail(exc)
        else:
            detail = f"Backend returned HTTP {response.status_code} without a JSON error detail."
        return (
            False,
            f"Failed to sync NetBox endpoint to proxbox-api: HTTP {response.status_code} - {detail}",
            response.status_code,
        )

    except requests.exceptions.RequestException as exc:
        detail, http_status = extract_backend_error_detail(exc)
        return (
            False,
            f"Failed to sync NetBox endpoint to ProxBox backend: {detail}",
            http_status,
        )
