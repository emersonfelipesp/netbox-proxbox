"""Configuration and ownership boundaries for optional automatic polling."""

from __future__ import annotations

from typing import Any

SUPPRESSION_MARKER = "proxbox_automatic_monitor_suppressed"


def validate_automatic_background_tasks(value: object) -> bool:
    """Reject truthy strings and integers instead of silently enabling polling."""
    if type(value) is not bool:
        raise ValueError("automatic_background_tasks must be a boolean.")
    return value


def validate_sync_node_interfaces(value: object) -> bool:
    """Reject non-boolean values instead of silently enabling topology sync."""
    if type(value) is not bool:
        raise ValueError("sync_node_interfaces must be a boolean.")
    return value


def automatic_background_tasks_enabled() -> bool:
    """Read the plugin option lazily, after NetBox settings initialization."""
    from django.conf import settings

    config = getattr(settings, "PLUGINS_CONFIG", {}).get("netbox_proxbox", {})
    return validate_automatic_background_tasks(
        config.get("automatic_background_tasks", True)
    )


def is_stock_monitor_scope(job: Any) -> bool:
    """Never classify a user-owned or partially scoped job as a system timer."""
    return (
        getattr(job, "name", None) == "Proxmox Service Monitoring"
        and getattr(job, "user_id", None) is None
        and getattr(job, "object_id", None) is None
        and getattr(job, "object_type_id", None) is None
    )


def monitor_data(job: Any) -> dict[str, object]:
    """Preserve nullable core metadata and refuse malformed suppression markers."""
    value = getattr(job, "data", None)
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError("Automatic monitor data must be an object or null.")
    if SUPPRESSION_MARKER in value and value[SUPPRESSION_MARKER] is not True:
        raise ValueError("Automatic monitor suppression marker is invalid.")
    return dict(value)


def is_automatic_monitor(job: Any) -> bool:
    """Recognize stock timers and durably suppressed retries, never user jobs."""
    if not is_stock_monitor_scope(job):
        return False
    data = monitor_data(job)
    interval = getattr(job, "interval", None)
    if data.get(SUPPRESSION_MARKER) is True:
        if interval is not None and (type(interval) is not int or interval != 1):
            raise ValueError("Suppressed automatic monitor recurrence is invalid.")
        return True
    return type(interval) is int and interval == 1
