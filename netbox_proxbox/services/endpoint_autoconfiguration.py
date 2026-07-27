"""Controlled discovery and credential bootstrap for local ProxBox endpoints.

Discovery is intentionally bounded to operator configuration and same-site DNS
names derived from NetBox's trusted origins.  It never scans the network.  A
stored backend key is sent only to one of those controlled targets; a fresh key
is generated only for the backend's one-time empty-key bootstrap flow.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
import logging
import secrets
from types import SimpleNamespace
from typing import Literal, cast
from urllib.parse import urlsplit

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from netbox_proxbox.services.backend_key_adoption import (
    BackendKeyAdoptionError,
    adopt_rotated_backend_key,
    backend_key_runtime_is_trusted,
    backend_key_target,
)
from netbox_proxbox.services.http_client import (
    HttpClient,
    HttpError,
    get_default_http_client,
)

logger = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 5
_BACKEND_SINGLETON_ADVISORY_LOCK = 1_312_968_792  # ASCII "NBPX"
_NETBOX_SINGLETON_ADVISORY_LOCK = _BACKEND_SINGLETON_ADVISORY_LOCK + 1


@dataclass(frozen=True, slots=True)
class EndpointAutoConfigurationResult:
    """Secret-free outcome suitable for logs and operator status surfaces."""

    state: Literal["configured", "pending", "skipped"]
    detail: str
    endpoint_id: object | None = None


def _plugin_config() -> Mapping[str, object]:
    configured = getattr(settings, "PLUGINS_CONFIG", {})
    if not isinstance(configured, Mapping):
        return {}
    plugin = configured.get("netbox_proxbox", {})
    return cast(Mapping[str, object], plugin) if isinstance(plugin, Mapping) else {}


def _normalized_origin(value: object, *, allow_loopback: bool = False) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None
    host = hostname.lower().rstrip(".")
    if host == "*" or (
        not allow_loopback and host in {"localhost", "127.0.0.1", "::1"}
    ):
        return None
    try:
        parsed_ip = ip_address(host)
    except ValueError:
        authority = host
    else:
        authority = (
            f"[{parsed_ip}]" if isinstance(parsed_ip, IPv6Address) else str(parsed_ip)
        )
    if port is not None:
        authority = f"{authority}:{port}"
    return f"{parsed.scheme}://{authority}"


def _deduplicate(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _configured_hostname(value: object) -> str:
    """Extract a hostname from trusted settings without propagating parse errors."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        return str(urlsplit(raw).hostname or "").lower()
    except ValueError:
        return ""


def discover_netbox_urls() -> tuple[str, ...]:
    """Return bounded local-NetBox candidates in deterministic preference order."""
    plugin_url = _normalized_origin(
        _plugin_config().get("netbox_url"), allow_loopback=True
    )
    trusted_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", ())
    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", ())
    origin_candidates = (
        _normalized_origin(origin)
        for origin in trusted_origins
        if _configured_hostname(origin).startswith("netbox.")
    )
    host_candidates = (
        _normalized_origin(host)
        for host in allowed_hosts
        if _configured_hostname(host).startswith("netbox.")
    )
    return _deduplicate((plugin_url, *origin_candidates, *host_candidates))


def discover_backend_urls() -> tuple[str, ...]:
    """Return configured/canonical/legacy backend targets without network scanning."""
    configured = _normalized_origin(
        _plugin_config().get("backend_url"), allow_loopback=True
    )
    derived: list[str] = []
    for netbox_url in discover_netbox_urls():
        parsed = urlsplit(netbox_url)
        host = str(parsed.hostname or "")
        if not host.startswith("netbox."):
            continue
        site_domain = host.removeprefix("netbox.")
        derived.extend(
            (
                f"https://backend.proxbox.{site_domain}",
                f"https://proxbox.backend.{site_domain}",
            )
        )
    return _deduplicate((configured, *derived))


def _backend_discovery_candidates() -> tuple[tuple[str, bool], ...]:
    """Attach the configured TLS policy to each no-row discovery candidate."""
    urls = discover_backend_urls()
    configured = _normalized_origin(
        _plugin_config().get("backend_url"), allow_loopback=True
    )
    configured_verify = bool(_plugin_config().get("backend_verify_ssl", True))
    return tuple(
        (
            candidate,
            configured_verify
            if configured is not None and candidate == configured
            else urlsplit(candidate).scheme == "https",
        )
        for candidate in urls
    )


def _is_proxbox_backend(base_url: str, verify_ssl: bool, client: HttpClient) -> bool:
    """Confirm a candidate's public identity and readiness without credentials."""
    try:
        identity = client.get(
            f"{base_url}/",
            verify=verify_ssl,
            timeout=DISCOVERY_TIMEOUT,
            allow_redirects=False,
        )
        health = client.get(
            f"{base_url}/health",
            verify=verify_ssl,
            timeout=DISCOVERY_TIMEOUT,
            allow_redirects=False,
        )
        identity_payload = identity.json()
        health_payload = health.json()
    except (HttpError, TypeError, ValueError):
        return False
    return bool(
        identity.status_code == 200
        and health.status_code == 200
        and isinstance(identity_payload, dict)
        and str(identity_payload.get("message", "")).startswith("Proxbox Backend")
        and isinstance(health_payload, dict)
        and health_payload.get("status") == "ready"
        and health_payload.get("init_ok") is True
    )


def discover_live_backend_url(
    *,
    configured_endpoint: object | None = None,
    http_client: HttpClient | None = None,
) -> tuple[str, bool] | None:
    """Return one healthy allowlisted target and its exact TLS policy.

    A persisted UI endpoint is the complete allowlist when supplied. Automatic
    same-site/configured candidates are considered only when no row exists.
    """
    client = http_client or get_default_http_client()
    if configured_endpoint is not None:
        try:
            candidates = (backend_key_target(configured_endpoint),)
        except BackendKeyAdoptionError:
            return None
    else:
        candidates = _backend_discovery_candidates()
    for candidate, verify_ssl in candidates:
        if _is_proxbox_backend(candidate, verify_ssl, client):
            return candidate, verify_ssl
    return None


def configured_backend_url_is_allowed(
    base_url: str, *, configured_endpoint: object | None = None
) -> bool:
    """Return whether an exact target belongs to the bounded discovery allowlist."""
    normalized = _normalized_origin(base_url, allow_loopback=True)
    if normalized is None:
        return False
    if configured_endpoint is not None:
        try:
            configured_url, _verify_ssl = backend_key_target(configured_endpoint)
        except BackendKeyAdoptionError:
            return False
        return normalized == _normalized_origin(configured_url, allow_loopback=True)
    return normalized in discover_backend_urls()


def _endpoint_for_url(
    endpoint: object, base_url: str, *, verify_ssl: bool
) -> SimpleNamespace:
    parsed = urlsplit(base_url)
    use_https = parsed.scheme == "https"
    port = parsed.port or (443 if use_https else 80)
    host = str(parsed.hostname or "")
    try:
        parsed_ip = ip_address(host)
    except ValueError:
        domain: str | None = host
        address: object | None = None
    else:
        domain = None
        address = str(parsed_ip)
    return SimpleNamespace(
        pk=getattr(endpoint, "pk", None),
        enabled=True,
        domain=domain,
        ip_address=address,
        port=port,
        use_https=use_https,
        verify_ssl=verify_ssl,
        use_websocket=bool(getattr(endpoint, "use_websocket", False)),
        websocket_domain=getattr(endpoint, "websocket_domain", None),
        websocket_port=getattr(endpoint, "websocket_port", None),
        server_side_websocket=bool(getattr(endpoint, "server_side_websocket", False)),
    )


def _configured_endpoint_snapshot(endpoint: object) -> SimpleNamespace:
    """Freeze one persisted trust target across probe and credential check."""
    ip_resolver = getattr(endpoint, "backend_key_ip_address_for_trust", None)
    ip_value = (
        ip_resolver()
        if callable(ip_resolver)
        else getattr(endpoint, "ip_address", None)
    )
    return SimpleNamespace(
        pk=getattr(endpoint, "pk", None),
        enabled=bool(getattr(endpoint, "enabled", False)),
        domain=getattr(endpoint, "domain", None),
        ip_address=ip_value,
        port=getattr(endpoint, "port", 0),
        use_https=bool(getattr(endpoint, "use_https", False)),
        verify_ssl=bool(getattr(endpoint, "verify_ssl", True)),
        use_websocket=bool(getattr(endpoint, "use_websocket", False)),
        websocket_domain=getattr(endpoint, "websocket_domain", None),
        websocket_port=getattr(endpoint, "websocket_port", None),
        server_side_websocket=bool(getattr(endpoint, "server_side_websocket", False)),
    )


def autoconfigure_fastapi_endpoint(
    *, http_client: HttpClient | None = None
) -> EndpointAutoConfigurationResult:
    """Discover, authenticate, and atomically persist the singleton backend row."""
    from netbox_proxbox.models import FastAPIEndpoint
    from netbox_proxbox.models.primary_secrets import encrypt_primary_secret

    endpoints = list(FastAPIEndpoint.objects.order_by("pk")[:2])
    if len(endpoints) > 1:
        return EndpointAutoConfigurationResult(
            "pending",
            "Multiple backend endpoints exist; automatic selection is blocked.",
        )
    current = endpoints[0] if endpoints else None
    if current is not None and not current.enabled:
        return EndpointAutoConfigurationResult(
            "skipped",
            "The configured backend endpoint is disabled; discovery made no request.",
            current.pk,
        )
    if (
        current is not None
        and current.token
        and backend_key_runtime_is_trusted(current)
    ):
        return EndpointAutoConfigurationResult(
            "configured", "Backend endpoint is already authenticated.", current.pk
        )

    client = http_client or get_default_http_client()
    configured_snapshot = (
        _configured_endpoint_snapshot(current) if current is not None else None
    )
    discovered = discover_live_backend_url(
        configured_endpoint=configured_snapshot,
        http_client=client,
    )
    if discovered is None:
        return EndpointAutoConfigurationResult(
            "pending",
            "No healthy backend was found at a configured or same-site target.",
        )
    live_url, verify_ssl = discovered

    if not endpoints:
        endpoint = _endpoint_for_url(
            SimpleNamespace(pk=None), live_url, verify_ssl=verify_ssl
        )
        created = None
        with transaction.atomic():
            # NetBox requires PostgreSQL. This transaction-scoped lock prevents
            # multiple web/RQ startup processes from creating competing
            # singleton rows after the same credential-free discovery probe.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [_BACKEND_SINGLETON_ADVISORY_LOCK],
                )
            if not FastAPIEndpoint.objects.exists():
                ip_object = None
                if endpoint.ip_address is not None:
                    from ipam.models import IPAddress

                    parsed_ip = ip_address(str(endpoint.ip_address))
                    prefix_length = 128 if isinstance(parsed_ip, IPv6Address) else 32
                    ip_object, _created = IPAddress.objects.get_or_create(
                        address=f"{parsed_ip}/{prefix_length}"
                    )
                created = FastAPIEndpoint(
                    name="Auto-discovered ProxBox Backend",
                    domain=endpoint.domain,
                    ip_address=ip_object,
                    port=endpoint.port,
                    use_https=endpoint.use_https,
                    verify_ssl=endpoint.verify_ssl,
                    enabled=True,
                )
                created.save()
        if created is None:
            return autoconfigure_fastapi_endpoint(http_client=client)
        created.refresh_from_db()
        if created.token and backend_key_runtime_is_trusted(created):
            return EndpointAutoConfigurationResult(
                "configured",
                "Backend endpoint discovered and authenticated.",
                created.pk,
            )
        # ``FastAPIEndpoint.save()`` schedules authentication with
        # ``transaction.on_commit``.  If this service itself is running inside
        # a wider transaction, do not recurse and send the committed candidate
        # to the backend early: an outer rollback would otherwise leave a
        # remote key whose encrypted local copy no longer exists.
        return EndpointAutoConfigurationResult(
            "pending",
            "Backend endpoint discovered; authentication is scheduled after commit.",
            created.pk,
        )

    current = endpoints[0]
    candidate = (current.token or "").strip()
    generated_now = False
    if not candidate:
        candidate = secrets.token_urlsafe(48)
        encrypted_candidate = encrypt_primary_secret(candidate)
        stored = FastAPIEndpoint.objects.filter(
            pk=current.pk,
            token_enc=current.token_enc,
            backend_key_target_fingerprint=current.backend_key_target_fingerprint,
            enabled=current.enabled,
            domain=current.domain,
            ip_address_id=current.ip_address_id,
            port=current.port,
            use_https=current.use_https,
            verify_ssl=current.verify_ssl,
            use_websocket=current.use_websocket,
            websocket_domain=current.websocket_domain,
            websocket_port=current.websocket_port,
            server_side_websocket=current.server_side_websocket,
        ).update(token_enc=encrypted_candidate)
        if stored != 1:
            return EndpointAutoConfigurationResult(
                "pending",
                "Backend endpoint changed concurrently; automatic configuration will retry.",
                current.pk,
            )
        current.refresh_from_db()
        candidate = (current.token or "").strip()
        if not candidate:  # pragma: no cover - encrypted persistence invariant
            return EndpointAutoConfigurationResult(
                "pending",
                "The generated backend key could not be retained.",
                current.pk,
            )
        generated_now = True

    if generated_now and connection.in_atomic_block:
        # Never disclose a key generated by this transaction before its local
        # encrypted copy is durable. A rollback drops this callback with it.
        transaction.on_commit(
            lambda: autoconfigure_fastapi_endpoint(http_client=client)
        )
        return EndpointAutoConfigurationResult(
            "pending",
            "The generated backend key is retained; authentication is scheduled after commit.",
            current.pk,
        )

    # The frozen persisted UI row is the trust configuration. Do not rewrite its
    # authority, IP fallback, port, or TLS policy during discovery.
    assert configured_snapshot is not None  # narrowed by the existing-row branch
    try:
        proof = adopt_rotated_backend_key(
            configured_snapshot,
            candidate,
            bootstrap_if_needed=True,
            http_client=client,
        )
    except BackendKeyAdoptionError as exc:
        return EndpointAutoConfigurationResult(
            "pending",
            f"Backend discovery succeeded, but authentication is pending ({exc.code}).",
            current.pk,
        )

    updates: dict[str, object] = {
        "backend_key_target_fingerprint": proof.target_fingerprint,
    }
    changed = FastAPIEndpoint.objects.filter(
        pk=current.pk,
        token_enc=current.token_enc,
        backend_key_target_fingerprint=current.backend_key_target_fingerprint,
        enabled=current.enabled,
        domain=current.domain,
        ip_address_id=current.ip_address_id,
        port=current.port,
        use_https=current.use_https,
        verify_ssl=current.verify_ssl,
        use_websocket=current.use_websocket,
        websocket_domain=current.websocket_domain,
        websocket_port=current.websocket_port,
        server_side_websocket=current.server_side_websocket,
    ).update(**updates)
    if changed != 1:
        return EndpointAutoConfigurationResult(
            "pending",
            "Backend endpoint changed concurrently; automatic configuration will retry.",
            current.pk,
        )
    return EndpointAutoConfigurationResult(
        "configured", "Backend endpoint discovered and authenticated.", current.pk
    )


def autoconfigure_netbox_endpoint() -> EndpointAutoConfigurationResult:
    """Create the local NetBox row when one service-token candidate is unambiguous."""
    from netbox_proxbox.models import NetBoxEndpoint
    from users.models import Token

    endpoints = list(NetBoxEndpoint.objects.order_by("pk")[:2])
    if len(endpoints) > 1:
        return EndpointAutoConfigurationResult(
            "pending",
            "Multiple NetBox endpoints exist; automatic selection is blocked.",
        )
    existing = endpoints[0] if endpoints else None
    if existing is not None and not existing.enabled:
        return EndpointAutoConfigurationResult(
            "skipped",
            "The configured NetBox endpoint is disabled; discovery made no change.",
            existing.pk,
        )
    if existing is not None and existing.has_configured_token:
        linked_token = getattr(existing, "token", None)
        linked_token_is_usable = linked_token is None or bool(
            getattr(linked_token, "version", None) == 1
            and getattr(linked_token, "enabled", False)
            and getattr(linked_token, "write_enabled", False)
            and getattr(getattr(linked_token, "user", None), "is_active", False)
            and not getattr(linked_token, "is_expired", True)
            and (getattr(linked_token, "plaintext", None) or "").strip()
        )
        if linked_token_is_usable:
            return EndpointAutoConfigurationResult(
                "configured", "NetBox endpoint is already configured.", existing.pk
            )
    urls: tuple[str, ...] = ()
    if existing is None:
        urls = discover_netbox_urls()
        if not urls:
            return EndpointAutoConfigurationResult(
                "pending", "The local NetBox public URL could not be discovered."
            )
    service_tokens = list(
        Token.objects.filter(
            version=1,
            enabled=True,
            write_enabled=True,
            user__is_active=True,
        )
        .filter(Q(expires__isnull=True) | Q(expires__gt=timezone.now()))
        .filter(description__icontains="proxbox")
        .order_by("pk")[:2]
    )
    if len(service_tokens) != 1 or not (
        getattr(service_tokens[0], "plaintext", None)
        or getattr(service_tokens[0], "key", None)
    ):
        return EndpointAutoConfigurationResult(
            "pending",
            "Create one writable v1 NetBox token whose description contains 'proxbox'.",
        )
    if existing is not None:
        changed = NetBoxEndpoint.objects.filter(
            pk=existing.pk,
            enabled=existing.enabled,
            domain=existing.domain,
            ip_address_id=existing.ip_address_id,
            port=existing.port,
            verify_ssl=existing.verify_ssl,
            token_id=existing.token_id,
            token_version=existing.token_version,
            token_key=existing.token_key,
            token_secret=existing.token_secret,
        ).update(
            token=service_tokens[0],
            token_version="v1",
            token_key="",
            token_secret="",
        )
        if changed != 1:
            return EndpointAutoConfigurationResult(
                "pending",
                "NetBox endpoint changed concurrently; automatic configuration will retry.",
                existing.pk,
            )
        existing.refresh_from_db()
        return EndpointAutoConfigurationResult(
            "configured",
            "NetBox service token discovered for the configured endpoint.",
            existing.pk,
        )

    if connection.in_atomic_block:
        transaction.on_commit(autoconfigure_netbox_endpoint)
        return EndpointAutoConfigurationResult(
            "pending",
            "NetBox endpoint discovery is scheduled after commit.",
        )

    parsed = urlsplit(urls[0])
    discovered_host = str(parsed.hostname or "")
    try:
        discovered_ip = ip_address(discovered_host)
    except ValueError:
        discovered_ip = None
    endpoint = None
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [_NETBOX_SINGLETON_ADVISORY_LOCK],
            )
        if not NetBoxEndpoint.objects.exists():
            ip_object = None
            if discovered_ip is not None:
                from ipam.models import IPAddress

                prefix_length = 128 if isinstance(discovered_ip, IPv6Address) else 32
                ip_object, _created = IPAddress.objects.get_or_create(
                    address=f"{discovered_ip}/{prefix_length}"
                )
            endpoint = NetBoxEndpoint.objects.create(
                name="Auto-discovered NetBox Endpoint",
                domain=None if discovered_ip is not None else discovered_host,
                ip_address=ip_object,
                port=parsed.port or (443 if parsed.scheme == "https" else 80),
                token=service_tokens[0],
                verify_ssl=parsed.scheme == "https",
                enabled=True,
            )
    if endpoint is None:
        return autoconfigure_netbox_endpoint()
    return EndpointAutoConfigurationResult(
        "configured", "NetBox endpoint and service token discovered.", endpoint.pk
    )


def autoconfigure_endpoints(
    *, http_client: HttpClient | None = None
) -> tuple[EndpointAutoConfigurationResult, EndpointAutoConfigurationResult]:
    """Run both idempotent endpoint discovery operations."""
    backend = autoconfigure_fastapi_endpoint(http_client=http_client)
    netbox = autoconfigure_netbox_endpoint()
    logger.info("ProxBox backend auto-configuration: %s", backend.detail)
    logger.info("NetBox endpoint auto-configuration: %s", netbox.detail)
    return backend, netbox
