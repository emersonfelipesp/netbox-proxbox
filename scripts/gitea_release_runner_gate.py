#!/usr/bin/env python3
"""Fail before candidate execution unless this is the exact accepted runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any


API_ORIGIN = "https://git.nmulti.cloud/api/v1"
MAX_RESPONSE_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ZERO_SHA256 = "0" * 64


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
        "network_attestation_sha256",
        "runner_id",
        "runner_label",
        "runner_name",
        "runtime_attestation_sha256",
        "schema",
    }
    runtime_digest = (
        value.get("runtime_attestation_sha256") if isinstance(value, dict) else None
    )
    network_digest = (
        value.get("network_attestation_sha256") if isinstance(value, dict) else None
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
        or not isinstance(runtime_digest, str)
        or SHA256_RE.fullmatch(runtime_digest) is None
        or runtime_digest == ZERO_SHA256
        or not isinstance(network_digest, str)
        or SHA256_RE.fullmatch(network_digest) is None
        or network_digest == ZERO_SHA256
    ):
        raise RunnerGateError("release runner acceptance is not activated")
    return value


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
    return {
        "acceptance_sha256": hashlib.sha256(_canonical_json(acceptance)).hexdigest(),
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
    args = parser.parse_args()
    evidence = validate_release_runner(
        acceptance_path=args.acceptance,
        owner=args.owner,
        repository=args.repository,
        run_id=args.run_id,
        job_name=args.job_name,
        source_sha=args.source_sha,
        token=os.getenv("GITEA_API_TOKEN", ""),
    )
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
