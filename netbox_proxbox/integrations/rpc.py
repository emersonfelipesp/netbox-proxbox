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
    "INSTALL_SSH_KEY_PROCEDURE",
)


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
            instance=execution,
            user=requested_by,
            backend_pk=getattr(backend, "pk", None),
        )
    except Exception:  # noqa: BLE001 - enqueue failures must not crash the caller
        logger.exception(
            "Failed to enqueue netbox-rpc execution #%s for %r", execution.pk, target
        )

    return execution
