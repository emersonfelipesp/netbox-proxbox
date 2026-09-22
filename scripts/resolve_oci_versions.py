#!/usr/bin/env python3
"""Resolve the newest stable PyPI releases used by the OCI appliance."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version


PYPI_JSON = "https://pypi.org/pypi/{package}/json"


def _metadata(package: str) -> dict:
    with urllib.request.urlopen(
        PYPI_JSON.format(package=package), timeout=30
    ) as response:
        return json.load(response)


def latest_compatible(package: str, python_version: Version) -> Version:
    """Return the newest stable release with a compatible, non-yanked file."""
    releases = _metadata(package)["releases"]
    candidates: list[Version] = []
    for raw_version, files in releases.items():
        version = Version(raw_version)
        if version.is_prerelease or version.is_devrelease:
            continue
        for file in files:
            requirement = file.get("requires_python") or ""
            if file.get("yanked", False):
                continue
            if requirement and python_version not in SpecifierSet(requirement):
                continue
            candidates.append(version)
            break
    if not candidates:
        raise RuntimeError(
            f"PyPI has no stable {package} artifact compatible with "
            f"Python {python_version}"
        )
    return max(candidates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbox-python", default="3.14")
    parser.add_argument("--proxbox-api-python", default="3.13")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    netbox_python = Version(args.netbox_python)
    backend_python = Version(args.proxbox_api_python)
    plugin_version = latest_compatible("netbox-proxbox", netbox_python)
    backend_version = latest_compatible("proxbox-api", backend_python)

    values = {
        "netbox_proxbox_version": str(plugin_version),
        "proxbox_api_version": str(backend_version),
        "proxbox_api_python": str(backend_python),
    }
    output = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as destination:
            destination.write(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
