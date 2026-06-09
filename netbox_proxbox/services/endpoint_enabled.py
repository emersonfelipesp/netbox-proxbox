"""Shared enabled-state guards for endpoint-like objects."""

from __future__ import annotations


def endpoint_is_enabled(endpoint: object) -> bool:
    """Return whether an endpoint-like object is operationally enabled."""
    return bool(getattr(endpoint, "enabled", True))


def endpoint_label(endpoint: object) -> str:
    """Return a stable human-readable label for skip/error messages."""
    name = getattr(endpoint, "name", None)
    if name not in (None, ""):
        return str(name)
    try:
        return str(endpoint)
    except Exception:  # noqa: BLE001
        return endpoint.__class__.__name__


def disabled_endpoint_detail(
    endpoint: object,
    *,
    kind: str | None = None,
    action: str = "skipping",
) -> str | None:
    """Return a skip detail for disabled endpoints, or ``None`` when enabled."""
    if endpoint_is_enabled(endpoint):
        return None

    label = endpoint_label(endpoint)
    endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", None))
    endpoint_kind = kind or endpoint.__class__.__name__
    if endpoint_id is not None:
        return f"{endpoint_kind} '{label}' (id={endpoint_id}) is disabled; {action}."
    return f"{endpoint_kind} '{label}' is disabled; {action}."
