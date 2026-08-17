#!/usr/bin/env python3
"""Bind release authorization to authenticated Gitea CI run and job records."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_ORIGIN = "https://git.nmulti.cloud/api/v1"
HTML_ORIGIN = "https://git.nmulti.cloud"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
FIRST_JOB_ATTEMPT = 1
FIRST_RUN_ATTEMPT_ENCODINGS = frozenset({0, 1})


class CIGateError(ValueError):
    """Authenticated Gitea evidence violates the release CI contract."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _request_json(path: str, *, token: str) -> Any:
    if not token:
        raise CIGateError("Gitea API token is unavailable")
    if not path.startswith("/repos/") or ".." in path:
        raise CIGateError("Gitea API path is invalid")
    request = urllib.request.Request(
        f"{API_ORIGIN}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "User-Agent": "release-ci-gate/1",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(
            request, timeout=30
        ) as response:
            if response.status != 200:
                raise CIGateError(f"Gitea returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CIGateError("Gitea CI evidence request failed") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CIGateError("Gitea CI evidence exceeds its size bound")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CIGateError("Gitea CI evidence is not valid JSON") from exc


def _expected_job_name(context: str) -> str:
    prefix, suffix = "CI / ", " (push)"
    if not context.startswith(prefix) or not context.endswith(suffix):
        raise CIGateError(f"Unsupported release CI context: {context!r}")
    name = context[len(prefix) : -len(suffix)]
    if not name:
        raise CIGateError("Release CI job name is empty")
    return name


def _latest_workflow_run(
    payload: object, *, source_sha: str, trusted_actor: str
) -> dict[str, Any]:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    if (
        not isinstance(runs, list)
        or not runs
        or isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count != len(runs)
        or total_count > 100
    ):
        raise CIGateError("Gitea Actions run inventory is incomplete")
    candidates: list[dict[str, Any]] = []
    observed_ids: set[int] = set()
    for run in runs:
        run_id = run.get("id") if isinstance(run, dict) else None
        if (
            not isinstance(run, dict)
            or isinstance(run_id, bool)
            or not isinstance(run_id, int)
            or run_id <= 0
            or run_id in observed_ids
        ):
            raise CIGateError("Gitea Actions run inventory is malformed")
        observed_ids.add(run_id)
        if (
            run.get("path") == "ci.yml@refs/heads/develop"
            and run.get("head_sha") == source_sha
            and run.get("head_branch") == "develop"
            and run.get("event") == "push"
        ):
            candidates.append(run)
    if not candidates:
        raise CIGateError("Required Gitea Actions workflow run is missing")
    latest = max(candidates, key=lambda row: int(row["id"]))
    _validate_run(
        latest,
        context="latest required workflow run",
        run_id=int(latest["id"]),
        source_sha=source_sha,
        trusted_actor=trusted_actor,
    )
    return latest


def _required_jobs(
    payload: object, *, required_contexts: list[str]
) -> dict[str, dict[str, Any]]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    if (
        not isinstance(jobs, list)
        or not jobs
        or isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count != len(jobs)
        or total_count > 100
    ):
        raise CIGateError("Gitea Actions job inventory is incomplete")
    expected = {_expected_job_name(context): context for context in required_contexts}
    selected: dict[str, dict[str, Any]] = {}
    observed_ids: set[int] = set()
    for job in jobs:
        job_id = job.get("id") if isinstance(job, dict) else None
        if (
            not isinstance(job, dict)
            or isinstance(job_id, bool)
            or not isinstance(job_id, int)
            or job_id <= 0
            or job_id in observed_ids
        ):
            raise CIGateError("Gitea Actions job inventory is malformed")
        observed_ids.add(job_id)
        name = job.get("name")
        if name in expected:
            if name in selected:
                raise CIGateError("Required Gitea Actions job is ambiguous")
            selected[str(name)] = job
    if set(selected) != set(expected):
        raise CIGateError("Required Gitea Actions job is missing")
    return {expected[name]: job for name, job in selected.items()}


def _validate_run(
    run: object,
    *,
    context: str,
    run_id: int,
    source_sha: str,
    trusted_actor: str,
) -> None:
    actor = run.get("actor") if isinstance(run, dict) else None
    expected = {
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_sha": source_sha,
        "head_branch": "develop",
        "path": "ci.yml@refs/heads/develop",
    }
    if not isinstance(run, dict) or any(
        run.get(key) != value for key, value in expected.items()
    ):
        raise CIGateError(f"Gitea CI run does not match the release source: {context}")
    observed_run_id = run.get("id")
    if (
        isinstance(observed_run_id, bool)
        or not isinstance(observed_run_id, int)
        or observed_run_id != run_id
    ):
        raise CIGateError(f"Gitea CI run does not match the release source: {context}")
    if not isinstance(actor, dict) or actor.get("login") != trusted_actor:
        raise CIGateError(f"Gitea CI run actor is not trusted: {context}")
    run_attempt = run.get("run_attempt")
    if (
        isinstance(run_attempt, bool)
        or not isinstance(run_attempt, int)
        or run_attempt not in FIRST_RUN_ATTEMPT_ENCODINGS
    ):
        raise CIGateError(f"Gitea CI run attempt is invalid: {context}")


def _validate_job(
    job: object,
    *,
    context: str,
    owner: str,
    repository: str,
    run_id: int,
    job_id: int,
    source_sha: str,
) -> None:
    expected = {
        "name": _expected_job_name(context),
        "status": "completed",
        "conclusion": "success",
        "head_sha": source_sha,
    }
    if not isinstance(job, dict) or any(
        job.get(key) != value for key, value in expected.items()
    ):
        raise CIGateError(f"Gitea CI job does not match its status: {context}")
    strict_integer_fields = {
        "id": job_id,
        "run_id": run_id,
        "run_attempt": FIRST_JOB_ATTEMPT,
    }
    if any(
        isinstance(job.get(key), bool)
        or not isinstance(job.get(key), int)
        or job.get(key) != value
        for key, value in strict_integer_fields.items()
    ):
        raise CIGateError(f"Gitea CI job does not match its status: {context}")
    labels = job.get("labels")
    runner_name = job.get("runner_name")
    if (
        labels != ["ci-untrusted-python312"]
        or not isinstance(runner_name, str)
        or not runner_name.startswith("ci-untrusted-")
    ):
        raise CIGateError(
            f"Gitea CI job did not use the trusted CI runner class: {context}"
        )
    expected_target = (
        f"{HTML_ORIGIN}/{owner}/{repository}/actions/runs/{run_id}/jobs/{job_id}"
    )
    if job.get("html_url") != expected_target:
        raise CIGateError(f"Gitea CI job URL does not match its status: {context}")


def validate_ci_gate(
    *,
    owner: str,
    repository: str,
    source_sha: str,
    required_contexts: list[str],
    trusted_actor: str,
    token: str,
) -> dict[str, dict[str, int]]:
    """Require the latest authenticated Actions run and its trusted CI jobs."""
    if SHA_RE.fullmatch(source_sha) is None:
        raise CIGateError("Release source SHA must be canonical lowercase 40-hex")
    if not required_contexts or len(required_contexts) != len(set(required_contexts)):
        raise CIGateError("Required CI contexts must be a non-empty unique set")
    query = urllib.parse.urlencode(
        {
            "branch": "develop",
            "event": "push",
            "head_sha": source_sha,
            "limit": 100,
            "page": 1,
        }
    )
    latest_run = _latest_workflow_run(
        _request_json(f"/repos/{owner}/{repository}/actions/runs?{query}", token=token),
        source_sha=source_sha,
        trusted_actor=trusted_actor,
    )
    run_id = int(latest_run["id"])
    jobs = _required_jobs(
        _request_json(
            f"/repos/{owner}/{repository}/actions/runs/{run_id}/jobs", token=token
        ),
        required_contexts=required_contexts,
    )

    evidence: dict[str, dict[str, int]] = {}
    for context in required_contexts:
        job = jobs[context]
        job_id = int(job["id"])
        _validate_job(
            job,
            context=context,
            owner=owner,
            repository=repository,
            run_id=run_id,
            job_id=job_id,
            source_sha=source_sha,
        )
        evidence[context] = {
            "job_id": job_id,
            "run_attempt": FIRST_JOB_ATTEMPT,
            "run_id": run_id,
        }
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--required-context", action="append", required=True)
    parser.add_argument("--trusted-actor", required=True)
    args = parser.parse_args()
    evidence = validate_ci_gate(
        owner=args.owner,
        repository=args.repository,
        source_sha=args.source_sha,
        required_contexts=args.required_context,
        trusted_actor=args.trusted_actor,
        token=os.getenv("GITEA_API_TOKEN", ""),
    )
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
