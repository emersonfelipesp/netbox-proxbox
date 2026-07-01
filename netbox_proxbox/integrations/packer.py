"""Optional integration with the **netbox-packer** plugin.

netbox-packer is one of the *Additional Optional Plugins* in the Proxbox family.
When it is installed, netbox-proxbox can offer a shortcut for building a new
Cloud-Init template **image** (a real Proxmox VM template baked from a base image
plus a ``#cloud-config``) directly from the ProxmoxEndpoint **Templates** tab.

The dependency is *soft*: netbox-packer is never imported at module import time and
is not listed in ``pyproject.toml`` dependencies. Detection happens at call time
against ``settings.PLUGINS`` (the same pattern used by
:mod:`netbox_proxbox.integrations.rpc` for netbox-rpc), and every helper degrades
cleanly when the plugin is absent so the tab keeps working without it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("netbox_proxbox.integrations.packer")

# URL name of the netbox-packer "add template" page the create button links to.
PACKER_TEMPLATE_ADD_URL_NAME = "plugins:netbox_packer:packertemplate_add"

__all__ = (
    "is_netbox_packer_installed",
    "packer_template_add_url",
    "PACKER_TEMPLATE_ADD_URL_NAME",
)


def is_netbox_packer_installed() -> bool:
    """Return ``True`` when the netbox-packer plugin is enabled in this NetBox."""
    try:
        from django.conf import settings
    except Exception:  # noqa: BLE001 - Django not ready
        return False
    return "netbox_packer" in (getattr(settings, "PLUGINS", []) or [])


def packer_template_add_url() -> str | None:
    """Return the netbox-packer "add template" URL, or ``None`` when unavailable.

    Never raises: when netbox-packer is not installed (or the URL cannot be
    reversed for any reason) the caller gets ``None`` and renders a disabled
    button instead.
    """
    if not is_netbox_packer_installed():
        return None
    try:
        from django.urls import reverse

        return reverse(PACKER_TEMPLATE_ADD_URL_NAME)
    except Exception:  # noqa: BLE001 - missing url pattern must not crash the tab
        logger.debug(
            "netbox-packer is installed but %s could not be reversed.",
            PACKER_TEMPLATE_ADD_URL_NAME,
        )
        return None
