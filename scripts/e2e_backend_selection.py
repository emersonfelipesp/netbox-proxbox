"""Deterministic backend selection for E2E and release workflows."""

from __future__ import annotations

import argparse

from packaging.version import InvalidVersion, Version

DEFAULT_DEPENDENCY_MODE = "published"
DEPENDENCY_MODES = frozenset({"dev", "published", "testpypi-package", "pypi-package"})


def resolve_dependency_mode(value: str) -> str:
    """Return a supported mode, defaulting an empty event input to published."""
    mode = value.strip() or DEFAULT_DEPENDENCY_MODE
    if mode not in DEPENDENCY_MODES:
        choices = ", ".join(sorted(DEPENDENCY_MODES))
        raise ValueError(
            f"Unsupported proxbox-api dependency mode {mode!r}; use {choices}"
        )
    return mode


def resolve_release_version(
    *, explicit: str, configured: str, required_default: str
) -> str:
    """Resolve a release backend version and reject stale implicit settings."""
    expected = validate_version(required_default)
    requested = explicit.strip()
    if requested:
        return validate_version(requested)
    selected = validate_version(configured)
    if selected != expected:
        raise ValueError(
            "Stale proxbox-api repository variable selected: "
            f"{selected!r}; expected {expected!r}. Update the release "
            "variables or provide the explicit proxbox_api_version workflow input."
        )
    return selected


def validate_version(value: str) -> str:
    """Return one canonical, nonempty PEP 440 version for workflow transport."""
    candidate = value.strip()
    try:
        parsed = Version(candidate)
    except InvalidVersion as exc:
        raise ValueError(f"Invalid proxbox-api version {candidate!r}") from exc
    if not candidate or str(parsed) != candidate:
        raise ValueError(f"Non-canonical proxbox-api version {candidate!r}")
    return candidate


def main() -> int:
    """Resolve one dependency-mode argument for the shell workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("dependency-mode", "version"))
    parser.add_argument("value", nargs="?", default="")
    args = parser.parse_args()
    try:
        resolved = (
            resolve_dependency_mode(args.value)
            if args.kind == "dependency-mode"
            else validate_version(args.value)
        )
        print(resolved)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
