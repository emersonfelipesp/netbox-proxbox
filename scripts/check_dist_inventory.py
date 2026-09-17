"""Refuse a wheel or sdist that ships a forbidden artifact path.

Source-tree tests cannot see what the build back end packaged. A stale include
rule can restore deleted code, while generated documentation can leak derived
workspace output into a source distribution. This check reads normalized
artifact member paths and is run by CI right after the build, before
``twine check``.

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

# Generated workspace roots that are never reviewed package source. An sdist
# nests these below its versioned top-level directory, while a wheel does not.
GENERATED_ROOTS: tuple[str, ...] = (".ci-site",)


def artifact_members(path: Path) -> list[str]:
    """Return the member names of a wheel or sdist."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as wheel:
            return wheel.namelist()
    with tarfile.open(path) as sdist:
        return sdist.getnames()


def forbidden_members(members: list[str]) -> list[str]:
    """Members that name removed code or generated workspace output."""
    return [
        member
        for member in members
        if (
            any(
                member.replace("\\", "/") == removed
                or member.replace("\\", "/").endswith("/" + removed)
                for removed in REMOVED_MODULES
            )
            or any(
                root in member.replace("\\", "/").split("/") for root in GENERATED_ROOTS
            )
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
            print(f"{path.name}: ships forbidden paths: {offenders}", file=sys.stderr)
        else:
            print(f"{path.name}: inventory clean")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
