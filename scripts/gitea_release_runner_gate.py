#!/usr/bin/env python3
"""Fail before candidate execution unless this is the exact accepted runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ORIGIN = "https://git.nmulti.cloud/api/v1"
MAX_RESPONSE_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ZERO_SHA256 = "0" * 64
OPENSSL = Path("/usr/bin/openssl")
DEFAULT_ATTESTATION_ROOT = Path("/run/nmc-release-attestation")
DEFAULT_PUBLIC_KEY = Path("/etc/nmc-release-runner-attestation-public.pem")
TRUSTED_EXTERNAL_UID = 0


class RunnerGateError(ValueError):
    """The scheduled job does not match accepted release-runner evidence."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _load_acceptance(path: Path, repository: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerGateError("release runner acceptance is unavailable") from exc
    expected_keys = {
        "attestation_public_key_sha256",
        "network_attestation_sha256",
        "registered_labels",
        "runner_id",
        "runner_label",
        "runner_name",
        "runtime_attestation_sha256",
        "runtime_image_digest",
        "schema",
        "supervisor_policy_sha256",
    }
    runtime_digest = (
        value.get("runtime_attestation_sha256") if isinstance(value, dict) else None
    )
    network_digest = (
        value.get("network_attestation_sha256") if isinstance(value, dict) else None
    )
    registered_labels = (
        value.get("registered_labels") if isinstance(value, dict) else None
    )
    pinned_digests = (
        value.get("attestation_public_key_sha256") if isinstance(value, dict) else None,
        network_digest,
        runtime_digest,
        value.get("runtime_image_digest") if isinstance(value, dict) else None,
        value.get("supervisor_policy_sha256") if isinstance(value, dict) else None,
    )
    if (
        not path.is_file()
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_size != len(raw)
        or not isinstance(value, dict)
        or set(value) != expected_keys
        or raw != _canonical_json(value)
        or isinstance(value.get("schema"), bool)
        or value.get("schema") != 1
        or isinstance(value.get("runner_id"), bool)
        or not isinstance(value.get("runner_id"), int)
        or value["runner_id"] <= 0
        or not isinstance(value.get("runner_name"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value["runner_name"])
        is None
        or value.get("runner_label") != f"ci-release-{repository}"
        or not isinstance(registered_labels, list)
        or registered_labels != sorted(set(registered_labels))
        or value.get("runner_label") not in registered_labels
        or any(
            not isinstance(label, str)
            or re.fullmatch(r"ci-(?:release|untrusted)-[a-z0-9-]+", label) is None
            for label in registered_labels
        )
        or any(
            not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or digest == ZERO_SHA256
            for digest in pinned_digests
        )
    ):
        raise RunnerGateError("release runner acceptance is not activated")
    return value


def _open_external_file(
    path: Path,
    label: str,
    maximum: int,
    *,
    trusted_uid: int = TRUSTED_EXTERNAL_UID,
) -> tuple[bytes, int]:
    descriptor = -1
    try:
        parent_metadata = path.parent.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        metadata = os.fstat(descriptor)
        chunks = bytearray()
        while len(chunks) <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise RunnerGateError(f"{label} is unavailable") from exc
    raw = bytes(chunks)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != trusted_uid
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != trusted_uid
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size != len(raw)
        or not 0 < len(raw) <= maximum
        or (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        os.close(descriptor)
        raise RunnerGateError(f"{label} metadata is unsafe")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return raw, descriptor


def _verify_live_attestation(
    *,
    acceptance: dict[str, Any],
    attestation_root: Path,
    public_key_path: Path,
    repository_full_name: str,
    run_id: int,
    job_id: int,
    source_sha: str,
    now: int,
    trusted_external_uid: int,
) -> str:
    if not attestation_root.is_absolute() or not public_key_path.is_absolute():
        raise RunnerGateError("runner attestation paths are not absolute")
    stem = f"run-{run_id}-job-{job_id}"
    attestation_path = attestation_root / f"{stem}.json"
    signature_path = attestation_root / f"{stem}.sig"
    public_key, public_key_fd = _open_external_file(
        public_key_path,
        "attestation public key",
        16384,
        trusted_uid=trusted_external_uid,
    )
    if (
        hashlib.sha256(public_key).hexdigest()
        != acceptance["attestation_public_key_sha256"]
    ):
        os.close(public_key_fd)
        raise RunnerGateError("attestation public key differs from acceptance")
    attestation_fd = -1
    signature_fd = -1
    try:
        raw, attestation_fd = _open_external_file(
            attestation_path,
            "live runner attestation",
            16384,
            trusted_uid=trusted_external_uid,
        )
        _, signature_fd = _open_external_file(
            signature_path,
            "live runner attestation signature",
            16384,
            trusted_uid=trusted_external_uid,
        )
    except RunnerGateError:
        os.close(public_key_fd)
        if attestation_fd >= 0:
            os.close(attestation_fd)
        if signature_fd >= 0:
            os.close(signature_fd)
        raise
    try:
        if not OPENSSL.is_file() or OPENSSL.is_symlink():
            raise RunnerGateError("OpenSSL verifier is unavailable")
        try:
            verified = subprocess.run(  # noqa: S603
                [
                    str(OPENSSL),
                    "dgst",
                    "-sha256",
                    "-verify",
                    f"/proc/self/fd/{public_key_fd}",
                    "-signature",
                    f"/proc/self/fd/{signature_fd}",
                    f"/proc/self/fd/{attestation_fd}",
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(public_key_fd, signature_fd, attestation_fd),
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RunnerGateError(
                "live runner attestation verification failed"
            ) from exc
    finally:
        os.close(public_key_fd)
        if signature_fd >= 0:
            os.close(signature_fd)
        if attestation_fd >= 0:
            os.close(attestation_fd)
    if verified.returncode != 0:
        raise RunnerGateError("live runner attestation signature is invalid")
    try:
        attestation = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerGateError("live runner attestation is invalid JSON") from exc
    expected_keys = {
        "expires_at",
        "issued_at",
        "job_id",
        "network_attestation_sha256",
        "registered_labels",
        "repository",
        "run_id",
        "runner_id",
        "runner_name",
        "runtime_attestation_sha256",
        "runtime_image_digest",
        "schema",
        "source_sha",
        "supervisor_policy_sha256",
    }
    issued_at = attestation.get("issued_at") if isinstance(attestation, dict) else None
    expires_at = (
        attestation.get("expires_at") if isinstance(attestation, dict) else None
    )
    if (
        not isinstance(attestation, dict)
        or set(attestation) != expected_keys
        or raw != _canonical_json(attestation)
        or isinstance(attestation.get("schema"), bool)
        or attestation.get("schema") != 1
        or isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
        or not issued_at <= now < expires_at
        or not 0 < expires_at - issued_at <= 300
        or attestation.get("repository") != repository_full_name
        or attestation.get("run_id") != run_id
        or isinstance(attestation.get("run_id"), bool)
        or attestation.get("job_id") != job_id
        or isinstance(attestation.get("job_id"), bool)
        or attestation.get("source_sha") != source_sha
        or attestation.get("runner_id") != acceptance["runner_id"]
        or isinstance(attestation.get("runner_id"), bool)
        or attestation.get("runner_name") != acceptance["runner_name"]
        or attestation.get("registered_labels") != acceptance["registered_labels"]
        or attestation.get("runtime_image_digest") != acceptance["runtime_image_digest"]
        or attestation.get("runtime_attestation_sha256")
        != acceptance["runtime_attestation_sha256"]
        or attestation.get("network_attestation_sha256")
        != acceptance["network_attestation_sha256"]
        or attestation.get("supervisor_policy_sha256")
        != acceptance["supervisor_policy_sha256"]
    ):
        raise RunnerGateError(
            "live runner attestation differs from this job and acceptance"
        )
    return hashlib.sha256(raw).hexdigest()


def _request_jobs(owner: str, repository: str, run_id: int, token: str) -> Any:
    if not token or any(
        ord(character) <= 0x20 or ord(character) == 0x7F for character in token
    ):
        raise RunnerGateError("Gitea Actions token is unavailable")
    path = f"/repos/{owner}/{repository}/actions/runs/{run_id}/jobs"
    request = urllib.request.Request(
        f"{API_ORIGIN}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "User-Agent": "release-runner-gate/1",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(
            request, timeout=30
        ) as response:
            if response.status != 200:
                raise RunnerGateError(f"Gitea returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RunnerGateError("Gitea runner evidence request failed") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RunnerGateError("Gitea runner evidence exceeds its size bound")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunnerGateError("Gitea runner evidence is not valid JSON") from exc


def validate_release_runner(
    *,
    acceptance_path: Path,
    owner: str,
    repository: str,
    run_id: int,
    job_name: str,
    source_sha: str,
    token: str,
    jobs_payload: object | None = None,
    attestation_root: Path = DEFAULT_ATTESTATION_ROOT,
    public_key_path: Path = DEFAULT_PUBLIC_KEY,
    now: int | None = None,
    trusted_external_uid: int = TRUSTED_EXTERNAL_UID,
) -> dict[str, Any]:
    acceptance = _load_acceptance(acceptance_path, repository)
    if (
        not owner
        or not repository
        or isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or run_id <= 0
        or not job_name
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or isinstance(trusted_external_uid, bool)
        or not isinstance(trusted_external_uid, int)
        or trusted_external_uid < 0
    ):
        raise RunnerGateError("release job identity is invalid")
    payload = (
        _request_jobs(owner, repository, run_id, token)
        if jobs_payload is None
        else jobs_payload
    )
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    if (
        not isinstance(jobs, list)
        or isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count != len(jobs)
        or not 0 < total_count <= 100
    ):
        raise RunnerGateError("release job inventory is incomplete")
    matches = [
        job for job in jobs if isinstance(job, dict) and job.get("name") == job_name
    ]
    if len(matches) != 1:
        raise RunnerGateError("current release job identity is ambiguous")
    job = matches[0]
    if (
        isinstance(job.get("id"), bool)
        or not isinstance(job.get("id"), int)
        or job["id"] <= 0
        or job.get("run_id") != run_id
        or isinstance(job.get("run_id"), bool)
        or job.get("run_attempt") != 1
        or isinstance(job.get("run_attempt"), bool)
        or job.get("head_sha") != source_sha
        or job.get("status") != "in_progress"
        or job.get("conclusion") not in {None, ""}
        or job.get("runner_id") != acceptance["runner_id"]
        or isinstance(job.get("runner_id"), bool)
        or job.get("runner_name") != acceptance["runner_name"]
        or job.get("labels") != [acceptance["runner_label"]]
    ):
        raise RunnerGateError("job did not use the exact accepted release runner")
    attestation_sha256 = _verify_live_attestation(
        acceptance=acceptance,
        attestation_root=attestation_root,
        public_key_path=public_key_path,
        repository_full_name=f"{owner}/{repository}",
        run_id=run_id,
        job_id=int(job["id"]),
        source_sha=source_sha,
        now=int(time.time()) if now is None else now,
        trusted_external_uid=trusted_external_uid,
    )
    return {
        "acceptance_sha256": hashlib.sha256(_canonical_json(acceptance)).hexdigest(),
        "attestation_sha256": attestation_sha256,
        "job_id": job["id"],
        "runner_id": job["runner_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--attestation-root", type=Path, default=DEFAULT_ATTESTATION_ROOT
    )
    parser.add_argument(
        "--attestation-public-key", type=Path, default=DEFAULT_PUBLIC_KEY
    )
    args = parser.parse_args()
    evidence = validate_release_runner(
        acceptance_path=args.acceptance,
        owner=args.owner,
        repository=args.repository,
        run_id=args.run_id,
        job_name=args.job_name,
        source_sha=args.source_sha,
        token=os.getenv("GITEA_API_TOKEN", ""),
        attestation_root=args.attestation_root,
        public_key_path=args.attestation_public_key,
    )
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
