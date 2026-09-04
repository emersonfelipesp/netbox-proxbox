#!/usr/bin/env python3
"""Attest the live mirror runner and install the checksum-pinned uv runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import re
import stat
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.gitea_release_runner_gate import API_ORIGIN
except ModuleNotFoundError:
    from gitea_release_runner_gate import API_ORIGIN

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_ENVIRONMENT_BYTES = 1024 * 1024 * 1024
MAX_ENVIRONMENT_FILES = 50_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROXY_ENVIRONMENT_NAMES = frozenset(
    {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
)
EXPECTED_EXECUTABLES = frozenset({"bash", "gh", "git", "python", "sh"})
EXPECTED_ACCEPTANCE_KEYS = {
    "allowed_job_names",
    "executables",
    "registered_labels",
    "repository",
    "runner_id",
    "runner_label",
    "runner_name",
    "schema",
    "uv_archive",
}


class MirrorRunnerGateError(ValueError):
    """The live job or release runtime differs from reviewed acceptance."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _PinnedUvRedirect(urllib.request.HTTPRedirectHandler):
    _ALLOWED_HOSTS = frozenset({"github.com", "release-assets.githubusercontent.com"})

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> urllib.request.Request | None:
        parsed = urllib.parse.urlsplit(new_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise MirrorRunnerGateError("uv download redirected outside its allowlist")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _read_acceptance(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MirrorRunnerGateError("mirror runner acceptance is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_size != len(raw)
        or not isinstance(value, dict)
        or set(value) != EXPECTED_ACCEPTANCE_KEYS
        or raw != _canonical_json(value)
    ):
        raise MirrorRunnerGateError("mirror runner acceptance is malformed")
    _validate_acceptance_values(value)
    return value


def _validate_acceptance_values(value: dict[str, Any]) -> None:
    jobs = value.get("allowed_job_names")
    labels = value.get("registered_labels")
    executables = value.get("executables")
    if (
        isinstance(value.get("schema"), bool)
        or value.get("schema") != 1
        or value.get("repository") != "emersonfelipesp/netbox-proxbox"
        or isinstance(value.get("runner_id"), bool)
        or not isinstance(value.get("runner_id"), int)
        or value["runner_id"] <= 0
        or value.get("runner_label") != "mirror-host"
        or labels != [value.get("runner_label")]
        or not isinstance(value.get("runner_name"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value["runner_name"])
        is None
        or not isinstance(jobs, list)
        or jobs != sorted(set(jobs))
        or len(jobs) != 2
        or any(not isinstance(job, str) or not job for job in jobs)
        or not isinstance(executables, dict)
        or set(executables) != EXPECTED_EXECUTABLES
    ):
        raise MirrorRunnerGateError("mirror runner acceptance is not activated")
    for executable in executables.values():
        _validate_executable_acceptance(executable)
    _validate_uv_acceptance(value.get("uv_archive"))


def _validate_executable_acceptance(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "size"}:
        raise MirrorRunnerGateError("accepted executable record is malformed")
    path = value.get("path")
    size = value.get("size")
    if (
        not isinstance(path, str)
        or not Path(path).is_absolute()
        or ".." in Path(path).parts
        or not _is_sha256(value.get("sha256"))
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= MAX_EXECUTABLE_BYTES
    ):
        raise MirrorRunnerGateError("accepted executable record is invalid")


def _validate_uv_acceptance(value: object) -> None:
    expected_keys = {
        "archive_sha256",
        "archive_size",
        "binary_sha256",
        "binary_size",
        "member",
        "url",
        "version",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise MirrorRunnerGateError("accepted uv archive record is malformed")
    parsed = urllib.parse.urlsplit(str(value.get("url")))
    sizes = (value.get("archive_size"), value.get("binary_size"))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not _is_sha256(value.get("archive_sha256"))
        or not _is_sha256(value.get("binary_sha256"))
        or any(isinstance(size, bool) or not isinstance(size, int) for size in sizes)
        or not 0 < sizes[0] <= MAX_EXECUTABLE_BYTES
        or not 0 < sizes[1] <= MAX_EXECUTABLE_BYTES
        or value.get("member") != "uv-x86_64-unknown-linux-gnu/uv"
        or value.get("version") != "0.12.5"
    ):
        raise MirrorRunnerGateError("accepted uv archive record is invalid")


def _hash_open_executable(
    path: Path,
    expected_size: int,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> str:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while total <= MAX_EXECUTABLE_BYTES:
            chunk = os.read(
                descriptor, min(1024 * 1024, MAX_EXECUTABLE_BYTES + 1 - total)
            )
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise MirrorRunnerGateError(
            f"accepted executable {path} is unavailable"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    stable = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or stat.S_IMODE(before.st_mode) != 0o755
        or before.st_nlink != 1
        or before.st_size != expected_size
        or total != expected_size
        or not stable
    ):
        raise MirrorRunnerGateError(f"accepted executable {path} metadata changed")
    return digest.hexdigest()


def _verify_executables(acceptance: dict[str, Any]) -> dict[str, str]:
    verified: dict[str, str] = {}
    for name, record in acceptance["executables"].items():
        path = Path(record["path"])
        digest = _hash_open_executable(path, record["size"])
        if digest != record["sha256"]:
            raise MirrorRunnerGateError(f"accepted executable {path} digest changed")
        verified[name] = str(path)
    interpreter = Path(os.path.realpath(sys.executable))
    if interpreter != Path(verified["python"]):
        raise MirrorRunnerGateError("runner gate did not use the accepted interpreter")
    return verified


def _request_jobs(owner: str, repository: str, run_id: int, token: str) -> Any:
    if not token or any(ord(character) <= 0x20 for character in token):
        raise MirrorRunnerGateError("Gitea Actions token is unavailable")
    if any(
        name.casefold() in PROXY_ENVIRONMENT_NAMES and value
        for name, value in os.environ.items()
    ):
        raise MirrorRunnerGateError("ambient proxy configuration is forbidden")
    request = urllib.request.Request(
        f"{API_ORIGIN}/repos/{owner}/{repository}/actions/runs/{run_id}/jobs",
        headers={
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "User-Agent": "mirror-runner-gate/1",
        },
    )
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect
        ).open(request, timeout=30) as response:
            if response.status != 200:
                raise MirrorRunnerGateError(f"Gitea returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MirrorRunnerGateError("Gitea runner evidence request failed") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise MirrorRunnerGateError("Gitea runner evidence exceeds its size bound")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MirrorRunnerGateError("Gitea runner evidence is not valid JSON") from exc


def _select_current_job(payload: object, job_name: str) -> dict[str, Any]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    if (
        not isinstance(jobs, list)
        or isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count != len(jobs)
        or not 0 < total_count <= 100
    ):
        raise MirrorRunnerGateError("mirror runner job inventory is incomplete")
    matches = [
        job for job in jobs if isinstance(job, dict) and job.get("name") == job_name
    ]
    if len(matches) != 1:
        raise MirrorRunnerGateError("current mirror runner job identity is ambiguous")
    return matches[0]


def validate_mirror_runner(
    *,
    acceptance_path: Path,
    owner: str,
    repository: str,
    run_id: int,
    run_attempt: int,
    job_name: str,
    source_sha: str,
    token: str,
    jobs_payload: object | None = None,
) -> dict[str, Any]:
    acceptance = _read_acceptance(acceptance_path)
    if (
        f"{owner}/{repository}" != acceptance["repository"]
        or job_name not in acceptance["allowed_job_names"]
        or isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or run_id <= 0
        or run_attempt != 1
        or isinstance(run_attempt, bool)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
    ):
        raise MirrorRunnerGateError("mirror runner invocation is invalid")
    verified = _verify_executables(acceptance)
    payload = (
        _request_jobs(owner, repository, run_id, token)
        if jobs_payload is None
        else jobs_payload
    )
    job = _select_current_job(payload, job_name)
    if (
        job.get("run_id") != run_id
        or job.get("run_attempt") != run_attempt
        or job.get("head_sha") != source_sha
        or job.get("status") != "in_progress"
        or job.get("conclusion") not in {None, ""}
        or job.get("runner_id") != acceptance["runner_id"]
        or job.get("runner_name") != acceptance["runner_name"]
        or job.get("labels") != acceptance["registered_labels"]
    ):
        raise MirrorRunnerGateError("job did not use the exact accepted mirror runner")
    return {
        "acceptance_sha256": hashlib.sha256(_canonical_json(acceptance)).hexdigest(),
        "executables": verified,
        "job_id": job.get("id"),
        "runner_id": job.get("runner_id"),
    }


def _download_uv_archive(record: dict[str, Any]) -> bytes:
    if any(
        name.casefold() in PROXY_ENVIRONMENT_NAMES and value
        for name, value in os.environ.items()
    ):
        raise MirrorRunnerGateError("ambient proxy configuration is forbidden")
    request = urllib.request.Request(
        record["url"], headers={"User-Agent": "mirror-runner-gate/1"}
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _PinnedUvRedirect
    )
    try:
        with opener.open(request, timeout=60) as response:
            raw = response.read(record["archive_size"] + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MirrorRunnerGateError("pinned uv archive download failed") from exc
    return raw


def _uv_binary(record: dict[str, Any], archive: bytes) -> bytes:
    if (
        len(archive) != record["archive_size"]
        or hashlib.sha256(archive).hexdigest() != record["archive_sha256"]
    ):
        raise MirrorRunnerGateError("pinned uv archive bytes differ from acceptance")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            member = bundle.getmember(record["member"])
            stream = bundle.extractfile(member)
            binary = stream.read(record["binary_size"] + 1) if stream else b""
    except (KeyError, OSError, tarfile.TarError) as exc:
        raise MirrorRunnerGateError("pinned uv archive is malformed") from exc
    if (
        not member.isfile()
        or member.issym()
        or member.islnk()
        or member.size != record["binary_size"]
        or len(binary) != record["binary_size"]
        or hashlib.sha256(binary).hexdigest() != record["binary_sha256"]
    ):
        raise MirrorRunnerGateError("pinned uv executable differs from acceptance")
    return binary


def install_uv(
    *, acceptance_path: Path, output: Path, archive_bytes: bytes | None = None
) -> dict[str, object]:
    acceptance = _read_acceptance(acceptance_path)
    _verify_executables(acceptance)
    record = acceptance["uv_archive"]
    archive = _download_uv_archive(record) if archive_bytes is None else archive_bytes
    binary = _uv_binary(record, archive)
    if not output.is_absolute() or output.parent.is_symlink() or output.exists():
        raise MirrorRunnerGateError("uv output path is unsafe")
    descriptor = -1
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o500,
        )
        view = memoryview(binary)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short uv executable write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise MirrorRunnerGateError("uv executable installation failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {
        "path": str(output),
        "sha256": hashlib.sha256(binary).hexdigest(),
        "version": record["version"],
    }


def _open_validated_uv(*, acceptance_path: Path, executable: Path) -> int:
    """Open and revalidate the pinned uv inode immediately before execution."""
    acceptance = _read_acceptance(acceptance_path)
    _verify_executables(acceptance)
    record = acceptance["uv_archive"]
    runner_uid = os.geteuid()
    runner_gid = os.getegid()
    try:
        parent = executable.parent.lstat()
        path_metadata = executable.lstat()
        descriptor = os.open(executable, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        descriptor_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise MirrorRunnerGateError("pinned uv runtime is unavailable") from exc
    try:
        if (
            not executable.is_absolute()
            or executable.parent.is_symlink()
            or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != runner_uid
            or parent.st_gid != runner_gid
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISREG(path_metadata.st_mode)
            or path_metadata.st_uid != runner_uid
            or path_metadata.st_gid != runner_gid
            or path_metadata.st_nlink != 1
            or stat.S_IMODE(path_metadata.st_mode) != 0o500
            or path_metadata.st_dev != descriptor_metadata.st_dev
            or path_metadata.st_ino != descriptor_metadata.st_ino
            or descriptor_metadata.st_size != record["binary_size"]
        ):
            raise MirrorRunnerGateError("pinned uv runtime metadata changed")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        if digest.hexdigest() != record["binary_sha256"]:
            raise MirrorRunnerGateError("pinned uv runtime digest changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def run_uv(*, acceptance_path: Path, executable: Path, arguments: list[str]) -> None:
    """Execute the revalidated uv inode through its already-open descriptor."""
    if not arguments:
        raise MirrorRunnerGateError("pinned uv invocation is empty")
    descriptor = _open_validated_uv(
        acceptance_path=acceptance_path, executable=executable
    )
    os.set_inheritable(descriptor, True)
    os.execve(
        f"/proc/self/fd/{descriptor}",
        [str(executable), *arguments],
        os.environ.copy(),
    )


def _validate_environment_root(root: Path) -> None:
    if not root.is_absolute() or ".." in root.parts:
        raise MirrorRunnerGateError("locked Python environment path is invalid")
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise MirrorRunnerGateError("locked Python environment is unavailable") from exc
    if (
        root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or root_metadata.st_gid != os.getegid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise MirrorRunnerGateError("locked Python environment root is unsafe")


def _environment_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _hash_environment_file(path: Path, expected: os.stat_result) -> tuple[str, int]:
    if expected.st_nlink != 1:
        raise MirrorRunnerGateError(
            "locked Python environment contains a hard-linked file"
        )
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise MirrorRunnerGateError(
            "locked Python environment file cannot be hashed"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        _environment_file_identity(before) != _environment_file_identity(after)
        or size != expected.st_size
    ):
        raise MirrorRunnerGateError(
            "locked Python environment changed while being hashed"
        )
    return digest.hexdigest(), size


def _environment_entry_record(
    root: Path, entry: os.DirEntry[str]
) -> tuple[dict[str, object], Path | None, int]:
    path = Path(entry.path)
    relative = path.relative_to(root).as_posix()
    try:
        metadata = entry.stat(follow_symlinks=False)
    except OSError as exc:
        raise MirrorRunnerGateError(
            "locked Python environment entry is unavailable"
        ) from exc
    if (
        not relative
        or relative.startswith("../")
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
    ):
        raise MirrorRunnerGateError(
            "locked Python environment entry metadata is unsafe"
        )
    if stat.S_ISLNK(metadata.st_mode):
        raise MirrorRunnerGateError(
            "locked Python environment contains a symbolic link"
        )
    if metadata.st_mode & 0o022:
        raise MirrorRunnerGateError(
            "locked Python environment entry metadata is unsafe"
        )
    if stat.S_ISDIR(metadata.st_mode):
        return (
            {
                "mode": stat.S_IMODE(metadata.st_mode),
                "path": relative,
                "type": "directory",
            },
            path,
            0,
        )
    if stat.S_ISREG(metadata.st_mode):
        digest, size = _hash_environment_file(path, metadata)
        return (
            {
                "mode": stat.S_IMODE(metadata.st_mode),
                "path": relative,
                "sha256": digest,
                "size": size,
                "type": "file",
            },
            None,
            size,
        )
    raise MirrorRunnerGateError("locked Python environment contains a special file")


def _environment_inventory(root: Path) -> list[dict[str, object]]:
    """Hash a bounded runner-owned Python environment without following links."""
    _validate_environment_root(root)
    records: list[dict[str, object]] = []
    total_size = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise MirrorRunnerGateError(
                "locked Python environment cannot be inventoried"
            ) from exc
        for entry in entries:
            record, child, size = _environment_entry_record(root, entry)
            records.append(record)
            if child is not None:
                pending.append(child)
            total_size += size
            if total_size > MAX_ENVIRONMENT_BYTES:
                raise MirrorRunnerGateError(
                    "locked Python environment exceeds its size bound"
                )
            if len(records) > MAX_ENVIRONMENT_FILES:
                raise MirrorRunnerGateError(
                    "locked Python environment exceeds its file bound"
                )
    return sorted(records, key=lambda record: str(record["path"]))


def _site_packages(root: Path) -> Path:
    candidates = sorted((root / "lib").glob("python3.*/site-packages"))
    if len(candidates) != 1 or not candidates[0].is_dir():
        raise MirrorRunnerGateError(
            "locked Python environment has no unique site-packages directory"
        )
    return candidates[0]


def _required_distributions(
    site_packages: Path, requirements: list[str]
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for requirement in requirements:
        name, separator, version = requirement.partition("=")
        normalized = re.sub(r"[-_.]+", "-", name).casefold()
        if (
            separator != "="
            or not normalized
            or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", normalized) is None
            or not version
            or len(version) > 128
            or normalized in expected
        ):
            raise MirrorRunnerGateError("locked Python requirement is malformed")
        expected[normalized] = version
    installed = {
        re.sub(
            r"[-_.]+", "-", distribution.metadata["Name"]
        ).casefold(): distribution.version
        for distribution in importlib.metadata.distributions(path=[str(site_packages)])
        if distribution.metadata.get("Name")
    }
    if any(installed.get(name) != version for name, version in expected.items()):
        raise MirrorRunnerGateError(
            "locked Python environment distribution versions differ"
        )
    return expected


def seal_python_environment(
    *, root: Path, manifest: Path, requirements: list[str]
) -> dict[str, object]:
    """Seal the complete installed environment before any credential use."""
    if (
        not manifest.is_absolute()
        or manifest.exists()
        or manifest.parent != root.parent
    ):
        raise MirrorRunnerGateError("locked Python manifest path is unsafe")
    site_packages = _site_packages(root)
    value = {
        "files": _environment_inventory(root),
        "requirements": _required_distributions(site_packages, requirements),
        "root": str(root),
        "schema": 1,
        "site_packages": site_packages.relative_to(root).as_posix(),
    }
    raw = _canonical_json(value)
    descriptor = -1
    try:
        descriptor = os.open(
            manifest,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o400,
        )
        remaining = memoryview(raw)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short locked Python manifest write")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise MirrorRunnerGateError("locked Python manifest cannot be written") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {
        "files": len(value["files"]),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "requirements": value["requirements"],
    }


def _read_python_environment_manifest(manifest: Path) -> dict[str, Any]:
    try:
        metadata = manifest.lstat()
        raw = manifest.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MirrorRunnerGateError("locked Python manifest is unavailable") from exc
    if (
        manifest.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or metadata.st_size != len(raw)
        or not isinstance(value, dict)
        or set(value) != {"files", "requirements", "root", "schema", "site_packages"}
        or value.get("schema") != 1
        or raw != _canonical_json(value)
    ):
        raise MirrorRunnerGateError("locked Python manifest is malformed")
    root = Path(value["root"])
    if value.get("files") != _environment_inventory(root):
        raise MirrorRunnerGateError("locked Python environment bytes changed")
    site_packages = value.get("site_packages")
    if (
        not isinstance(site_packages, str)
        or not site_packages
        or Path(site_packages).is_absolute()
        or ".." in Path(site_packages).parts
        or root / site_packages != _site_packages(root)
    ):
        raise MirrorRunnerGateError("locked Python manifest site path is malformed")
    return value


def _open_accepted_python(acceptance: dict[str, Any]) -> int:
    record = acceptance["executables"]["python"]
    path = Path(record["path"])
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    metadata = os.fstat(descriptor)
    digest = hashlib.sha256()
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o755
        or metadata.st_nlink != 1
        or metadata.st_size != record["size"]
        or digest.hexdigest() != record["sha256"]
    ):
        os.close(descriptor)
        raise MirrorRunnerGateError("accepted Python runtime changed")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor


def run_locked_python(
    *, acceptance_path: Path, manifest: Path, module: str, arguments: list[str]
) -> None:
    """Run an allowlisted module through an attested interpreter and environment."""
    if module not in {"build", "twine"}:
        raise MirrorRunnerGateError("locked Python module is not allowlisted")
    environment = _read_python_environment_manifest(manifest)
    acceptance = _read_acceptance(acceptance_path)
    _verify_executables(acceptance)
    descriptor = _open_accepted_python(acceptance)
    os.set_inheritable(descriptor, True)
    site_packages = str(Path(environment["root"]) / environment["site_packages"])
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0,{site_packages!r});"
        "module=sys.argv[1];"
        "sys.argv=[module,*sys.argv[2:]];"
        "runpy.run_module(module,run_name='__main__',alter_sys=True)"
    )
    clean_environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("PYTHON") and name != "VIRTUAL_ENV"
    }
    clean_environment["PYTHONNOUSERSITE"] = "1"
    clean_environment["PYTHONPATH"] = site_packages
    os.execve(
        f"/proc/self/fd/{descriptor}",
        [
            str(acceptance["executables"]["python"]["path"]),
            "-I",
            "-S",
            "-c",
            bootstrap,
            module,
            *arguments,
        ],
        clean_environment,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--acceptance", type=Path, required=True)
    validate.add_argument("--owner", required=True)
    validate.add_argument("--repository", required=True)
    validate.add_argument("--run-id", type=int, required=True)
    validate.add_argument("--run-attempt", type=int, required=True)
    validate.add_argument("--job-name", required=True)
    validate.add_argument("--source-sha", required=True)
    install = subparsers.add_parser("install-uv")
    install.add_argument("--acceptance", type=Path, required=True)
    install.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("run-uv")
    run.add_argument("--acceptance", type=Path, required=True)
    run.add_argument("--uv", type=Path, required=True)
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    seal_environment = subparsers.add_parser("seal-python-environment")
    seal_environment.add_argument("--root", type=Path, required=True)
    seal_environment.add_argument("--manifest", type=Path, required=True)
    seal_environment.add_argument("--require", action="append", default=[])
    run_python = subparsers.add_parser("run-locked-python")
    run_python.add_argument("--acceptance", type=Path, required=True)
    run_python.add_argument("--manifest", type=Path, required=True)
    run_python.add_argument("--module", choices=("build", "twine"), required=True)
    run_python.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "validate":
        evidence = validate_mirror_runner(
            acceptance_path=args.acceptance,
            owner=args.owner,
            repository=args.repository,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            job_name=args.job_name,
            source_sha=args.source_sha,
            token=os.getenv("GITEA_API_TOKEN", ""),
        )
    elif args.command == "install-uv":
        evidence = install_uv(
            acceptance_path=args.acceptance,
            output=args.output,
        )
    elif args.command == "run-uv":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        run_uv(
            acceptance_path=args.acceptance,
            executable=args.uv,
            arguments=arguments,
        )
        raise AssertionError("uv execution returned unexpectedly")
    elif args.command == "seal-python-environment":
        evidence = seal_python_environment(
            root=args.root,
            manifest=args.manifest,
            requirements=args.require,
        )
    else:
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        run_locked_python(
            acceptance_path=args.acceptance,
            manifest=args.manifest,
            module=args.module,
            arguments=arguments,
        )
        raise AssertionError("locked Python execution returned unexpectedly")
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
