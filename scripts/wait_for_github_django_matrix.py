#!/usr/bin/env -S python3 -I
"""Wait for one exact, reviewed GitHub Django-matrix workflow run.

This module is a bootstrap artifact for a future base-pinned supervisor.  It
does not make candidate-controlled package code or tests trusted evidence, and
it must never be imported or executed from a candidate checkout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import socket
import sys
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
REPOSITORY_OWNER = "emersonfelipesp"
REPOSITORY_NAME = "netbox-proxbox"
REPOSITORY = f"{REPOSITORY_OWNER}/{REPOSITORY_NAME}"
REPOSITORY_PREFIX = f"/repos/{REPOSITORY}"
WORKFLOW_PATH = ".github/workflows/django-tests.yml"
WORKFLOW_NAME = "django-tests.yml"
WORKFLOW_API_PATH = f"{REPOSITORY_PREFIX}/actions/workflows/{WORKFLOW_NAME}"
WORKFLOW_CONTENT_PATH = f"{REPOSITORY_PREFIX}/contents/{WORKFLOW_PATH}"
WORKFLOW_RUNS_PATH = f"{WORKFLOW_API_PATH}/runs"

# Git blob identity of django-tests.yml at the reviewed target-branch commit.
# A workflow edit must update this only in a separately reviewed base artifact.
PINNED_WORKFLOW_BLOB_SHA = "54118c16afe255ae18d4aaf8325ea7dc68cebfd4"

TOKEN_ENV = "GH_MATRIX_READ_TOKEN"
DEFAULT_DEADLINE_SECONDS = 45 * 60
DEFAULT_POLL_INTERVAL_SECONDS = 20
DEFAULT_MAX_REQUESTS = 200
DEFAULT_CONCURRENT_GATES = 4
RATE_LIMIT_RESERVE = 200
MIN_AUTHENTICATED_RATE_LIMIT = 5_000
MIN_STARTING_RATE_REMAINING = (
    DEFAULT_CONCURRENT_GATES * DEFAULT_MAX_REQUESTS + RATE_LIMIT_RESERVE
)
MAX_INSTALLATION_PAGES = 10
MAX_REPOSITORY_PAGES = 10
REPOSITORIES_PER_PAGE = 100
RUNS_PER_PAGE = 10
MAX_SETUP_REQUESTS = 1 + MAX_INSTALLATION_PAGES + MAX_REPOSITORY_PAGES + 2
MAX_JSON_BYTES = 1024 * 1024
MAX_IO_SLICE_SECONDS = 10.0
MAX_READ_SLICE_SECONDS = 1.0
RETRY_DELAY_SECONDS = 5.0
READ_CHUNK_BYTES = 64 * 1024

REPO_ROOT = Path(__file__).resolve().parents[1]

_TOKEN_PATTERN = re.compile(r"ghu_[A-Za-z0-9]{20,255}\Z")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_BRANCH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}\Z")
_ALLOWED_API_PATHS = frozenset(
    {
        "/user",
        "/user/installations",
        WORKFLOW_API_PATH,
        WORKFLOW_CONTENT_PATH,
        WORKFLOW_RUNS_PATH,
    }
)
_INSTALLATION_REPOSITORIES_PATH = re.compile(
    r"/user/installations/[1-9][0-9]*/repositories\Z"
)
_REQUIRED_INSTALLATION_PERMISSIONS = {
    "actions": "read",
    "contents": "read",
    "metadata": "read",
}


class WaiterError(RuntimeError):
    """Base class for safe, user-facing waiter failures."""


class InputError(WaiterError):
    """The trusted caller supplied invalid candidate identity data."""


class AuthenticationError(WaiterError):
    """The GitHub credential is missing, invalid, or under-scoped."""


class ApiProtocolError(WaiterError):
    """GitHub returned an unexpected or malformed response."""


class ResponseTooLarge(ApiProtocolError):
    """A response exceeded its fixed byte limit."""


class DeadlineExceeded(WaiterError):
    """The single waiter deadline expired."""


class RequestBudgetExceeded(WaiterError):
    """The waiter exhausted its fixed API request budget."""


class WorkflowIdentityError(WaiterError):
    """The candidate commit does not contain the reviewed workflow blob."""


class RunIdentityError(WaiterError):
    """A returned workflow run does not match every expected identity field."""


class WorkflowRunFailed(WaiterError):
    """The exact workflow run reached a non-success terminal conclusion."""


class _Response(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


class _Opener(Protocol):
    def open(self, request: Request, timeout: float) -> _Response: ...


@dataclass(frozen=True)
class ApiResponse:
    """A decoded, size-bounded GitHub API response."""

    payload: object
    headers: Mapping[str, str]


@dataclass(frozen=True)
class WorkflowIdentity:
    """Reviewed workflow metadata used to bind workflow runs."""

    workflow_id: int
    api_url: str


class Deadline:
    """One monotonic wall-clock deadline shared by all waiter operations."""

    def __init__(
        self,
        seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if seconds <= 0:
            raise ValueError("deadline must be positive")
        self._monotonic = monotonic
        self._sleep = sleep
        self._expires_at = monotonic() + seconds

    def remaining(self, operation: str) -> float:
        """Return time left or fail with the bounded operation name."""
        remaining = self._expires_at - self._monotonic()
        if remaining <= 0:
            raise DeadlineExceeded(f"deadline expired during {operation}")
        return remaining

    def check(self, operation: str) -> None:
        """Fail if the shared deadline has expired."""
        self.remaining(operation)

    def sleep_for(self, seconds: float, operation: str) -> None:
        """Sleep only when the full delay fits inside the shared deadline."""
        if seconds < 0:
            raise ValueError("sleep duration must not be negative")
        remaining = self.remaining(operation)
        if seconds >= remaining:
            raise DeadlineExceeded(f"deadline expired during {operation}")
        self._sleep(seconds)
        self.check(operation)


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from replaying the bearer token to any redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _validate_user_access_token(token: str) -> str:
    if not _TOKEN_PATTERN.fullmatch(token):
        raise AuthenticationError(f"{TOKEN_ENV} must be a GitHub App user access token")
    return token


def take_token_from_environment(environment: MutableMapping[str, str]) -> str:
    """Remove and return the base-owned token before any other work begins."""
    token = environment.pop(TOKEN_ENV, "")
    return _validate_user_access_token(token)


def validate_candidate(branch: str, sha: str) -> tuple[str, str]:
    """Validate a short branch name and a full lowercase Git commit SHA."""
    if not _BRANCH_PATTERN.fullmatch(branch):
        raise InputError("candidate branch has an invalid format")
    if branch.startswith("refs/") or branch.endswith(("/", ".", ".lock")):
        raise InputError("candidate branch must be a short branch name")
    if any(
        part.startswith(".") or part.endswith(".lock") for part in branch.split("/")
    ):
        raise InputError("candidate branch contains an invalid path component")
    if any(fragment in branch for fragment in ("..", "//", "@{")):
        raise InputError("candidate branch contains an invalid sequence")
    if not _SHA_PATTERN.fullmatch(sha):
        raise InputError("candidate SHA must be 40 lowercase hexadecimal characters")
    return branch, sha


def _header(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    for key, value in headers.items():
        if key.casefold() == expected:
            return value
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ApiProtocolError(f"GitHub returned invalid {description}")
    return value


def _set_stream_timeout(response: object, timeout: float) -> None:
    """Apply a shrinking timeout to urllib's socket when it is reachable."""
    candidates = [response]
    current = response
    for attribute in ("fp", "raw", "_sock"):
        current = getattr(current, attribute, None)
        if current is None:
            break
        candidates.append(current)
    for candidate in reversed(candidates):
        setter = getattr(candidate, "settimeout", None)
        if callable(setter):
            setter(timeout)
            return


class GitHubApiClient:
    """Minimal authenticated client for the waiter's fixed GitHub endpoints."""

    def __init__(
        self,
        *,
        token: str,
        deadline: Deadline,
        opener: _Opener | None = None,
        wall_clock: Callable[[], float] = time.time,
        max_requests: int = DEFAULT_MAX_REQUESTS,
    ) -> None:
        self._token = _validate_user_access_token(token)
        self.deadline = deadline
        self._opener = opener or build_opener(ProxyHandler({}), _NoRedirectHandler())
        self._wall_clock = wall_clock
        self._max_requests = max_requests
        self.request_count = 0

    def _url(self, path: str, query: Mapping[str, object] | None) -> str:
        if (
            path not in _ALLOWED_API_PATHS
            and not _INSTALLATION_REPOSITORIES_PATH.fullmatch(path)
        ):
            raise ApiProtocolError("GitHub API path is not allowlisted")
        url = f"{API_ROOT}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    def _request(self, url: str) -> Request:
        return Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "netbox-proxbox-reviewed-matrix-waiter",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )

    def _reserve_request(self) -> None:
        if self.request_count >= self._max_requests:
            raise RequestBudgetExceeded("GitHub API request budget exhausted")
        self.request_count += 1

    def _read_bounded(self, response: _Response, max_bytes: int) -> bytes:
        content_length = _header(response.headers, "Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise ApiProtocolError(
                    "GitHub returned invalid Content-Length"
                ) from exc
            if declared_length < 0:
                raise ApiProtocolError("GitHub returned invalid Content-Length")
            if declared_length > max_bytes:
                raise ResponseTooLarge("GitHub response exceeds the byte limit")

        body = bytearray()
        read = getattr(response, "read1", None)
        if not callable(read):
            read = response.read
        while True:
            remaining = self.deadline.remaining("response reading")
            _set_stream_timeout(response, min(remaining, MAX_READ_SLICE_SECONDS))
            try:
                chunk = read(min(READ_CHUNK_BYTES, max_bytes + 1 - len(body)))
            except (TimeoutError, socket.timeout):
                continue
            self.deadline.check("response reading")
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > max_bytes:
                raise ResponseTooLarge("GitHub response exceeds the byte limit")
        return bytes(body)

    def _rate_limit_delay(self, error: HTTPError) -> float | None:
        retry_after = _header(error.headers, "Retry-After")
        if retry_after is not None:
            try:
                retry_seconds = float(retry_after)
            except ValueError:
                return None
            if not math.isfinite(retry_seconds):
                return None
            return max(1.0, retry_seconds)

        remaining = _header(error.headers, "X-RateLimit-Remaining")
        reset = _header(error.headers, "X-RateLimit-Reset")
        if remaining != "0" or reset is None:
            return None
        try:
            reset_at = float(reset)
        except ValueError:
            return None
        if not math.isfinite(reset_at):
            return None
        return max(1.0, reset_at - self._wall_clock())

    def _handle_http_error(self, error: HTTPError) -> None:
        status = error.code
        if status == 401:
            raise AuthenticationError("GitHub rejected the matrix read token")
        if status == 403:
            delay = self._rate_limit_delay(error)
            if delay is None:
                raise AuthenticationError(
                    "GitHub rejected an invalid or under-scoped matrix read token"
                )
            self.deadline.sleep_for(delay, "rate-limit handling")
            return
        if status == 429:
            delay = self._rate_limit_delay(error)
            if delay is None:
                raise ApiProtocolError(
                    "GitHub returned 429 without rate-limit evidence"
                )
            self.deadline.sleep_for(delay, "rate-limit handling")
            return
        if status in {500, 502, 503, 504}:
            self.deadline.sleep_for(RETRY_DELAY_SECONDS, "GitHub API retry")
            return
        if status in {301, 302, 303, 307, 308}:
            raise ApiProtocolError("GitHub API redirects are not allowed")
        raise ApiProtocolError(f"GitHub API returned HTTP {status}")

    def get_json(
        self,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        max_bytes: int = MAX_JSON_BYTES,
    ) -> ApiResponse:
        """GET and decode one bounded JSON object from an allowlisted path."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        url = self._url(path, query)
        while True:
            self.deadline.check("GitHub API connection")
            self._reserve_request()
            response: _Response | None = None
            try:
                timeout = min(
                    self.deadline.remaining("GitHub API connection"),
                    MAX_IO_SLICE_SECONDS,
                )
                response = self._opener.open(self._request(url), timeout=timeout)
                self.deadline.check("GitHub API connection")
                if response.status != 200:
                    raise ApiProtocolError(
                        f"GitHub API returned unexpected HTTP {response.status}"
                    )
                body = self._read_bounded(response, max_bytes)
                self.deadline.check("JSON parsing")
                try:
                    decoded = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                    raise ApiProtocolError("GitHub returned invalid JSON") from exc
                self.deadline.check("JSON parsing")
                return ApiResponse(payload=decoded, headers=response.headers)
            except HTTPError as exc:
                try:
                    self._handle_http_error(exc)
                finally:
                    exc.close()
            except (URLError, TimeoutError, socket.timeout, OSError):
                self.deadline.sleep_for(RETRY_DELAY_SECONDS, "GitHub API retry")
            finally:
                if response is not None:
                    response.close()


class MatrixWaiter:
    """Authenticate, pin the workflow blob, and wait for one exact push run."""

    def __init__(
        self,
        *,
        client: GitHubApiClient,
        deadline: Deadline,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll interval must be positive")
        self.client = client
        self.deadline = deadline
        self.poll_interval = poll_interval

    def _validate_rate_budget(self, headers: Mapping[str, str]) -> None:
        try:
            limit = int(_header(headers, "X-RateLimit-Limit") or "")
            remaining = int(_header(headers, "X-RateLimit-Remaining") or "")
        except ValueError as exc:
            raise AuthenticationError(
                "GitHub did not provide an authenticated rate limit"
            ) from exc
        if limit < MIN_AUTHENTICATED_RATE_LIMIT:
            raise AuthenticationError(
                "GitHub did not provide an authenticated rate limit"
            )
        if remaining < MIN_STARTING_RATE_REMAINING:
            raise AuthenticationError(
                "GitHub authenticated rate limit has insufficient remaining budget"
            )

    def _validate_user(self, response: ApiResponse) -> None:
        self._validate_rate_budget(response.headers)
        user = _mapping(response.payload, "authenticated user")
        if user.get("login") != REPOSITORY_OWNER:
            raise AuthenticationError(
                "matrix token is not owned by the repository owner"
            )

    def _installation_from_response(
        self,
        value: object,
    ) -> int | None:
        installation = _mapping(value, "GitHub App installation")
        account = _mapping(installation.get("account"), "installation account")
        if account.get("login") != REPOSITORY_OWNER:
            return None
        if installation.get("suspended_at") is not None:
            raise AuthenticationError("GitHub App installation is suspended")
        if installation.get("repository_selection") != "selected":
            raise AuthenticationError(
                "GitHub App installation must select only the matrix repository"
            )
        permissions = _mapping(
            installation.get("permissions"), "installation permissions"
        )
        if dict(permissions) != _REQUIRED_INSTALLATION_PERMISSIONS:
            raise AuthenticationError(
                "matrix token requires only actions:read, contents:read, "
                "and metadata:read repository permissions"
            )
        installation_id = _positive_int(installation.get("id"))
        if installation_id is None:
            raise AuthenticationError("GitHub App installation has an invalid id")
        return installation_id

    def _find_installation(self) -> int:
        for page in range(1, MAX_INSTALLATION_PAGES + 1):
            response = self.client.get_json(
                "/user/installations",
                query={"page": page, "per_page": REPOSITORIES_PER_PAGE},
            )
            payload = _mapping(response.payload, "GitHub App installation list")
            installations = payload.get("installations")
            if not isinstance(installations, list):
                raise ApiProtocolError("GitHub returned invalid installation list")
            for installation in installations:
                match = self._installation_from_response(installation)
                if match is not None:
                    return match
            total_count = payload.get("total_count")
            if (
                isinstance(total_count, bool)
                or not isinstance(total_count, int)
                or total_count < len(installations)
            ):
                raise ApiProtocolError("GitHub returned invalid installation count")
            if page * REPOSITORIES_PER_PAGE >= total_count:
                break
        raise AuthenticationError(
            "matrix token has no correctly scoped repository-owner installation"
        )

    def _installation_has_exact_repository(self, installation_id: int) -> bool:
        path = f"/user/installations/{installation_id}/repositories"
        for page in range(1, MAX_REPOSITORY_PAGES + 1):
            response = self.client.get_json(
                path,
                query={"page": page, "per_page": REPOSITORIES_PER_PAGE},
            )
            payload = _mapping(response.payload, "installation repository list")
            repositories = payload.get("repositories")
            if not isinstance(repositories, list):
                raise ApiProtocolError(
                    "GitHub returned invalid installation repository list"
                )
            total_count = payload.get("total_count")
            if (
                isinstance(total_count, bool)
                or not isinstance(total_count, int)
                or total_count != 1
            ):
                raise AuthenticationError(
                    "matrix token installation must select exactly one repository"
                )
            for repository in repositories:
                item = _mapping(repository, "installation repository")
                owner = _mapping(item.get("owner"), "installation repository owner")
                if (
                    item.get("full_name") == REPOSITORY
                    and item.get("name") == REPOSITORY_NAME
                    and owner.get("login") == REPOSITORY_OWNER
                ):
                    return True
            if page * REPOSITORIES_PER_PAGE >= total_count:
                return False
        raise AuthenticationError(
            "exact repository not found within bounded token scope"
        )

    def authenticate(self) -> None:
        """Prove token validity, readable permissions, ownership, and repo scope."""
        user = self.client.get_json("/user")
        self._validate_user(user)
        installation_id = self._find_installation()
        if not self._installation_has_exact_repository(installation_id):
            raise AuthenticationError("matrix token cannot access the exact repository")

    def _workflow_identity(self) -> WorkflowIdentity:
        response = self.client.get_json(WORKFLOW_API_PATH)
        workflow = _mapping(response.payload, "workflow metadata")
        workflow_id = _positive_int(workflow.get("id"))
        if workflow_id is None:
            raise WorkflowIdentityError("reviewed workflow has an invalid workflow id")
        if workflow.get("path") != WORKFLOW_PATH:
            raise WorkflowIdentityError("reviewed workflow path does not match")
        if workflow.get("state") != "active":
            raise WorkflowIdentityError("reviewed workflow is not active")
        expected_url = f"{API_ROOT}{REPOSITORY_PREFIX}/actions/workflows/{workflow_id}"
        if workflow.get("url") != expected_url:
            raise WorkflowIdentityError("reviewed workflow API identity does not match")
        return WorkflowIdentity(workflow_id=workflow_id, api_url=expected_url)

    def _verify_workflow_blob(self, candidate_sha: str) -> None:
        response = self.client.get_json(
            WORKFLOW_CONTENT_PATH,
            query={"ref": candidate_sha},
        )
        content = _mapping(response.payload, "workflow content metadata")
        if content.get("type") != "file" or content.get("path") != WORKFLOW_PATH:
            raise WorkflowIdentityError("candidate workflow is not the reviewed file")
        if content.get("sha") != PINNED_WORKFLOW_BLOB_SHA:
            raise WorkflowIdentityError(
                "candidate workflow blob does not match the pin"
            )

    def _validate_run(
        self,
        value: object,
        *,
        branch: str,
        sha: str,
        workflow: WorkflowIdentity,
    ) -> Mapping[str, object]:
        run = _mapping(value, "workflow run")
        run_id = _positive_int(run.get("id"))
        if run_id is None:
            raise RunIdentityError("workflow run has an invalid id")
        if run.get("workflow_id") != workflow.workflow_id:
            raise RunIdentityError("workflow run has the wrong workflow id")
        if run.get("workflow_url") != workflow.api_url:
            raise RunIdentityError("workflow run has the wrong workflow API identity")
        expected_run_url = f"{API_ROOT}{REPOSITORY_PREFIX}/actions/runs/{run_id}"
        if run.get("url") != expected_run_url:
            raise RunIdentityError("workflow run has the wrong API identity")
        repository = _mapping(run.get("repository"), "workflow run repository")
        head_repository = _mapping(
            run.get("head_repository"), "workflow run head repository"
        )
        if (
            repository.get("full_name") != REPOSITORY
            or head_repository.get("full_name") != REPOSITORY
        ):
            raise RunIdentityError("workflow run has the wrong repository identity")
        if run.get("head_branch") != branch:
            raise RunIdentityError("workflow run has the wrong branch provenance")
        if run.get("head_sha") != sha:
            raise RunIdentityError("workflow run has the wrong SHA")
        head_commit = _mapping(run.get("head_commit"), "workflow run head commit")
        if head_commit.get("id") != sha:
            raise RunIdentityError("workflow run has the wrong head commit identity")
        if run.get("event") != "push":
            raise RunIdentityError("workflow run is not push provenance")
        expected_title = f"Django Tests (push refs/heads/{branch} @ {sha})"
        if run.get("display_title") != expected_title:
            raise RunIdentityError("workflow run is not exact branch-ref provenance")
        if run.get("path") != f"{WORKFLOW_PATH}@{branch}":
            raise RunIdentityError("workflow run has the wrong workflow path/ref")
        if _positive_int(run.get("run_attempt")) is None:
            raise RunIdentityError("workflow run has an invalid attempt")
        return run

    def _matching_runs(
        self,
        branch: str,
        sha: str,
        workflow: WorkflowIdentity,
    ) -> Sequence[Mapping[str, object]]:
        response = self.client.get_json(
            WORKFLOW_RUNS_PATH,
            query={
                "branch": branch,
                "event": "push",
                "head_sha": sha,
                "per_page": RUNS_PER_PAGE,
            },
        )
        payload = _mapping(response.payload, "workflow run list")
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            raise ApiProtocolError("GitHub returned invalid workflow runs")
        total_count = payload.get("total_count")
        if (
            isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count < len(runs)
        ):
            raise ApiProtocolError("GitHub returned invalid workflow run count")
        return [
            self._validate_run(run, branch=branch, sha=sha, workflow=workflow)
            for run in runs
        ]

    def wait_for_success(self, branch: str, sha: str) -> Mapping[str, object]:
        """Return only a successful exact-identity push run before the deadline."""
        branch, sha = validate_candidate(branch, sha)
        self.authenticate()
        workflow = self._workflow_identity()
        self._verify_workflow_blob(sha)

        while True:
            runs = self._matching_runs(branch, sha, workflow)
            for run in runs:
                status = run.get("status")
                conclusion = run.get("conclusion")
                if status == "completed":
                    if conclusion == "success":
                        return run
                    rendered = conclusion if isinstance(conclusion, str) else "missing"
                    raise WorkflowRunFailed(
                        f"exact Django workflow run concluded with {rendered}"
                    )
                if status not in {
                    "requested",
                    "waiting",
                    "pending",
                    "queued",
                    "in_progress",
                }:
                    raise ApiProtocolError(
                        "GitHub returned invalid workflow run status"
                    )
            self.deadline.sleep_for(self.poll_interval, "workflow polling")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wait for the exact reviewed GitHub Django matrix run."
    )
    parser.add_argument("--candidate-branch", required=True)
    parser.add_argument("--candidate-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for a future base-pinned external supervisor."""
    try:
        token = take_token_from_environment(os.environ)
        if not sys.flags.isolated:
            raise AuthenticationError("waiter must run with Python isolated mode (-I)")
        arguments = _parser().parse_args(argv)
        branch, sha = validate_candidate(
            arguments.candidate_branch,
            arguments.candidate_sha,
        )
        deadline = Deadline(DEFAULT_DEADLINE_SECONDS)
        client = GitHubApiClient(token=token, deadline=deadline)
        matrix_waiter = MatrixWaiter(client=client, deadline=deadline)
        run = matrix_waiter.wait_for_success(branch, sha)
    except WaiterError as exc:
        print(f"Django matrix verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Verified reviewed Django matrix push run {run['id']} for {branch}@{sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
