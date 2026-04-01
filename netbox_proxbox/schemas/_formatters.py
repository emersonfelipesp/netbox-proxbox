"""Pure-function formatting helpers consolidated from dashboard, storage, and vm_config views."""

from __future__ import annotations

from collections.abc import Iterable


def to_int(value: object, default: int = 0) -> int:
    """Coerce *value* to int, returning *default* on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def to_float(value: object, default: float = 0.0) -> float:
    """Coerce *value* to float, returning *default* on failure."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def percent(value: object, max_value: object) -> float:
    """Return (value / max_value) * 100 rounded to 2 dp, or 0.0 on bad input."""
    val = to_float(value)
    max_val = to_float(max_value)
    if max_val <= 0:
        return 0.0
    return round((val / max_val) * 100.0, 2)


def cpu_percent(value: object) -> float:
    """Normalise a Proxmox CPU ratio (0..1) or raw percentage to a 0..100 float."""
    cpu = to_float(value)
    if cpu <= 1:
        return round(cpu * 100.0, 2)
    return round(cpu, 2)


def format_bytes(value: object) -> str:
    """Convert an integer byte count to a human-readable string (B/KiB/MiB/GiB/TiB)."""
    size = float(to_int(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"


def format_uptime(seconds: object) -> str:
    """Format an integer second count as ``Xd HH:MM:SS``, or ``—`` when zero/None."""
    total = to_int(seconds)
    if total <= 0:
        return "—"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02}:{minutes:02}:{secs:02}"


def loadavg_text(value: object) -> str:
    """Format a load-average list/tuple/string as a comma-separated display string."""
    if isinstance(value, (list, tuple)) and value:
        return ", ".join(f"{to_float(v):.2f}" for v in value[:3])
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "—"


def iter_scalar_records(payload: object) -> Iterable[dict[str, object]]:
    """Recursively yield flat dict records from nested list/dict Proxmox API payloads."""
    if isinstance(payload, list):
        for item in payload:
            yield from iter_scalar_records(item)
        return
    if isinstance(payload, dict):
        has_nested = any(isinstance(v, (dict, list)) for v in payload.values())
        if not has_nested:
            yield payload
            return
        for value in payload.values():
            yield from iter_scalar_records(value)
