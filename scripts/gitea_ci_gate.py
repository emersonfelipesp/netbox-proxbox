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


def _job_ids(target_url: object, *, owner: str, repository: str) -> tuple[int, int]:
    if not isinstance(target_url, str):
        raise CIGateError("Successful CI status has no job target URL")
    parsed = urllib.parse.urlsplit(target_url)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != "git.nmulti.cloud":
            raise CIGateError("CI status target is outside canonical Gitea")
        path = parsed.path
    else:
        path = target_url
    if parsed.query or parsed.fragment:
        raise CIGateError("CI status target URL must not contain parameters")
    match = re.fullmatch(
        rf"/{re.escape(owner)}/{re.escape(repository)}/actions/runs/([1-9][0-9]*)/jobs/([1-9][0-9]*)",
        path,
    )
    if match is None:
        raise CIGateError("CI status target is not an exact Gitea Actions job")
    return int(match.group(1)), int(match.group(2))


def _expected_job_name(context: str) -> str:
    prefix, suffix = "CI / ", " (push)"
    if not context.startswith(prefix) or not context.endswith(suffix):
        raise CIGateError(f"Unsupported release CI context: {context!r}")
    name = context[len(prefix) : -len(suffix)]
    if not name:
        raise CIGateError("Release CI job name is empty")
    return name


def _latest_statuses(
    statuses: object, *, required_contexts: list[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(statuses, list):
        raise CIGateError("Gitea commit statuses are malformed")
    latest: dict[str, dict[str, Any]] = {}
    for row in statuses:
        if not isinstance(row, dict) or row.get("context") not in required_contexts:
            continue
        status_id = row.get("id")
        if (
            isinstance(status_id, bool)
            or not isinstance(status_id, int)
            or status_id <= 0
        ):
            raise CIGateError("Gitea commit status ID is invalid")
        context = str(row["context"])
        if context not in latest or status_id > int(latest[context]["id"]):
            latest[context] = row
    if set(latest) != set(required_contexts):
        raise CIGateError("Required CI status context is missing")
    return latest


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
        "id": run_id,
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
    if not isinstance(actor, dict) or actor.get("login") != trusted_actor:
        raise CIGateError(f"Gitea CI run actor is not trusted: {context}")


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
        "id": job_id,
        "run_id": run_id,
        "name": _expected_job_name(context),
        "status": "completed",
        "conclusion": "success",
        "head_sha": source_sha,
    }
    if not isinstance(job, dict) or any(
        job.get(key) != value for key, value in expected.items()
    ):
        raise CIGateError(f"Gitea CI job does not match its status: {context}")
    labels = job.get("labels")
    runner_name = job.get("runner_name")
    if (
        not isinstance(labels, list)
        or "ci-untrusted-python312" not in labels
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
    """Require each latest status to resolve to one trusted successful CI job."""
    if SHA_RE.fullmatch(source_sha) is None:
        raise CIGateError("Release source SHA must be canonical lowercase 40-hex")
    if not required_contexts or len(required_contexts) != len(set(required_contexts)):
        raise CIGateError("Required CI contexts must be a non-empty unique set")
    latest = _latest_statuses(
        _request_json(
            f"/repos/{owner}/{repository}/commits/{source_sha}/statuses?limit=100",
            token=token,
        ),
        required_contexts=required_contexts,
    )

    evidence: dict[str, dict[str, int]] = {}
    for context in required_contexts:
        status = latest[context]
        if status.get("status") != "success":
            raise CIGateError(f"Latest required CI status is not successful: {context}")
        run_id, job_id = _job_ids(
            status.get("target_url"), owner=owner, repository=repository
        )
        run = _request_json(
            f"/repos/{owner}/{repository}/actions/runs/{run_id}", token=token
        )
        job = _request_json(
            f"/repos/{owner}/{repository}/actions/jobs/{job_id}", token=token
        )
        _validate_run(
            run,
            context=context,
            run_id=run_id,
            source_sha=source_sha,
            trusted_actor=trusted_actor,
        )
        _validate_job(
            job,
            context=context,
            owner=owner,
            repository=repository,
            run_id=run_id,
            job_id=job_id,
            source_sha=source_sha,
        )
        evidence[context] = {"job_id": job_id, "run_id": run_id}
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
