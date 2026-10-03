"""Validate values that are interpolated into proxbox-api request paths.

Node names, storage names, guest types, and VMIDs reach backend URLs from
NetBox data that users can edit (for example a ``dcim.Device`` name). A value
such as ``../extras`` would be collapsed by URL normalisation and send the
authenticated backend request to a different route. Every such value must
pass through one of these helpers before it is placed in a URL path. The
helpers fail closed: they raise instead of trying to repair the value.
"""

from __future__ import annotations

import re
from urllib.parse import quote

__all__ = (
    "UnsafeBackendPathSegment",
    "safe_path_segment",
    "safe_vm_type",
    "safe_vmid",
)

# Proxmox node and storage identifiers are DNS-label like. NetBox device names
# may also be dotted FQDN-style names, so dots, underscores, and hyphens are
# allowed after a leading alphanumeric character.
_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_MAX_SEGMENT_LENGTH = 253
_VM_TYPES = frozenset({"qemu", "lxc"})
# Proxmox accepts VMIDs from 100 to 999999999.
_MAX_VMID = 999_999_999


class UnsafeBackendPathSegment(ValueError):
    """Raised when a value cannot be safely placed in a backend URL path."""


def safe_path_segment(value: object) -> str:
    """Return ``value`` as one percent-encoded path segment, or raise.

    Rejects empty values, ``.``/``..``, any value with a ``..`` component,
    and any character outside the identifier allow-list (which excludes
    ``/``, ``\\``, ``?``, ``#``, ``%``, whitespace, and control characters).
    """
    text = str(value if value is not None else "").strip()
    if not text or len(text) > _MAX_SEGMENT_LENGTH:
        raise UnsafeBackendPathSegment("path segment is empty or too long")
    if _SEGMENT_RE.fullmatch(text) is None:
        raise UnsafeBackendPathSegment("path segment contains forbidden characters")
    if ".." in text:
        raise UnsafeBackendPathSegment("path segment contains a dot-dot sequence")
    return quote(text, safe="")


def safe_vm_type(value: object) -> str:
    """Return ``qemu`` or ``lxc``, or raise for any other guest type."""
    text = str(value if value is not None else "").strip().lower()
    if text not in _VM_TYPES:
        raise UnsafeBackendPathSegment("guest type must be qemu or lxc")
    return text


def safe_vmid(value: object) -> str:
    """Return a positive integer VMID as a decimal string, or raise."""
    if isinstance(value, bool):
        raise UnsafeBackendPathSegment("VMID must be a positive integer")
    text = str(value if value is not None else "").strip()
    if not text.isascii() or not text.isdigit():
        raise UnsafeBackendPathSegment("VMID must be a positive integer")
    vmid = int(text)
    if not 1 <= vmid <= _MAX_VMID:
        raise UnsafeBackendPathSegment("VMID is out of range")
    return str(vmid)
