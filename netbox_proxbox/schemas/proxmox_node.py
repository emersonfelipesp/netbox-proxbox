"""Pydantic V2 schemas for Proxmox cluster and node API responses."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel
from netbox_proxbox.schemas._formatters import (
    cpu_percent,
    format_bytes,
    format_uptime,
    loadavg_text,
    percent,
)


class ProxmoxClusterStatusRecord(ProxboxLenientModel):
    """One record from ``/proxmox/cluster/status`` — type is 'cluster', 'node', or 'quorum'."""

    type: Literal["cluster", "node", "quorum"] | str = ""
    name: str | None = None
    id: str | None = None
    # cluster-type fields
    nodes: int | None = None
    quorate: bool | None = None
    version: int | None = None
    # node-type fields
    nodeid: int | None = None
    ip: str | None = None
    online: bool | None = None
    local: bool | None = None
    level: str | None = None
    status: str | None = None

    @field_validator("quorate", "online", "local", mode="before")
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

    @field_validator("nodes", "nodeid", "version", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


class ProxmoxClusterStatusResponse(ProxboxBaseModel):
    """Full parsed ``/proxmox/cluster/status`` payload (list of per-cluster records)."""

    records: list[ProxmoxClusterStatusRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_list_or_dict(cls, v: object) -> dict[str, object]:
        """Normalise the ``/proxmox/cluster/status`` payload into flat records.

        The backend returns one entry per Proxmox session. Each entry is a
        *cluster* object that carries its members under a nested ``node_list``
        (``[{"type": "cluster", ..., "node_list": [{"type": "node", ...}]}]``).
        Older/standalone shapes may instead return a flat list mixing
        ``cluster`` and ``node`` records, or a dict of session_name → list.

        Flatten every shape into a single ``records`` list so ``cluster_record``
        and ``node_records`` work regardless of nesting: each cluster object is
        kept *and* its ``node_list`` members are hoisted to top-level node
        records.
        """
        raw_items: list[object] = []
        if isinstance(v, list):
            raw_items = list(v)
        elif isinstance(v, dict):
            for val in v.values():
                if isinstance(val, list):
                    raw_items.extend(val)
        else:
            return {"records": []}

        records: list[object] = []
        for item in raw_items:
            records.append(item)
            if isinstance(item, dict):
                nested_nodes = item.get("node_list")
                if isinstance(nested_nodes, list):
                    records.extend(nested_nodes)
        return {"records": records}

    @property
    def cluster_record(self) -> ProxmoxClusterStatusRecord | None:
        """Handle cluster record."""
        return next((r for r in self.records if r.type == "cluster"), None)

    @property
    def node_records(self) -> list[ProxmoxClusterStatusRecord]:
        """Handle node records."""
        return [r for r in self.records if r.type == "node"]


class ProxmoxNodeDetail(ProxboxLenientModel):
    """One record from ``/proxmox/nodes/`` — hardware resource summary for a node."""

    node: str = ""
    status: str | None = None
    uptime: int | None = None
    cpu: float | None = None
    maxcpu: int | None = None
    mem: int | None = None
    maxmem: int | None = None
    disk: int | None = None
    maxdisk: int | None = None
    ssl_fingerprint: str | None = None
    level: str | None = None
    location: str | None = None
    loadavg: list[float] | None = None

    @field_validator("cpu", mode="before")
    @classmethod
    def _coerce_cpu(cls, v: object) -> float | None:
        if v is None:
            return None
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @field_validator(
        "mem", "maxmem", "disk", "maxdisk", "uptime", "maxcpu", mode="before"
    )
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @field_validator("loadavg", mode="before")
    @classmethod
    def _coerce_loadavg(cls, v: object) -> list[float] | None:
        if v is None:
            return None
        if isinstance(v, (list, tuple)):
            result = []
            for item in v:
                try:
                    result.append(float(item))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    pass
            return result or None
        if isinstance(v, str):
            parts = v.split()
            try:
                return [float(p) for p in parts[:3]]
            except ValueError:
                return None
        return None


class ProxmoxClusterSummary(ProxboxBaseModel):
    """Normalised cluster summary for dashboard display."""

    name: str = "—"
    mode: str = "—"
    quorate: bool = False
    nodes_total: int = 0
    nodes_online: int = 0
    nodes_offline: int = 0

    @classmethod
    def from_status_response(
        cls, response: ProxmoxClusterStatusResponse
    ) -> ProxmoxClusterSummary:
        """Handle from status response."""
        cr = response.cluster_record
        nr = response.node_records
        total = (cr.nodes if cr and cr.nodes is not None else len(nr)) or len(nr)
        online = sum(1 for r in nr if r.online)
        if online == 0:
            online = sum(1 for r in nr if r.status == "online")
        return cls(
            name=(cr.name or "—") if cr else "—",
            mode=(cr.level or cr.type or "—") if cr else "—",
            quorate=bool(cr.quorate) if cr else False,
            nodes_total=total,
            nodes_online=online,
            nodes_offline=max(total - online, 0),
        )


class ProxmoxNodeRow(ProxboxBaseModel):
    """Rendered node row for dashboard display."""

    name: str
    status: str = "unknown"
    uptime: str = "—"
    cpu_pct: float = 0.0
    cpu_label: str = ""
    loadavg: str = "—"
    memory_pct: float = 0.0
    memory_label: str = ""
    disk_pct: float = 0.0
    disk_label: str = ""

    @classmethod
    def _from_values(
        cls,
        *,
        name: str,
        status: str,
        uptime: str,
        cpu_pct: float,
        cpu_label: str,
        loadavg: str,
        memory_pct: float,
        memory_label: str,
        disk_pct: float,
        disk_label: str,
    ) -> ProxmoxNodeRow:
        """Build a dashboard row from already-normalised values."""
        return cls(
            name=name,
            status=status,
            uptime=uptime,
            cpu_pct=cpu_pct,
            cpu_label=cpu_label,
            loadavg=loadavg,
            memory_pct=memory_pct,
            memory_label=memory_label,
            disk_pct=disk_pct,
            disk_label=disk_label,
        )

    @classmethod
    def from_node_detail(cls, detail: ProxmoxNodeDetail) -> ProxmoxNodeRow:
        """Handle from node detail."""
        mem_used = detail.mem or 0
        mem_total = detail.maxmem or 0
        disk_used = detail.disk or 0
        disk_total = detail.maxdisk or 0
        cpu_pct = cpu_percent(detail.cpu)
        mem_pct = percent(mem_used, mem_total)
        disk_pct = percent(disk_used, disk_total)
        return cls(
            name=detail.node,
            status=detail.status or "unknown",
            uptime=format_uptime(detail.uptime),
            cpu_pct=cpu_pct,
            cpu_label=f"{cpu_pct:.2f}% ({detail.maxcpu or 0} CPUs)",
            loadavg=loadavg_text(detail.loadavg),
            memory_pct=mem_pct,
            memory_label=f"{format_bytes(mem_used)} / {format_bytes(mem_total)}",
            disk_pct=disk_pct,
            disk_label=f"{format_bytes(disk_used)} / {format_bytes(disk_total)}",
        )

    @classmethod
    def from_node_model(cls, node: object) -> ProxmoxNodeRow:
        """Render a persisted ``ProxmoxNode`` row for the dashboard card."""
        name = str(getattr(node, "name", "") or "—")
        online = bool(getattr(node, "online", False))
        cpu_value = getattr(node, "cpu_usage_percent", None)
        if cpu_value is None:
            cpu_value = getattr(node, "cpu_usage", None)
        cpu_pct = cpu_percent(cpu_value)
        max_cpu = int(getattr(node, "max_cpu", 0) or 0)

        memory_used = getattr(node, "memory_usage", None)
        memory_total = getattr(node, "max_memory", None)
        if memory_used is None and memory_total is None:
            memory_pct = 0.0
            memory_label = "—"
        else:
            memory_used = memory_used or 0
            memory_total = memory_total or 0
            memory_pct = percent(memory_used, memory_total)
            memory_label = f"{format_bytes(memory_used)} / {format_bytes(memory_total)}"

        cpu_label = f"{cpu_pct:.2f}% ({max_cpu} CPUs)" if cpu_value is not None else "—"
        status = "online" if online else "offline"

        return cls._from_values(
            name=name,
            status=status,
            uptime="—",
            cpu_pct=cpu_pct,
            cpu_label=cpu_label,
            loadavg="—",
            memory_pct=memory_pct,
            memory_label=memory_label,
            disk_pct=0.0,
            disk_label="—",
        )
