"""Optional integration with the **netbox-rpc** plugin.

netbox-rpc is one of the *Additional Optional Plugins* in the Proxbox family. When
it is installed, netbox-proxbox can run audited SSH procedures against Proxmox
hosts through the netbox-rpc engine instead of handling SSH itself — for example
installing an SSH public key on a Proxmox node so the Proxbox **cloud image build
pipeline** (proxbox-api) can reach that node.

The dependency is *soft*: netbox-rpc is never imported at module import time and is
not listed in ``pyproject.toml`` dependencies. Every helper here detects netbox-rpc
at call time with ``try/except ImportError`` (the same pattern netbox-proxbox uses
for ``netbox_branching`` and ``netbox_pbs``) and degrades cleanly when it is absent.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("netbox_proxbox.integrations.rpc")

# Canonical procedure name seeded by netbox-rpc migration 0006.
INSTALL_SSH_KEY_PROCEDURE = "os.linux.ubuntu.24.install_ssh_key"

__all__ = (
    "is_netbox_rpc_installed",
    "install_ssh_key_via_rpc",
    "rpc_dashboard_context",
    "INSTALL_SSH_KEY_PROCEDURE",
)

# netbox-rpc mounts its UI under base_url "rpc"; the landing page is the plugin
# root. Kept as a stable literal so this soft integration does not depend on the
# companion plugin's internal URL names.
NETBOX_RPC_HOME_URL = "/plugins/rpc/"


def is_netbox_rpc_installed() -> bool:
    """Return ``True`` when the netbox-rpc plugin is enabled in this NetBox."""
    try:
        from django.conf import settings
    except Exception:  # noqa: BLE001 - Django not ready
        return False
    return "netbox_rpc" in (getattr(settings, "PLUGINS", []) or [])


def install_ssh_key_via_rpc(
    *,
    target: Any,
    public_key: str,
    backend: Any,
    requested_by: Any | None = None,
    username: str | None = None,
) -> Any | None:
    """Queue a netbox-rpc ``install_ssh_key`` execution against *target*.

    Args:
        target: the NetBox object the key is installed on (``dcim.Device`` or
            ``virtualization.VirtualMachine``) — usually the Proxmox host.
        public_key: OpenSSH public key string to append to the host's
            ``authorized_keys`` (e.g. the proxbox-api cloud-image-build key).
        backend: the ``netbox_nms.NMSBackend`` record that executes the procedure.
        requested_by: the NetBox user requesting the execution (optional).
        username: POSIX user on the host; defaults to the SSH credential's user.

    Returns:
        The created ``RPCExecution`` (status ``queued``), or ``None`` when
        netbox-rpc is not installed or the procedure is unavailable. Never raises
        on a missing optional dependency.
    """
    try:
        from netbox_rpc.jobs import RPCExecutionJob
        from netbox_rpc.models import RPCExecution, RPCProcedure
    except ImportError:
        logger.info(
            "netbox-rpc is not installed; skipping SSH key install for %r.", target
        )
        return None

    procedure = RPCProcedure.objects.filter(
        name=INSTALL_SSH_KEY_PROCEDURE, enabled=True
    ).first()
    if procedure is None:
        logger.warning(
            "netbox-rpc procedure %s not found/enabled; cannot install SSH key.",
            INSTALL_SSH_KEY_PROCEDURE,
        )
        return None

    params: dict[str, str] = {"public_key": public_key}
    if username:
        params["username"] = username

    execution = RPCExecution.objects.create(
        procedure=procedure,
        assigned_object=target,
        backend=backend,
        requested_by=requested_by,
        params=params,
        status="queued",
    )

    try:
        RPCExecutionJob.enqueue(
            execution_pk=execution.pk,
            instance=None,
            user=requested_by,
            backend_pk=getattr(backend, "pk", None),
        )
    except Exception:  # noqa: BLE001 - enqueue failures must not crash the caller
        logger.exception(
            "Failed to enqueue netbox-rpc execution #%s for %r", execution.pk, target
        )

    return execution


def rpc_dashboard_context() -> dict[str, Any]:
    """Best-effort dashboard context for the optional netbox-rpc companion card.

    Returns ``{}`` when netbox-rpc is not installed, so the Proxbox home page
    simply omits the card. When netbox-rpc is present, returns
    ``{"rpc_integration": {...}}`` describing whether the operator has opted in
    (``enabled``) and which backend is configured. Never raises and never issues
    a network call — live backend reachability is offered by the netbox-rpc
    landing page's own *Test connection* action, so the Proxbox dashboard render
    stays fast and fully decoupled.
    """
    if not is_netbox_rpc_installed():
        return {}

    info: dict[str, Any] = {
        "installed": True,
        "enabled": False,
        "backend_name": "",
        "backend_url": "",
        "home_url": NETBOX_RPC_HOME_URL,
        "settings_supported": False,
    }

    try:
        from netbox_rpc.models import RpcPluginSettings  # type: ignore[import]
    except ImportError:
        # netbox-rpc is installed but predates the opt-in settings model; still
        # show the card (config state unknown) with a link to the plugin.
        return {"rpc_integration": info}

    info["settings_supported"] = True
    try:
        settings = RpcPluginSettings.get_solo()
        info["enabled"] = bool(getattr(settings, "enabled", False))
        backend = getattr(settings, "backend", None)
        if backend is not None:
            info["backend_name"] = str(backend)
            info["backend_url"] = getattr(backend, "backend_url", "") or ""
    except Exception:  # noqa: BLE001 - a bad/missing settings row must not break home
        logger.debug("Unable to read netbox-rpc RpcPluginSettings for dashboard card.")

    return {"rpc_integration": info}
