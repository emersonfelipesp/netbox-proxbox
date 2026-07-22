"""Fail-closed proxbox-api key bootstrap and rotation adoption.

The backend's unauthenticated bootstrap route is valid only while no key exists.
Once initialized, a candidate key is accepted only after it authenticates one
bounded, read-only ``GET /auth/keys`` request. Response bodies and transport
exception text are deliberately excluded from operator-facing errors because
either can contain credential material.

Ordinary adoption is read-only unless the caller explicitly proves that the
candidate was supplied and retained for a recoverable first-key bootstrap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from ipaddress import IPv6Address, ip_address
import re
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit

from netbox_proxbox.services.http_client import (
    HttpClient,
    HttpConnectionError,
    HttpError,
    HttpSslError,
    HttpTimeoutError,
    get_default_http_client,
)

_STATUS_TIMEOUT = 5
_AUTH_TIMEOUT = 5
_REGISTER_TIMEOUT = 10

_FQDN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z0-9]{2,}$"
)
_SIMPLE_HOST_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")

BackendKeyTransitionAction = Literal[
    "no_remote_check", "preflight", "reject_disabled_change"
]


class BackendKeyEndpoint(Protocol):
    """Minimum endpoint surface required by the adoption service."""

    pk: object | None
    enabled: bool
    domain: str | None
    ip_address: object | None
    port: int
    use_https: bool
    verify_ssl: bool
    use_websocket: bool
    server_side_websocket: bool


class BackendKeyAdoptionError(Exception):
    """Secret-safe validation failure raised before token persistence."""

    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class BackendKeyAdoptionProof:
    """In-memory proof binding a successful check to its exact target and key."""

    fingerprint: str
    action: Literal["adopted", "bootstrapped"]
    target_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class BackendKeyInspection:
    """Read-only result for an existing or not-yet-initialized backend."""

    state: Literal["accepted", "needs_bootstrap"]
    fingerprint: str


def plan_backend_key_transition(
    *,
    exists: bool,
    current_enabled: bool,
    previous_enabled: bool,
    token_changed: bool,
    connection_changed: bool,
) -> BackendKeyTransitionAction:
    """Select the only allowed persistence path for a key state transition."""
    if not current_enabled:
        if exists and token_changed:
            return "reject_disabled_change"
        return "no_remote_check"
    if not exists or not previous_enabled or token_changed or connection_changed:
        return "preflight"
    return "no_remote_check"


def _invalid_target(code: str, message: str) -> BackendKeyAdoptionError:
    return BackendKeyAdoptionError(code, message)


def _canonical_domain(value: str) -> str:
    """Return a validated DNS authority without accepting URL syntax."""
    domain = value.strip().lower()
    if (
        not domain
        or len(domain) > 253
        or (
            domain != "localhost"
            and _FQDN_RE.fullmatch(domain) is None
            and _SIMPLE_HOST_RE.fullmatch(domain) is None
        )
    ):
        raise _invalid_target(
            "endpoint_domain_invalid",
            "Configure a valid backend domain name before adopting an API key.",
        )
    return domain


def _canonical_ip_authority(value: object | None) -> str:
    """Return a validated IP authority, bracketing IPv6 for URL construction."""
    if value is None:
        return ""
    address = getattr(value, "address", value)
    raw_address = str(address).split("/", 1)[0].strip()
    try:
        parsed = ip_address(raw_address)
    except ValueError:
        raise _invalid_target(
            "endpoint_ip_invalid",
            "Configure a valid backend IP address before adopting an API key.",
        ) from None
    canonical = str(parsed)
    return f"[{canonical}]" if isinstance(parsed, IPv6Address) else canonical


def canonical_backend_authority(value: object | None) -> str:
    """Return one canonical DNS/IP authority without accepting URL syntax."""
    if value is None:
        return ""
    raw_value = str(getattr(value, "address", value)).split("/", 1)[0].strip()
    if not raw_value:
        return ""
    try:
        return _canonical_ip_authority(raw_value)
    except BackendKeyAdoptionError:
        return _canonical_domain(raw_value)


def _endpoint_ip_source(endpoint: BackendKeyEndpoint) -> object | None:
    """Resolve the current FK value, bypassing stale related-object caches."""
    resolver = getattr(endpoint, "backend_key_ip_address_for_trust", None)
    if callable(resolver):
        return resolver()
    return getattr(endpoint, "ip_address", None)


def _normalize_backend_base_url(base_url: str) -> str:
    """Validate and canonicalize a caller-supplied backend URL authority."""
    raw_url = (base_url or "").strip()
    if not raw_url:
        raise _invalid_target(
            "endpoint_address_missing",
            "Configure a backend domain or IP address before adopting an API key.",
        )
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError:
        raise _invalid_target(
            "endpoint_url_invalid",
            "Configure a valid backend URL before adopting an API key.",
        ) from None

    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise _invalid_target(
            "endpoint_url_invalid",
            "Configure a backend URL containing only an HTTP(S) scheme, host, and port.",
        )

    try:
        host_ip = ip_address(parsed.hostname)
    except ValueError:
        authority = _canonical_domain(parsed.hostname)
    else:
        canonical_ip = str(host_ip)
        authority = (
            f"[{canonical_ip}]" if isinstance(host_ip, IPv6Address) else canonical_ip
        )

    if port is not None:
        if not 1 <= port <= 65535:  # pragma: no cover - guarded by urlsplit
            raise _invalid_target(
                "endpoint_port_invalid",
                "Configure a valid backend port before adopting an API key.",
            )
        authority = f"{authority}:{port}"
    return f"{scheme}://{authority}"


def backend_key_target(endpoint: BackendKeyEndpoint) -> tuple[str, bool]:
    """Return the exact base URL and TLS-verification flag for an endpoint."""
    domain = str(getattr(endpoint, "domain", "") or "").strip()
    host = (
        _canonical_domain(domain)
        if domain
        else _canonical_ip_authority(_endpoint_ip_source(endpoint))
    )
    if not host:
        raise BackendKeyAdoptionError(
            "endpoint_address_missing",
            "Configure a backend domain or IP address before adopting an API key.",
        )

    scheme = "https" if bool(getattr(endpoint, "use_https", False)) else "http"
    port = int(getattr(endpoint, "port", 0) or 0)
    if not 1 <= port <= 65535:
        raise BackendKeyAdoptionError(
            "endpoint_port_invalid",
            "Configure a valid backend port before adopting an API key.",
        )
    base_url = _normalize_backend_base_url(f"{scheme}://{host}:{port}")
    return base_url, bool(getattr(endpoint, "verify_ssl", True))


def backend_key_target_fingerprint(endpoint: BackendKeyEndpoint) -> str:
    """Bind the stored key to the live canonical HTTP and server-WS policy."""
    base_url, verify_ssl = backend_key_target(endpoint)
    use_websocket = bool(getattr(endpoint, "use_websocket", False))
    server_side_websocket = bool(getattr(endpoint, "server_side_websocket", False))
    if server_side_websocket and not use_websocket:
        raise _invalid_target(
            "endpoint_websocket_policy_invalid",
            "Enable WebSocket before enabling the server-side WebSocket client.",
        )
    fallback_ip = _canonical_ip_authority(_endpoint_ip_source(endpoint))
    fallback_target = ""
    if fallback_ip:
        scheme = "https" if bool(getattr(endpoint, "use_https", False)) else "http"
        fallback_target = (
            f"{scheme}://{fallback_ip}:{int(getattr(endpoint, 'port', 0))}"
        )
    websocket_target = ""
    if use_websocket:
        websocket_host_source = (
            getattr(endpoint, "websocket_domain", None)
            or _endpoint_ip_source(endpoint)
            or getattr(endpoint, "domain", None)
        )
        websocket_host = canonical_backend_authority(websocket_host_source)
        if not websocket_host:
            raise _invalid_target(
                "endpoint_websocket_address_missing",
                "Configure a valid WebSocket host before adopting an API key.",
            )
        websocket_port_value = getattr(endpoint, "websocket_port", None)
        websocket_port = int(
            websocket_port_value
            if websocket_port_value is not None
            else getattr(endpoint, "port", 0)
        )
        if not 1 <= websocket_port <= 65535:
            raise _invalid_target(
                "endpoint_websocket_port_invalid",
                "Configure a valid WebSocket port before adopting an API key.",
            )
        websocket_target = f"{websocket_host}:{websocket_port}"
    payload = (
        f"{base_url}\0{fallback_target}\0{int(verify_ssl)}\0{int(use_websocket)}\0"
        f"{int(server_side_websocket)}\0{websocket_target}"
    ).encode()
    return sha256(payload).hexdigest()


def backend_key_runtime_is_trusted(endpoint: BackendKeyEndpoint) -> bool:
    """Return whether runtime traffic is allowed for the persisted endpoint."""
    if hasattr(endpoint, "enabled") and not bool(getattr(endpoint, "enabled", False)):
        return False
    stored = getattr(endpoint, "backend_key_target_fingerprint", None)
    # Lightweight test doubles predate the durable model field. Production
    # FastAPIEndpoint rows always expose it and therefore fail closed when blank.
    if stored is None:
        return True
    normalized_stored = str(stored or "").strip().lower()
    if len(normalized_stored) != 64:
        return False
    try:
        current = backend_key_target_fingerprint(endpoint)
    except BackendKeyAdoptionError:
        return False
    return compare_digest(normalized_stored, current)


def _proof_fingerprint(base_url: str, verify_ssl: bool, candidate: str) -> str:
    payload = f"{base_url}\0{int(verify_ssl)}\0{candidate}".encode()
    return sha256(payload).hexdigest()


def backend_key_proof_matches(
    proof: object,
    endpoint: BackendKeyEndpoint,
    candidate: str,
) -> bool:
    """Return whether a proof covers this exact endpoint configuration and key."""
    if not isinstance(proof, BackendKeyAdoptionProof):
        return False
    try:
        base_url, verify_ssl = backend_key_target(endpoint)
    except BackendKeyAdoptionError:
        return False
    normalized_candidate = (candidate or "").strip()
    return compare_digest(
        proof.fingerprint,
        _proof_fingerprint(base_url, verify_ssl, normalized_candidate),
    ) and compare_digest(
        proof.target_fingerprint,
        backend_key_target_fingerprint(endpoint),
    )


def _transport_error(exc: HttpError) -> BackendKeyAdoptionError:
    if isinstance(exc, HttpTimeoutError):
        return BackendKeyAdoptionError(
            "backend_timeout",
            "The backend timed out; the previous API key was kept unchanged.",
        )
    if isinstance(exc, HttpSslError):
        return BackendKeyAdoptionError(
            "backend_tls_error",
            "TLS verification failed; the previous API key was kept unchanged.",
        )
    if isinstance(exc, HttpConnectionError):
        return BackendKeyAdoptionError(
            "backend_unreachable",
            "The backend could not be reached; the previous API key was kept unchanged.",
        )
    return BackendKeyAdoptionError(
        "backend_request_failed",
        "The backend request failed; the previous API key was kept unchanged.",
    )


def _http_rejection(status_code: int, *, phase: str) -> BackendKeyAdoptionError:
    if phase == "bootstrap" and status_code == 409:
        return BackendKeyAdoptionError(
            "bootstrap_conflict",
            "The backend became initialized before registration completed; no key was persisted.",
        )
    if status_code in {401, 403}:
        return BackendKeyAdoptionError(
            "candidate_rejected",
            "The candidate API key was rejected; the previous key was kept unchanged.",
        )
    if status_code == 409:
        return BackendKeyAdoptionError(
            "candidate_conflict",
            "The backend rejected the key state transition; the previous key was kept unchanged.",
        )
    if status_code == 429:
        return BackendKeyAdoptionError(
            "backend_throttled",
            "The backend throttled validation; wait before trying again. The previous key was kept unchanged.",
        )
    return BackendKeyAdoptionError(
        f"{phase}_http_{status_code}",
        f"The backend rejected API-key {phase} with HTTP {status_code}; the previous key was kept unchanged.",
    )


def adopt_rotated_backend_key(
    endpoint: BackendKeyEndpoint,
    candidate: str,
    *,
    bootstrap_if_needed: bool = False,
    http_client: HttpClient | None = None,
) -> BackendKeyAdoptionProof:
    """Validate or bootstrap ``candidate`` before its encrypted value is saved.

    Initialized backends are never sent the bootstrap POST. They must accept the
    candidate on exactly one authenticated, read-only keys request. A backend
    that explicitly reports ``needs_bootstrap=true`` receives exactly one
    registration attempt, and only HTTP 201 is success.
    """
    if not bool(getattr(endpoint, "enabled", True)):
        raise BackendKeyAdoptionError(
            "endpoint_disabled",
            "Enable the backend endpoint before adopting a replacement API key.",
        )

    normalized_candidate = (candidate or "").strip()
    if not normalized_candidate:
        raise BackendKeyAdoptionError(
            "candidate_missing",
            "Provide a non-empty backend API key.",
        )

    base_url, verify_ssl = backend_key_target(endpoint)
    endpoint_id = getattr(endpoint, "pk", None)
    label_suffix = str(endpoint_id) if endpoint_id is not None else "pending"
    proof = adopt_backend_key_at_url(
        base_url,
        verify_ssl,
        normalized_candidate,
        label=f"netbox-fastapi-{label_suffix}",
        bootstrap_if_needed=bootstrap_if_needed,
        http_client=http_client,
    )
    return BackendKeyAdoptionProof(
        fingerprint=proof.fingerprint,
        action=proof.action,
        target_fingerprint=backend_key_target_fingerprint(endpoint),
    )


def adopt_backend_key_at_url(
    base_url: str,
    verify_ssl: bool,
    candidate: str,
    *,
    label: str,
    bootstrap_if_needed: bool = False,
    http_client: HttpClient | None = None,
) -> BackendKeyAdoptionProof:
    """Authenticate a candidate, optionally allowing explicit first bootstrap."""
    client = http_client or get_default_http_client()
    inspection = inspect_backend_key_at_url(
        base_url,
        verify_ssl,
        candidate,
        http_client=client,
    )
    if inspection.state == "accepted":
        return BackendKeyAdoptionProof(
            fingerprint=inspection.fingerprint,
            action="adopted",
        )

    if not bootstrap_if_needed:
        raise BackendKeyAdoptionError(
            "bootstrap_required",
            "The backend has no API keys. Provide an explicitly retained candidate "
            "for the one-time bootstrap operation.",
        )

    return _register_backend_key_at_url(
        base_url,
        verify_ssl,
        candidate,
        label=label,
        inspection=inspection,
        http_client=client,
    )


def bootstrap_backend_key_at_url(
    base_url: str,
    verify_ssl: bool,
    candidate: str,
    *,
    label: str,
    http_client: HttpClient | None = None,
) -> BackendKeyAdoptionProof:
    """Perform an explicit, recoverable first-key bootstrap.

    The caller must either own and retain the plaintext candidate or load it
    from a committed row. Hidden, server-generated candidates are forbidden.
    """
    return adopt_backend_key_at_url(
        base_url,
        verify_ssl,
        candidate,
        label=label,
        bootstrap_if_needed=True,
        http_client=http_client,
    )


def _register_backend_key_at_url(
    base_url: str,
    verify_ssl: bool,
    candidate: str,
    *,
    label: str,
    inspection: BackendKeyInspection,
    http_client: HttpClient,
) -> BackendKeyAdoptionProof:
    """Issue the single bootstrap POST after a matching empty-state inspection."""
    client = http_client

    normalized_candidate = (candidate or "").strip()
    normalized_base_url = _normalize_backend_base_url(base_url)
    try:
        registration_response = client.post(
            f"{normalized_base_url}/auth/register-key",
            json={
                "api_key": normalized_candidate,
                "label": label,
            },
            verify=verify_ssl,
            timeout=_REGISTER_TIMEOUT,
            allow_redirects=False,
        )
    except HttpError as exc:
        raise _transport_error(exc) from None
    if registration_response.status_code != 201:
        raise _http_rejection(registration_response.status_code, phase="bootstrap")
    try:
        registration_payload = registration_response.json()
    except (TypeError, ValueError):
        raise BackendKeyAdoptionError(
            "bootstrap_response_invalid",
            "The backend returned an invalid bootstrap response; verify the key "
            "before enabling the endpoint.",
        ) from None
    registration_mapping = (
        cast(Mapping[str, object], registration_payload)
        if isinstance(registration_payload, dict)
        else None
    )
    if registration_mapping is None or not isinstance(
        registration_mapping.get("detail"), str
    ):
        raise BackendKeyAdoptionError(
            "bootstrap_response_invalid",
            "The backend returned an invalid bootstrap response; verify the key "
            "before enabling the endpoint.",
        )
    return BackendKeyAdoptionProof(
        fingerprint=inspection.fingerprint,
        action="bootstrapped",
    )


def inspect_backend_key(
    endpoint: BackendKeyEndpoint,
    candidate: str,
    *,
    http_client: HttpClient | None = None,
) -> BackendKeyInspection:
    """Inspect key state without registering or changing anything remotely."""
    if not bool(getattr(endpoint, "enabled", True)):
        raise BackendKeyAdoptionError(
            "endpoint_disabled",
            "Enable the backend endpoint before checking its API key.",
        )
    base_url, verify_ssl = backend_key_target(endpoint)
    return inspect_backend_key_at_url(
        base_url,
        verify_ssl,
        candidate,
        http_client=http_client,
    )


def inspect_backend_key_at_url(
    base_url: str,
    verify_ssl: bool,
    candidate: str,
    *,
    http_client: HttpClient | None = None,
) -> BackendKeyInspection:
    """Read bootstrap state and authenticate a candidate when initialized."""
    normalized_candidate = (candidate or "").strip()
    if not normalized_candidate:
        raise BackendKeyAdoptionError(
            "candidate_missing",
            "Provide a non-empty backend API key.",
        )
    normalized_base_url = _normalize_backend_base_url(base_url)
    client = http_client or get_default_http_client()
    fingerprint = _proof_fingerprint(
        normalized_base_url, verify_ssl, normalized_candidate
    )

    try:
        status_response = client.get(
            f"{normalized_base_url}/auth/bootstrap-status",
            verify=verify_ssl,
            timeout=_STATUS_TIMEOUT,
            allow_redirects=False,
        )
    except HttpError as exc:
        raise _transport_error(exc) from None

    if status_response.status_code != 200:
        raise _http_rejection(status_response.status_code, phase="bootstrap_status")
    try:
        status_payload = status_response.json()
    except (TypeError, ValueError):
        raise BackendKeyAdoptionError(
            "bootstrap_status_invalid",
            "The backend returned an invalid bootstrap status; no key was persisted.",
        ) from None
    if not isinstance(status_payload, dict):
        raise BackendKeyAdoptionError(
            "bootstrap_status_invalid",
            "The backend returned an invalid bootstrap status; no key was persisted.",
        )
    status_mapping = cast(Mapping[str, object], status_payload)
    needs_bootstrap = status_mapping.get("needs_bootstrap")
    has_db_keys = status_mapping.get("has_db_keys")
    if (
        not isinstance(needs_bootstrap, bool)
        or not isinstance(has_db_keys, bool)
        or needs_bootstrap is has_db_keys
    ):
        raise BackendKeyAdoptionError(
            "bootstrap_status_invalid",
            "The backend returned an inconsistent bootstrap status; no key was persisted.",
        )

    if needs_bootstrap:
        return BackendKeyInspection(
            state="needs_bootstrap",
            fingerprint=fingerprint,
        )

    try:
        authenticated_response = client.get(
            f"{normalized_base_url}/auth/keys",
            headers={"X-Proxbox-API-Key": normalized_candidate},
            verify=verify_ssl,
            timeout=_AUTH_TIMEOUT,
            allow_redirects=False,
        )
    except HttpError as exc:
        raise _transport_error(exc) from None
    if authenticated_response.status_code != 200:
        raise _http_rejection(authenticated_response.status_code, phase="validation")
    try:
        authenticated_payload = authenticated_response.json()
    except (TypeError, ValueError):
        raise BackendKeyAdoptionError(
            "key_list_invalid",
            "The backend returned an invalid authenticated key list; the previous "
            "API key was kept unchanged.",
        ) from None
    authenticated_mapping = (
        cast(Mapping[str, object], authenticated_payload)
        if isinstance(authenticated_payload, dict)
        else None
    )
    keys = authenticated_mapping.get("keys") if authenticated_mapping else None
    if (
        not isinstance(keys, list)
        or not keys
        or not all(_valid_key_record(item) for item in keys)
    ):
        raise BackendKeyAdoptionError(
            "key_list_invalid",
            "The backend returned an invalid authenticated key list; the previous "
            "API key was kept unchanged.",
        )
    return BackendKeyInspection(
        state="accepted",
        fingerprint=fingerprint,
    )


def _valid_key_record(value: object) -> bool:
    """Validate the proxbox-api ``ApiKeyResponse`` contract without coercion."""
    if not isinstance(value, dict):
        return False
    record = cast(Mapping[str, object], value)
    key_id = record.get("id")
    created_at = record.get("created_at")
    return (
        isinstance(key_id, int)
        and not isinstance(key_id, bool)
        and key_id > 0
        and isinstance(record.get("label"), str)
        and isinstance(record.get("is_active"), bool)
        and isinstance(created_at, (int, float))
        and not isinstance(created_at, bool)
    )
