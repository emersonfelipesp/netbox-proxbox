"""Validate Proxbox against one explicitly identified netbox-sdk artifact.

This cross-repository gate is intentionally not part of Proxbox's isolated test
environment.  Its caller must provide the SDK root, exact module origin, and one
immutable expected identity.  The gate never trusts ambient ``PYTHONPATH`` or an
arbitrary installed ``netbox_sdk`` package.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "proxbox_bridge_v1.json"
_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_GIT_REF_RE = re.compile(r"refs/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


class PairedSDKGateError(RuntimeError):
    """The supplied SDK artifact or its bridge behavior is not trusted."""


def _bounded_text(path: Path, *, limit: int = 4096) -> str:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = stream.read(limit + 1)
    except OSError as exc:
        raise PairedSDKGateError(f"cannot read SDK identity file: {path}") from exc
    if len(value) > limit:
        raise PairedSDKGateError(f"SDK identity file is unexpectedly large: {path}")
    return value.strip()


def _git_directory(sdk_root: Path) -> Path:
    git_entry = sdk_root / ".git"
    if git_entry.is_dir():
        return git_entry.resolve(strict=True)
    if not git_entry.is_file():
        raise PairedSDKGateError("--expected-commit requires an SDK Git checkout")
    pointer = _bounded_text(git_entry)
    if not pointer.startswith("gitdir: "):
        raise PairedSDKGateError("SDK .git file is not a Git-directory pointer")
    target = Path(pointer.removeprefix("gitdir: "))
    if not target.is_absolute():
        target = git_entry.parent / target
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError("SDK Git directory does not exist") from exc
    if not resolved.is_dir():
        raise PairedSDKGateError("SDK Git directory is not a directory")
    return resolved


def _git_common_directory(git_directory: Path) -> Path:
    common_pointer = git_directory / "commondir"
    if not common_pointer.exists():
        return git_directory
    target = Path(_bounded_text(common_pointer))
    if not target.is_absolute():
        target = git_directory / target
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError("SDK common Git directory does not exist") from exc
    if not resolved.is_dir():
        raise PairedSDKGateError("SDK common Git directory is not a directory")
    return resolved


def _commit_from_packed_refs(git_directory: Path, ref: str) -> str | None:
    packed_refs = git_directory / "packed-refs"
    if not packed_refs.exists():
        return None
    for line in _bounded_text(packed_refs, limit=1024 * 1024).splitlines():
        if not line or line.startswith(("#", "^")):
            continue
        commit, separator, candidate_ref = line.partition(" ")
        if separator and candidate_ref == ref and _FULL_SHA_RE.fullmatch(commit):
            return commit
    return None


def _sdk_git_commit(sdk_root: Path) -> str:
    git_directory = _git_directory(sdk_root)
    common_directory = _git_common_directory(git_directory)
    head = _bounded_text(git_directory / "HEAD")
    if _FULL_SHA_RE.fullmatch(head):
        return head
    if not head.startswith("ref: "):
        raise PairedSDKGateError("SDK Git HEAD has an unsupported format")
    ref = head.removeprefix("ref: ")
    if (
        _GIT_REF_RE.fullmatch(ref) is None
        or ".." in ref
        or "//" in ref
        or ref.endswith("/")
    ):
        raise PairedSDKGateError("SDK Git HEAD contains an invalid ref")
    for directory in (git_directory, common_directory):
        loose_ref = directory / ref
        if loose_ref.exists():
            commit = _bounded_text(loose_ref)
            if _FULL_SHA_RE.fullmatch(commit):
                return commit
            raise PairedSDKGateError("SDK Git ref does not contain a full commit SHA")
        packed_commit = _commit_from_packed_refs(directory, ref)
        if packed_commit is not None:
            return packed_commit
    raise PairedSDKGateError("SDK Git HEAD ref cannot be resolved")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-root",
        required=True,
        type=Path,
        help="Exact source or installed-package root containing netbox_sdk/.",
    )
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument(
        "--expected-commit",
        help="Exact lowercase 40-character Git commit for a source checkout.",
    )
    identity.add_argument(
        "--expected-version",
        help="Exact released netbox_sdk.__version__ for an installed artifact.",
    )
    parser.add_argument(
        "--expected-module-origin",
        required=True,
        type=Path,
        help="Absolute expected path of netbox_sdk/plugin_bridge.py.",
    )
    return parser.parse_args(argv)


def _load_identified_sdk(arguments: argparse.Namespace):
    try:
        sdk_root = arguments.sdk_root.resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError("SDK root does not exist") from exc
    if not sdk_root.is_dir():
        raise PairedSDKGateError("SDK root is not a directory")

    origin_argument = arguments.expected_module_origin
    if not origin_argument.is_absolute():
        raise PairedSDKGateError("--expected-module-origin must be absolute")
    try:
        expected_origin = origin_argument.resolve(strict=True)
        canonical_origin = (sdk_root / "netbox_sdk" / "plugin_bridge.py").resolve(
            strict=True
        )
    except OSError as exc:
        raise PairedSDKGateError("expected SDK bridge module does not exist") from exc
    if expected_origin != canonical_origin:
        raise PairedSDKGateError(
            "expected module origin is not sdk-root/netbox_sdk/plugin_bridge.py"
        )

    expected_commit = arguments.expected_commit
    if expected_commit is not None:
        if _FULL_SHA_RE.fullmatch(expected_commit) is None:
            raise PairedSDKGateError("--expected-commit must be a lowercase full SHA")
        actual_commit = _sdk_git_commit(sdk_root)
        if actual_commit != expected_commit:
            raise PairedSDKGateError(
                f"SDK commit mismatch: expected {expected_commit}, got {actual_commit}"
            )

    root_string = str(sdk_root)
    if root_string in sys.path:
        sys.path.remove(root_string)
    sys.path.insert(0, root_string)
    importlib.invalidate_caches()
    sdk_package = importlib.import_module("netbox_sdk")
    bridge_module = importlib.import_module("netbox_sdk.plugin_bridge")

    module_file = getattr(bridge_module, "__file__", None)
    if not module_file or Path(module_file).resolve(strict=True) != expected_origin:
        raise PairedSDKGateError("imported SDK bridge module has the wrong origin")

    expected_version = arguments.expected_version
    if expected_version is not None:
        if (
            not expected_version
            or len(expected_version) > 100
            or expected_version.strip() != expected_version
        ):
            raise PairedSDKGateError("--expected-version must be exact nonblank text")
        actual_version = getattr(sdk_package, "__version__", None)
        if actual_version != expected_version:
            raise PairedSDKGateError(
                f"SDK version mismatch: expected {expected_version!r}, "
                f"got {actual_version!r}"
            )
    return bridge_module


def _validate_behavior(bridge_module) -> None:
    manifest_model = bridge_module.PluginManifest
    validate_arguments = bridge_module.validate_plugin_tool_arguments
    bridge_error = bridge_module.PluginBridgeError
    manifest = manifest_model.model_validate(json.loads(MANIFEST_FIXTURE.read_text()))
    schedule_tool = next(
        tool for tool in manifest.tools if tool.name == "schedule_sync"
    )

    accepted = (
        {"sync_stages": ["virtual-machines"]},
        {
            "sync_stages": ["storage"],
            "proxmox_endpoint_ids": [7.0],
            "recurrence": {"hours": 6.0},
        },
        {
            "sync_stages": ["storage"],
            "proxmox_endpoint_ids": [9_007_199_254_740_991.0],
            "schedule_at": "2099-01-15T03:00:00Z",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "2099-12-31T23:59:60Z",
        },
    )
    for value in accepted:
        try:
            validate_arguments(schedule_tool, value)
        except bridge_error as exc:
            raise PairedSDKGateError(
                f"paired SDK rejected valid arguments: {value!r}"
            ) from exc

    rejected = (
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": [7.5]},
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": [7, 7.0]},
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": [True]},
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": ["7"]},
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": [float("inf")]},
        {"sync_stages": ["storage"], "proxmox_endpoint_ids": [float("nan")]},
        {
            "sync_stages": ["storage"],
            "proxmox_endpoint_ids": [9_007_199_254_740_992.0],
        },
        {
            "sync_stages": ["storage"],
            "proxmox_endpoint_ids": [9_223_372_036_854_775_808],
        },
        {"sync_stages": ["storage"], "recurrence": {"hours": 1.5}},
        {
            "sync_stages": ["storage"],
            "schedule_at": "9999-12-31T23:59:60Z",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "9999-12-31T23:59:59-23:59",
        },
    )
    unexpectedly_accepted: list[dict[str, object]] = []
    for value in rejected:
        try:
            validate_arguments(schedule_tool, value)
        except bridge_error:
            continue
        unexpectedly_accepted.append(value)
    if unexpectedly_accepted:
        raise PairedSDKGateError(
            f"paired SDK accepted invalid argument vector(s): {unexpectedly_accepted!r}"
        )


def main(argv: list[str] | None = None) -> None:
    """Fail closed unless one immutable paired SDK passes every vector."""
    arguments = _parse_args(argv)
    bridge_module = _load_identified_sdk(arguments)
    _validate_behavior(bridge_module)


if __name__ == "__main__":
    try:
        main()
    except PairedSDKGateError as exc:
        raise SystemExit(f"paired SDK gate failed: {exc}") from exc
