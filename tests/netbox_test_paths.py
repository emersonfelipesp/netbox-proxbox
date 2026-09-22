"""Provider-neutral discovery of an optional real-NetBox source checkout."""

from __future__ import annotations

import os
from pathlib import Path


def netbox_source_roots(repo_root: Path) -> tuple[Path, ...]:
    """Prefer the explicit CI source root, then an ordinary sibling checkout."""
    configured = os.environ.get("NETBOX_SOURCE_ROOT", "").strip()
    roots = [repo_root.parent / "netbox" / "netbox"]
    if configured:
        roots.insert(0, Path(configured).expanduser())
    return tuple(roots)
