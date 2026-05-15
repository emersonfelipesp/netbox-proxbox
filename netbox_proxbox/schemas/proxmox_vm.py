"""Pydantic V2 schemas for Proxmox VM configuration and resource responses."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import Field, field_validator

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel
from netbox_proxbox.schemas._formatters import format_bytes


def _parse_proxmox_tags(raw: str | None) -> list[str]:
    """Split the Proxmox ``tags`` field on ``;``, trim, lower, dedupe in order."""
    if not isinstance(raw, str):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for piece in raw.split(";"):
        name = piece.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _tag_fallback_color(name: str) -> str:
    """Deterministic 6-char hex color for a tag name."""
    return hashlib.md5(name.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]


_CORE_VM_FIELDS = frozenset(
    {
        "name",
        "cores",
        "sockets",
        "memory",
        "onboot",
        "agent",
        "ostype",
        "boot",
        "startup",
        "searchdomain",
        "description",
        "tags",
    }
)


class ProxmoxVMConfig(ProxboxLenientModel):
    """Live Proxmox VM config from ``/proxmox/{node}/{type}/{vmid}/config``.

    Replaces ``_LiveVMConfig`` in ``views/vm_config.py``, including its fallback shim.
    """

    name: str | None = None
    cores: int | None = None
    sockets: int | None = None
    memory: int | None = None  # MiB
    onboot: bool | None = None
    agent: bool | None = None
    ostype: str | None = None
    boot: str | None = None
    startup: str | None = None
    searchdomain: str | None = None
    description: str | None = None
    tags: str | None = None

    @field_validator("onboot", "agent", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "on", "enabled"}:
            return True
        if s in {"0", "false", "no", "off", "disabled"}:
            return False
        return None

    @field_validator("cores", "sockets", "memory", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @property
    def memory_display(self) -> str:
        """Return formatted memory string, e.g. ``2048 MiB (2.00 GiB)``."""
        if not self.memory:
            return "—"
        gib = self.memory / 1024
        return f"{self.memory} MiB ({gib:.2f} GiB)"

    def flatten_sections(
        self,
        raw: dict[str, object],
    ) -> tuple[
        list[tuple[str, object]], list[tuple[str, object]], list[tuple[str, object]]
    ]:
        """Categorise raw config keys into (disks, networks, advanced).

        Replaces ``_flatten_sections()`` in ``views/vm_config.py``.
        """
        disks: list[tuple[str, object]] = []
        networks: list[tuple[str, object]] = []
        advanced: list[tuple[str, object]] = []
        for key, value in raw.items():
            if re.match(r"^(scsi|sata|ide|virtio|mp|rootfs|unused)\d*", key):
                disks.append((key, value))
            elif re.match(r"^net\d+$", key):
                networks.append((key, value))
            elif key not in _CORE_VM_FIELDS:
                advanced.append((key, value))
        return sorted(disks), sorted(networks), sorted(advanced)

    def to_normalized_context(self, vm_name: str = "") -> dict[str, object]:
        """Build the template context dict used in the VM config tab view."""
        tag_names = _parse_proxmox_tags(self.tags)
        tags_list = [
            {"name": name, "color": _tag_fallback_color(name)} for name in tag_names
        ]
        return {
            "name": self.name or vm_name,
            "cores": self.cores,
            "sockets": self.sockets,
            "memory": self.memory_display,
            "ostype": self.ostype or "—",
            "boot": self.boot or "—",
            "startup": self.startup or "—",
            "searchdomain": self.searchdomain or "—",
            "start_at_boot": self.onboot,
            "qemu_agent": self.agent,
            "description": self.description or "—",
            "tags": self.tags or "—",
            "tags_list": tags_list,
        }


class ProxmoxResourceRecord(ProxboxLenientModel):
    """One entry from ``/proxmox/cluster/resources`` (qemu, lxc, storage, node)."""

    type: Literal["qemu", "lxc", "storage", "node"] | str = ""
    vmid: int | None = None
    name: str | None = None
    node: str | None = None
    status: str | None = None
    template: bool | None = None
    maxcpu: int | None = None
    maxmem: int | None = None
    maxdisk: int | None = None

    @field_validator("template", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "on", "enabled"}:
            return True
        if s in {"0", "false", "no", "off", "disabled"}:
            return False
        return None

    @field_validator("vmid", "maxcpu", "maxmem", "maxdisk", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


class ProxmoxGuestSummary(ProxboxBaseModel):
    """Guest counts by type for dashboard display."""

    class GuestTypeCounts(ProxboxBaseModel):
        running: int = 0
        stopped: int = 0
        templates: int = 0

    virtual_machines: GuestTypeCounts = Field(default_factory=GuestTypeCounts)
    lxc_containers: GuestTypeCounts = Field(default_factory=GuestTypeCounts)

    @classmethod
    def from_resources(
        cls, records: list[ProxmoxResourceRecord]
    ) -> ProxmoxGuestSummary:
        """Handle from resources."""

        def _count(
            items: list[ProxmoxResourceRecord],
        ) -> ProxmoxGuestSummary.GuestTypeCounts:
            running = sum(1 for r in items if r.status == "running")
            templates = sum(1 for r in items if r.template)
            return cls.GuestTypeCounts(
                running=running,
                stopped=max(len(items) - running - templates, 0),
                templates=templates,
            )

        qemu = [r for r in records if r.type == "qemu"]
        lxc = [r for r in records if r.type == "lxc"]
        return cls(virtual_machines=_count(qemu), lxc_containers=_count(lxc))
