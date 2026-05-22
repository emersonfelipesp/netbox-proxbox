"""Version advisories for the companion proxbox-api backend."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class BackendVersionAdvisory:
    """Operator-facing advisory derived from the proxbox-api version string."""

    code: str
    severity: Severity
    message: str


_VERSION_RE = re.compile(
    r"^\s*v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:\.post(?P<post>\d+))?(?:rc(?P<rc>\d+))?.*$"
)

_VM_CONFIG_FIX_VERSION = (0, 0, 13, 0)
_AGENT_KV_AFFECTED_MAX_VERSION = (0, 0, 14, 0)


def parse_backend_version(value: object) -> tuple[int, int, int, int] | None:
    """Parse proxbox-api ``X.Y.Z[.postN|rcN]`` strings for coarse comparisons."""
    if value is None:
        return None
    match = _VERSION_RE.match(str(value).strip())
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        int(match.group("post") or 0),
    )


def backend_version_advisories(version: object) -> list[BackendVersionAdvisory]:
    """Return VM-IP-sync advisories for a proxbox-api backend version."""
    parsed = parse_backend_version(version)
    if parsed is None:
        return []

    version_label = str(version).strip()
    if parsed < _VM_CONFIG_FIX_VERSION:
        return [
            BackendVersionAdvisory(
                code="vm_ip_sync_backend_too_old",
                severity="error",
                message=(
                    f"proxbox-api {version_label} is too old for reliable VM IP "
                    "sync. Upgrade proxbox-api to 0.0.13 or later, then run a "
                    "Full Update so existing VMs get the proxmox_vm_id custom "
                    "field before IP-address sync runs."
                ),
            )
        ]

    if parsed <= _AGENT_KV_AFFECTED_MAX_VERSION:
        return [
            BackendVersionAdvisory(
                code="qemu_agent_kv_flag_fix_pending",
                severity="warning",
                message=(
                    f"proxbox-api {version_label} may still include the QEMU "
                    "guest-agent KV flag bug fixed after v0.0.14 in "
                    "proxbox-api PR #156. If VM IPs remain missing, install a "
                    "backend build containing commit f5618f3 or the next fixed "
                    "backend release, then run Full Update."
                ),
            )
        ]

    return []
