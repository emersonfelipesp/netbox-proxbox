"""Refuse a wheel or sdist that still ships a removed module.

Source-tree tests cannot see what the build back end packaged, and a stale
include rule would put a deleted module back into every install. This check
reads the artifact member lists themselves and is run by CI right after the
build, before ``twine check``.

Usage: ``python scripts/check_dist_inventory.py dist/*.whl dist/*.tar.gz``
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

# Paths (relative to the package root inside the artifact) that must never be
# packaged again. Keep this list in step with tests/test_module_layout.py.
REMOVED_MODULES: tuple[str, ...] = (
    "netbox_proxbox/services/sync_backup_routines.py",
    "netbox_proxbox/services/sync_sdn.py",
    "netbox_proxbox/utils.py",
)


def artifact_members(path: Path) -> list[str]:
    """Return the member names of a wheel or sdist."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as wheel:
            return wheel.namelist()
    with tarfile.open(path) as sdist:
        return sdist.getnames()


def forbidden_members(members: list[str]) -> list[str]:
    """Members that name a removed module, wherever the artifact nests them."""
    return [
        member
        for member in members
        if any(
            member == removed or member.endswith("/" + removed)
            for removed in REMOVED_MODULES
        )
    ]


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_dist_inventory.py <artifact>...", file=sys.stderr)
        return 2
    failed = False
    for raw in argv:
        path = Path(raw)
        offenders = forbidden_members(artifact_members(path))
        if offenders:
            failed = True
            print(f"{path.name}: ships removed modules: {offenders}", file=sys.stderr)
        else:
            print(f"{path.name}: inventory clean")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
