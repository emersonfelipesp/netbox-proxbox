"""Canonical typed-sidecar lookups for reflected core objects."""

from __future__ import annotations

from typing import Any


def virtual_disks_for_storage(queryset: Any, storage: object) -> Any:
    """Filter virtual disks by their typed Proxbox storage relation."""
    return queryset.filter(proxbox_sync_state__proxbox_storage=storage)


__all__ = ("virtual_disks_for_storage",)
