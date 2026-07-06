"""Optional netbox-bgp integration helpers."""

from __future__ import annotations

try:
    from django.apps import apps
except Exception:  # pragma: no cover - defensive for lightweight test stubs
    apps = None


def is_netbox_bgp_installed() -> bool:
    """Return whether the optional netbox_bgp plugin is installed in NetBox."""
    if apps is None:
        return False
    try:
        return bool(apps.is_installed("netbox_bgp"))
    except Exception:
        return False


def netbox_bgp_status() -> dict[str, object]:
    """Return a small status payload for settings pages and diagnostics."""
    installed = is_netbox_bgp_installed()
    return {
        "installed": installed,
        "plugin": "netbox_bgp",
        "message": (
            "netbox_bgp is installed; SDN BGP projection can run when enabled."
            if installed
            else "netbox_bgp is not installed; SDN BGP projection will be skipped."
        ),
    }
