#!/usr/bin/env python3
"""Resolve the newest stable PyPI releases used by the OCI appliance."""

from __future__ import annotations

import argparse
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version


PYPI_JSON = "https://pypi.org/pypi/{package}/json"


def _metadata(package: str) -> dict:
    with urllib.request.urlopen(
        PYPI_JSON.format(package=package), timeout=30
    ) as response:
        return json.load(response)


def _compatible_versions(releases: dict, python_version: Version) -> list[Version]:
    """Return stable versions that have a compatible, non-yanked file."""
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
    return candidates


_TRANSIENT = (
    urllib.error.URLError,
    http.client.HTTPException,
    TimeoutError,
    OSError,
    ValueError,
)
Fetch = Callable[[str], dict]


def retrying_fetch(
    *,
    wait_seconds: int = 0,
    poll_seconds: int = 30,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> Fetch:
    """Return a metadata reader that retries transient errors until a deadline."""
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    deadline = monotonic() + wait_seconds

    def fetch(package: str) -> dict:
        while True:
            try:
                return _metadata(package)
            except _TRANSIENT as error:
                if monotonic() >= deadline:
                    raise RuntimeError(
                        f"PyPI metadata for {package} is unavailable ({error})"
                    ) from error
                sleep(poll_seconds)

    return fetch


def latest_compatible(
    package: str, python_version: Version, *, fetch: Fetch | None = None
) -> Version:
    """Return the newest stable release with a compatible, non-yanked file."""
    releases = (fetch or _metadata)(package)["releases"]
    candidates = _compatible_versions(releases, python_version)
    if not candidates:
        raise RuntimeError(
            f"PyPI has no stable {package} artifact compatible with "
            f"Python {python_version}"
        )
    return max(candidates)


def newest_published(package: str, *, fetch: Fetch | None = None) -> Version:
    """Return the newest stable release ever published, even if yanked.

    Promotion order must not depend on installation eligibility: a yanked or
    Python-incompatible newer release still owns the moving image tag.
    """
    releases = (fetch or _metadata)(package)["releases"]
    versions = [
        version
        for raw, files in releases.items()
        if files
        for version in [Version(raw)]
        if not (version.is_prerelease or version.is_devrelease)
    ]
    if not versions:
        raise RuntimeError(f"PyPI has no stable {package} release")
    return max(versions)


def exact_compatible(
    package: str,
    wanted: Version,
    python_version: Version,
    *,
    wait_seconds: int = 0,
    poll_seconds: int = 30,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    fetch: Fetch | None = None,
) -> Version:
    """Return ``wanted`` once PyPI serves a compatible, stable artifact for it.

    Polls until ``wait_seconds`` elapse so a release build does not race the
    PyPI publication of the same release.
    """
    if wanted.is_prerelease or wanted.is_devrelease:
        raise RuntimeError(
            f"{package} {wanted} is a prerelease and is not published as an image"
        )
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    deadline = monotonic() + wait_seconds
    read = fetch or retrying_fetch(
        wait_seconds=wait_seconds,
        poll_seconds=poll_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )
    while True:
        if wanted in _compatible_versions(read(package)["releases"], python_version):
            return wanted
        if monotonic() >= deadline:
            raise RuntimeError(
                f"PyPI has no stable {package} {wanted} artifact compatible "
                f"with Python {python_version}"
            )
        sleep(poll_seconds)


def tag_to_version(tag: str) -> Version:
    """Map a release tag such as ``v0.0.29.post2`` to its package version."""
    return Version(tag.removeprefix("v"))


def _write_outputs(values: dict[str, str], destination: Path | None) -> None:
    output = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    if destination:
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")


def _check_promotion(args: argparse.Namespace) -> int:
    """Report whether the version may move the mutable image tag.

    Called after the versioned image is published, with fresh metadata, so a
    newer release that appeared during the build is still honored.
    """
    fetch = retrying_fetch(
        wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds
    )
    version = tag_to_version(args.check_promotion)
    newest = newest_published("netbox-proxbox", fetch=fetch)
    # The mutable image tag must never move to an older release.
    _write_outputs(
        {"publish_moving_tag": str(version >= newest).lower()}, args.github_output
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbox-python", default="3.14")
    parser.add_argument("--proxbox-api-python", default="3.13")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument(
        "--plugin-version",
        help="exact netbox-proxbox release tag or version to install",
    )
    parser.add_argument(
        "--check-promotion",
        metavar="VERSION",
        help="report whether VERSION may move the mutable image tag, then exit",
    )
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    if args.check_promotion:
        return _check_promotion(args)

    netbox_python = Version(args.netbox_python)
    backend_python = Version(args.proxbox_api_python)
    fetch = retrying_fetch(
        wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds
    )
    if args.plugin_version:
        plugin_version = exact_compatible(
            "netbox-proxbox",
            tag_to_version(args.plugin_version),
            netbox_python,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            fetch=fetch,
        )
    else:
        plugin_version = latest_compatible("netbox-proxbox", netbox_python, fetch=fetch)
    backend_version = latest_compatible("proxbox-api", backend_python, fetch=fetch)

    values = {
        "netbox_proxbox_version": str(plugin_version),
        "proxbox_api_version": str(backend_version),
        "proxbox_api_python": str(backend_python),
    }
    _write_outputs(values, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
