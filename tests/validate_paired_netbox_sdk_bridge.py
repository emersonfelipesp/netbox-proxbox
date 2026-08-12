"""Validate Proxbox against one explicitly identified netbox-sdk artifact.

This cross-repository gate is intentionally not part of Proxbox's isolated test
environment.  Its caller must provide the SDK root, exact module origin, and one
immutable expected identity.  The gate never trusts ambient ``PYTHONPATH`` or an
arbitrary installed ``netbox_sdk`` package.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import resource
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "proxbox_bridge_v1.json"
_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SDK_PATH_COMPONENT_RE = re.compile(r"[A-Za-z0-9_.-]+\Z")
_EXPECTED_MODULE_ORIGIN = Path("netbox_sdk/plugin_bridge.py")
_GIT_EXECUTABLE = Path("/usr/bin/git")
_MAX_SDK_FILES = 5_000
_MAX_SDK_FILE_BYTES = 32 * 1024 * 1024
_MAX_SDK_TREE_BYTES = 256 * 1024 * 1024
_MAX_GIT_TREE_BYTES = 4 * 1024 * 1024
_MAX_GIT_STDERR_BYTES = 64 * 1024


class PairedSDKGateError(RuntimeError):
    """The supplied SDK artifact or its bridge behavior is not trusted."""


def _git_environment() -> dict[str, str]:
    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def _run_git(
    sdk_root: Path,
    *arguments: str,
    max_stdout_bytes: int,
) -> bytes:
    if not _GIT_EXECUTABLE.is_file():
        raise PairedSDKGateError("trusted Git executable is unavailable")

    file_limit = max(max_stdout_bytes, _MAX_GIT_STDERR_BYTES) + 1

    def _limit_output_files() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))

    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.run(
                [
                    str(_GIT_EXECUTABLE),
                    "-c",
                    "core.attributesFile=/dev/null",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.untrackedCache=false",
                    "-C",
                    str(sdk_root),
                    *arguments,
                ],
                check=False,
                env=_git_environment(),
                preexec_fn=_limit_output_files,
                stderr=stderr,
                stdout=stdout,
                timeout=30,
            )
            stdout_size = stdout.tell()
            stderr_size = stderr.tell()
            if stdout_size > max_stdout_bytes or stderr_size > _MAX_GIT_STDERR_BYTES:
                raise PairedSDKGateError("SDK Git command exceeded its output limit")
            stdout.seek(0)
            output = stdout.read(max_stdout_bytes + 1)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PairedSDKGateError("SDK Git command could not complete safely") from exc
    if process.returncode != 0:
        raise PairedSDKGateError(
            f"SDK Git command failed safely: {arguments[0] if arguments else 'git'}"
        )
    return output


def _require_exact_head(sdk_root: Path, expected_commit: str) -> None:
    actual_commit = (
        _run_git(
            sdk_root,
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
            max_stdout_bytes=128,
        )
        .decode("ascii", "strict")
        .strip()
    )
    if actual_commit != expected_commit:
        raise PairedSDKGateError(
            f"SDK commit mismatch: expected {expected_commit}, got {actual_commit}"
        )


def _verify_commit_object_graph(sdk_root: Path, expected_commit: str) -> None:
    object_format = (
        _run_git(
            sdk_root,
            "rev-parse",
            "--show-object-format",
            max_stdout_bytes=32,
        )
        .decode("ascii", "strict")
        .strip()
    )
    if object_format != "sha1":
        raise PairedSDKGateError("SDK repository object format is unsupported")
    _run_git(
        sdk_root,
        "fsck",
        "--strict",
        "--no-dangling",
        "--no-reflogs",
        "--no-progress",
        expected_commit,
        max_stdout_bytes=_MAX_GIT_TREE_BYTES,
    )


def _verify_blob_identity(object_id: str, body: bytes) -> None:
    digest = hashlib.sha1(  # noqa: S324 - Git repository object format is SHA-1.
        b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    ).hexdigest()
    if digest != object_id:
        raise PairedSDKGateError("SDK blob contents do not match their object identity")


def _canonical_sdk_relative_path(raw_path: bytes) -> str:
    try:
        relative_path = raw_path.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise PairedSDKGateError("SDK package path is not canonical ASCII") from exc
    parts = relative_path.split("/")
    if (
        len(parts) < 2
        or parts[0] != "netbox_sdk"
        or any(
            part in {"", ".", ".."} or _SDK_PATH_COMPONENT_RE.fullmatch(part) is None
            for part in parts
        )
    ):
        raise PairedSDKGateError("SDK package path is unsafe")
    return relative_path


def _bounded_file_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            body = stream.read(_MAX_SDK_FILE_BYTES + 1)
    except OSError as exc:
        raise PairedSDKGateError("SDK checkout package file cannot be read") from exc
    if len(body) > _MAX_SDK_FILE_BYTES:
        raise PairedSDKGateError("SDK checkout package file exceeds the size limit")
    return body


def _source_package_files(sdk_root: Path) -> dict[str, tuple[bytes, bool]]:
    package_root = sdk_root / "netbox_sdk"
    try:
        package_stat = package_root.lstat()
    except OSError as exc:
        raise PairedSDKGateError("SDK checkout package directory is missing") from exc
    if not stat.S_ISDIR(package_stat.st_mode) or package_root.is_symlink():
        raise PairedSDKGateError("SDK checkout package directory is unsafe")

    files: dict[str, tuple[bytes, bool]] = {}
    stack = [package_root]
    total_bytes = 0
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
        except OSError as exc:
            raise PairedSDKGateError(
                "SDK checkout package cannot be enumerated"
            ) from exc
        for entry in entries:
            if entry.name == "__pycache__":
                if entry.is_symlink():
                    raise PairedSDKGateError("SDK checkout cache path is unsafe")
                continue
            try:
                entry_stat = entry.lstat()
            except OSError as exc:
                raise PairedSDKGateError(
                    "SDK checkout package entry cannot be read"
                ) from exc
            if stat.S_ISDIR(entry_stat.st_mode):
                stack.append(entry)
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise PairedSDKGateError(
                    "SDK checkout package contains an unsafe entry"
                )
            relative_path = entry.relative_to(sdk_root).as_posix()
            try:
                raw_relative_path = relative_path.encode("ascii", "strict")
            except UnicodeEncodeError as exc:
                raise PairedSDKGateError(
                    "SDK package path is not canonical ASCII"
                ) from exc
            _canonical_sdk_relative_path(raw_relative_path)
            body = _bounded_file_bytes(entry)
            total_bytes += len(body)
            if total_bytes > _MAX_SDK_TREE_BYTES or len(files) >= _MAX_SDK_FILES:
                raise PairedSDKGateError(
                    "SDK checkout package exceeds its resource limits"
                )
            files[relative_path] = (body, bool(entry_stat.st_mode & stat.S_IXUSR))
    return files


def _require_source_matches_snapshot(sdk_root: Path, snapshot_root: Path) -> None:
    if _source_package_files(sdk_root) != _source_package_files(snapshot_root):
        raise PairedSDKGateError(
            "SDK checkout package must exactly match the committed package tree"
        )


def _materialize_sdk_commit(
    sdk_root: Path,
    expected_commit: str,
    destination: Path,
) -> None:
    _require_exact_head(sdk_root, expected_commit)
    _verify_commit_object_graph(sdk_root, expected_commit)
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError as exc:
        raise PairedSDKGateError(
            "private SDK snapshot cannot be created safely"
        ) from exc
    tree = _run_git(
        sdk_root,
        "ls-tree",
        "-rz",
        "--full-tree",
        expected_commit,
        "--",
        "netbox_sdk",
        max_stdout_bytes=_MAX_GIT_TREE_BYTES,
    )
    entries = [entry for entry in tree.split(b"\0") if entry]
    if not entries or len(entries) > _MAX_SDK_FILES:
        raise PairedSDKGateError("SDK commit contains an invalid package file count")

    destination_root = destination.resolve(strict=True)
    total_bytes = 0
    for entry in entries:
        metadata, separator, raw_path = entry.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise PairedSDKGateError("SDK commit tree entry is malformed")
        mode, object_type, object_id = fields
        relative_path = _canonical_sdk_relative_path(raw_path)
        try:
            decoded_object_id = object_id.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise PairedSDKGateError(
                "SDK blob identity is not canonical ASCII"
            ) from exc
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or _FULL_SHA_RE.fullmatch(decoded_object_id) is None
        ):
            raise PairedSDKGateError("SDK package tree contains an unsafe entry")
        body = _run_git(
            sdk_root,
            "cat-file",
            "blob",
            decoded_object_id,
            max_stdout_bytes=_MAX_SDK_FILE_BYTES,
        )
        _verify_blob_identity(decoded_object_id, body)
        total_bytes += len(body)
        if total_bytes > _MAX_SDK_TREE_BYTES:
            raise PairedSDKGateError("SDK package tree exceeds the size limit")
        target = destination / relative_path
        if not target.resolve(strict=False).is_relative_to(destination_root):
            raise PairedSDKGateError("SDK package path escapes the private snapshot")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        target.chmod(0o755 if mode == b"100755" else 0o644)

    if not (destination / _EXPECTED_MODULE_ORIGIN).is_file():
        raise PairedSDKGateError("SDK commit does not contain the bridge module")
    _require_exact_head(sdk_root, expected_commit)
    _verify_commit_object_graph(sdk_root, expected_commit)
    _require_source_matches_snapshot(sdk_root, destination)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-root",
        required=True,
        type=Path,
        help=(
            "SDK Git checkout whose netbox_sdk/ package exactly matches the "
            "expected commit."
        ),
    )
    parser.add_argument(
        "--expected-commit",
        required=True,
        help="Exact lowercase 40-character Git commit for a source checkout.",
    )
    parser.add_argument(
        "--expected-version",
        required=True,
        help="Exact released SDK version declared by the expected commit.",
    )
    parser.add_argument(
        "--expected-environment-root",
        required=True,
        type=Path,
        help="Absolute root of the explicitly provisioned locked SDK environment.",
    )
    parser.add_argument(
        "--expected-module-origin",
        required=True,
        type=Path,
        help="Exact relative module path netbox_sdk/plugin_bridge.py.",
    )
    return parser.parse_args(argv)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_isolated_environment(arguments: argparse.Namespace) -> Path:
    if not sys.flags.isolated:
        raise PairedSDKGateError(
            "paired SDK gate must run with Python isolated mode (-I)"
        )
    environment_argument = arguments.expected_environment_root
    if not environment_argument.is_absolute():
        raise PairedSDKGateError("--expected-environment-root must be absolute")
    try:
        expected_environment = environment_argument.resolve(strict=True)
        actual_environment = Path(sys.prefix).resolve(strict=True)
        base_environment = Path(sys.base_prefix).resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError(
            "paired SDK environment root cannot be resolved"
        ) from exc
    if expected_environment != actual_environment:
        raise PairedSDKGateError("paired SDK interpreter environment does not match")
    for entry in sys.path:
        if not entry:
            raise PairedSDKGateError(
                "paired SDK interpreter has an ambient import path"
            )
        try:
            candidate = Path(entry)
            resolved = candidate.resolve(strict=candidate.exists())
        except OSError as exc:
            raise PairedSDKGateError(
                "paired SDK import path cannot be resolved"
            ) from exc
        if _is_relative_to(resolved, expected_environment):
            continue
        if "site-packages" in resolved.parts or not _is_relative_to(
            resolved, base_environment
        ):
            raise PairedSDKGateError(
                "paired SDK interpreter import path is not trusted"
            )
    return expected_environment


def _require_dependency_origins(environment_root: Path) -> None:
    for module_name in ("jsonschema", "pydantic"):
        module = sys.modules.get(module_name)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise PairedSDKGateError(
                f"paired SDK dependency origin is missing: {module_name}"
            )
        try:
            origin = Path(module_file).resolve(strict=True)
        except OSError as exc:
            raise PairedSDKGateError(
                f"paired SDK dependency origin cannot be resolved: {module_name}"
            ) from exc
        if not _is_relative_to(origin, environment_root):
            raise PairedSDKGateError(
                f"paired SDK dependency is outside the locked environment: {module_name}"
            )


def _load_identified_sdk(
    arguments: argparse.Namespace,
    snapshot_root: Path,
    environment_root: Path,
):
    origin_argument = arguments.expected_module_origin
    if origin_argument != _EXPECTED_MODULE_ORIGIN:
        raise PairedSDKGateError(
            "--expected-module-origin must be netbox_sdk/plugin_bridge.py"
        )
    try:
        expected_origin = (snapshot_root / origin_argument).resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError("expected SDK bridge module does not exist") from exc

    for module_name in tuple(sys.modules):
        if module_name == "netbox_sdk" or module_name.startswith("netbox_sdk."):
            del sys.modules[module_name]
    root_string = str(snapshot_root)
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
    if (
        not expected_version
        or len(expected_version) > 100
        or expected_version.strip() != expected_version
    ):
        raise PairedSDKGateError("--expected-version must be exact nonblank text")
    if getattr(sdk_package, "__version__", None) != expected_version:
        raise PairedSDKGateError("identified SDK version does not match")
    _require_dependency_origins(environment_root)
    return bridge_module


def _validate_behavior(bridge_module) -> None:
    manifest_model = bridge_module.PluginManifest
    validate_arguments = bridge_module.validate_plugin_tool_arguments
    validate_response = bridge_module.validate_plugin_tool_response
    bridge_error = bridge_module.PluginBridgeError
    manifest = manifest_model.model_validate(json.loads(MANIFEST_FIXTURE.read_text()))
    list_tool = next(tool for tool in manifest.tools if tool.name == "list_sync_jobs")
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
        {
            "sync_stages": ["storage"],
            "schedule_at": "2100-01-01T00:59:60+01:00",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "2099-12-31T18:59:60-05:00",
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
            "schedule_at": "9999-12-31T23:59:60+23:59",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "9999-12-31T23:59:59-23:59",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "2026-08-12T12:34:60Z",
        },
        {
            "sync_stages": ["storage"],
            "schedule_at": "2099-12-31T23:59:60+01:00",
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

    response = {
        "count": 1,
        "scheduled_jobs": [
            {
                "id": 1,
                "pk": 1,
                "name": "paired",
                "sync_types": ["storage"],
                "schedule": "2100-01-01T00:59:60+01:00",
                "interval": None,
                "status": "scheduled",
            }
        ],
    }
    try:
        validate_response(list_tool, response)
    except bridge_error as exc:
        raise PairedSDKGateError(
            "paired SDK rejected a valid response leap instant"
        ) from exc
    for accepted_id in (
        1,
        9_007_199_254_740_991.0,
        9_223_372_036_854_775_807,
    ):
        response["scheduled_jobs"][0]["id"] = accepted_id
        response["scheduled_jobs"][0]["pk"] = accepted_id
        try:
            validate_response(list_tool, response)
        except bridge_error as exc:
            raise PairedSDKGateError(
                f"paired SDK rejected valid response identity: {accepted_id!r}"
            ) from exc
    for rejected_id in (
        0,
        9_223_372_036_854_775_808,
        True,
        "7",
        7.5,
        9_007_199_254_740_992.0,
        float("inf"),
        float("nan"),
    ):
        response["scheduled_jobs"][0]["id"] = rejected_id
        response["scheduled_jobs"][0]["pk"] = rejected_id
        try:
            validate_response(list_tool, response)
        except bridge_error:
            continue
        raise PairedSDKGateError(
            f"paired SDK accepted invalid response identity: {rejected_id!r}"
        )
    response["scheduled_jobs"][0]["id"] = 1
    response["scheduled_jobs"][0]["pk"] = 1
    schedule_response = {"ok": True, "job_id": 1, "message": "queued"}
    for accepted_id in (1, 9_007_199_254_740_991.0, 9_223_372_036_854_775_807):
        response["count"] = accepted_id
        schedule_response["job_id"] = accepted_id
        try:
            validate_response(list_tool, response)
            validate_response(schedule_tool, schedule_response)
        except bridge_error as exc:
            raise PairedSDKGateError(
                f"paired SDK rejected valid response count/job ID: {accepted_id!r}"
            ) from exc
    response["count"] = 0
    try:
        validate_response(list_tool, response)
    except bridge_error as exc:
        raise PairedSDKGateError("paired SDK rejected a zero response count") from exc
    schedule_response["job_id"] = 0
    try:
        validate_response(schedule_tool, schedule_response)
    except bridge_error:
        pass
    else:
        raise PairedSDKGateError("paired SDK accepted a zero response job ID")
    for rejected_id in (
        -1,
        9_223_372_036_854_775_808,
        True,
        "7",
        7.5,
        9_007_199_254_740_992.0,
        float("inf"),
        float("nan"),
    ):
        response["count"] = rejected_id
        schedule_response["job_id"] = rejected_id
        for tool, body, label in (
            (list_tool, response, "count"),
            (schedule_tool, schedule_response, "job ID"),
        ):
            try:
                validate_response(tool, body)
            except bridge_error:
                continue
            raise PairedSDKGateError(
                f"paired SDK accepted invalid response {label}: {rejected_id!r}"
            )
    response["count"] = 1
    response["scheduled_jobs"][0]["schedule"] = "2026-08-12T12:34:60Z"
    try:
        validate_response(list_tool, response)
    except bridge_error:
        pass
    else:
        raise PairedSDKGateError("paired SDK accepted an invalid response leap instant")


def main(argv: list[str] | None = None) -> None:
    """Fail closed unless one immutable paired SDK passes every vector."""
    arguments = _parse_args(argv)
    environment_root = _require_isolated_environment(arguments)
    expected_commit = arguments.expected_commit
    if _FULL_SHA_RE.fullmatch(expected_commit) is None:
        raise PairedSDKGateError("--expected-commit must be a lowercase full SHA")
    try:
        sdk_root = arguments.sdk_root.resolve(strict=True)
    except OSError as exc:
        raise PairedSDKGateError("SDK root does not exist") from exc
    if not sdk_root.is_dir():
        raise PairedSDKGateError("SDK root is not a directory")
    with tempfile.TemporaryDirectory(
        prefix="proxbox-paired-sdk-", dir="/tmp"
    ) as temporary:
        snapshot_root = Path(temporary) / "snapshot"
        _materialize_sdk_commit(sdk_root, expected_commit, snapshot_root)
        bridge_module = _load_identified_sdk(
            arguments,
            snapshot_root,
            environment_root,
        )
        _validate_behavior(bridge_module)


if __name__ == "__main__":
    try:
        main()
    except PairedSDKGateError as exc:
        raise SystemExit(f"paired SDK gate failed: {exc}") from exc
