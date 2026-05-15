"""Render the ``netbox-metadata`` fenced block embedded in Proxmox descriptions.

Counterpart to ``proxbox_api.proxmox_to_netbox.description_metadata`` on the
backend: that module *parses* fenced blocks of the form ::

    ```netbox-metadata
    {"role": 1, "tenant": 13}
    ```

out of a Proxmox description and applies the PK ids onto the NetBox object.
This module is the write-side mirror — it *builds* the same fenced block from
a NetBox virtual machine's PK foreign keys so the intent path
(``netbox-proxbox`` -> ``proxbox-api`` -> Proxmox) can embed it into the
Proxmox VM/CT ``description`` at create / update time.

Embedding the block on the write side closes the round-trip: a subsequent
Proxmox -> NetBox reflection sync with ``parse_description_metadata=True``
will read the same PKs back without drift (the #357 drift-detect invariant).

Issue: https://github.com/emersonfelipesp/netbox-proxbox/issues/423
"""

from __future__ import annotations

import json
import re
from typing import Any

# Keep the regex shape in lock-step with
# ``proxbox_api.proxmox_to_netbox.description_metadata._FENCE_RE`` so a block
# emitted here is recognised by the parser and so existing blocks are stripped
# cleanly on update.
_FENCE_RE = re.compile(
    r"^[ \t]*```[ \t]*netbox-metadata[ \t]*\r?\n(?P<body>.*?)\r?\n[ \t]*```[ \t]*$",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# NetBox VM attributes that resolve to a single foreign-key id. Each entry is
# ``(metadata_key, attr_chain)``. ``attr_chain`` is walked via ``getattr`` so
# ``("role", "id")`` looks up ``vm.role.id``. Keys are restricted to the
# read-side parser's currently-honoured set; new keys here have no effect until
# the parser learns them.
_PK_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("role", ("role", "id")),
    ("tenant", ("tenant", "id")),
    ("site", ("site", "id")),
    ("platform", ("platform", "id")),
    ("cluster", ("cluster", "id")),
    ("device", ("device", "id")),
)


def _resolve(obj: Any, chain: tuple[str, ...]) -> Any:
    current: Any = obj
    for attr in chain:
        if current is None:
            return None
        current = getattr(current, attr, None)
    return current


def collect_netbox_metadata(vm: Any) -> dict[str, int]:
    """Return a ``{key: pk}`` dict of NetBox FK ids present on ``vm``.

    Missing relations (``vm.role is None``) are silently omitted so the
    resulting block only describes what NetBox actually knows. Non-positive
    or non-integer ids are dropped to match the parser's accepted shape.
    """
    out: dict[str, int] = {}
    for key, chain in _PK_FIELDS:
        value = _resolve(vm, chain)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value <= 0:
            continue
        out[key] = value
    return out


def render_netbox_metadata_block(metadata: dict[str, int]) -> str | None:
    """Render ``metadata`` as a fenced ``netbox-metadata`` block.

    Returns ``None`` if ``metadata`` is empty so callers can leave the
    description untouched. JSON is emitted with sorted keys so repeated
    builds of the same PK set produce byte-identical output (drift-detect).
    """
    if not metadata:
        return None
    body = json.dumps(metadata, sort_keys=True, indent=2)
    return "```netbox-metadata\n" + body + "\n```"


def strip_netbox_metadata(text: str | None) -> str | None:
    """Return ``text`` with every ``netbox-metadata`` fenced block removed.

    Trailing whitespace is trimmed; an empty result collapses to ``None`` so
    callers can decide to omit ``description`` entirely instead of writing a
    blank string.
    """
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text).rstrip()
    return cleaned or None


def embed_netbox_metadata(description: str | None, block: str | None) -> str | None:
    """Append ``block`` to ``description`` after a single blank line.

    Any existing ``netbox-metadata`` block is stripped first so repeated
    applies do not stack. Returns ``None`` if both inputs are empty.
    """
    if block is None:
        return strip_netbox_metadata(description)
    base = strip_netbox_metadata(description)
    if base is None:
        return block
    return base + "\n\n" + block


def build_description_with_metadata(vm: Any, description: str | None) -> str | None:
    """High-level helper used by ``build_vm_payload`` / ``build_lxc_payload``.

    Combines ``collect_netbox_metadata``, ``render_netbox_metadata_block`` and
    ``embed_netbox_metadata`` into one call. The caller is responsible for the
    plugin-settings opt-in gate; this helper unconditionally rebuilds the
    block.
    """
    metadata = collect_netbox_metadata(vm)
    block = render_netbox_metadata_block(metadata)
    return embed_netbox_metadata(description, block)


__all__ = [
    "build_description_with_metadata",
    "collect_netbox_metadata",
    "embed_netbox_metadata",
    "render_netbox_metadata_block",
    "strip_netbox_metadata",
]
