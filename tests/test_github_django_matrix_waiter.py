"""Security contracts for the reviewed GitHub Django-matrix waiter.

The eventual caller must execute the waiter from a base-owned checkout.  These
tests exercise the artifact itself; they do not make candidate-owned tests into
trusted evidence and they never contact GitHub.
"""

from __future__ import annotations

import hashlib
import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from scripts import wait_for_github_django_matrix as waiter


TOKEN = "ghu_" + "A" * 36
BRANCH = "300-ci-gate-bootstrap"
SHA = "a" * 40
NOT_BEFORE = "2026-08-09T20:00:00Z"
RUN_CREATED_AT = "2026-08-09T20:01:00Z"
RATE_HEADERS = {
    "X-RateLimit-Limit": "5000",
    "X-RateLimit-Remaining": "4999",
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.wall_now = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.wall_now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        self.wall_now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.wall_now += seconds


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
        status: int = 200,
        clock: FakeClock | None = None,
        read_seconds: float = 0.0,
    ) -> None:
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self._body = io.BytesIO(json.dumps(payload).encode())
        self._clock = clock
        self._read_seconds = read_seconds
        self.closed = False

    def read1(self, size: int) -> bytes:
        if self._clock is not None:
            self._clock.advance(self._read_seconds)
        return self._body.read(size)

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, *outcomes: object, clock: FakeClock | None = None) -> None:
        self.outcomes = list(outcomes)
        self.clock = clock
        self.open_seconds = 0.0
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        if self.clock is not None:
            self.clock.advance(self.open_seconds)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, FakeResponse)
        return outcome


class StubClient:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def get_json(
        self,
        path: str,
        *,
        query: dict[str, object] | None = None,
        max_bytes: int = waiter.MAX_JSON_BYTES,
    ) -> waiter.ApiResponse:
        del max_bytes
        self.calls.append((path, query))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, waiter.ApiResponse)
        return response


def api_response(payload: object, headers: dict[str, str] | None = None):
    return waiter.ApiResponse(
        payload=payload,
        headers=RATE_HEADERS if headers is None else headers,
    )


def installation_payload(
    *,
    installation_id: int = 17,
    owner: str = waiter.REPOSITORY_OWNER,
    actions: str = "read",
    contents: str = "read",
    extra_permissions: dict[str, str] | None = None,
) -> dict[str, object]:
    permissions = {
        "actions": actions,
        "contents": contents,
        "metadata": "read",
    }
    permissions.update(extra_permissions or {})
    return {
        "id": installation_id,
        "account": {"login": owner},
        "permissions": permissions,
        "repository_selection": "selected",
        "suspended_at": None,
    }


def user_payload(login: str = waiter.REPOSITORY_OWNER) -> dict[str, object]:
    return {"login": login}


def installations_payload(*installations: dict[str, object]) -> dict[str, object]:
    return {
        "total_count": len(installations),
        "installations": list(installations),
    }


def repositories_payload(*names: str) -> dict[str, object]:
    return {
        "total_count": len(names),
        "repositories": [
            {
                "full_name": name,
                "name": name.split("/", 1)[-1],
                "owner": {"login": name.split("/", 1)[0]},
            }
            for name in names
        ],
    }


def workflow_payload() -> dict[str, object]:
    return {
        "id": 42,
        "path": waiter.WORKFLOW_PATH,
        "state": "active",
        "url": f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/workflows/42",
    }


def content_payload(blob_sha: str = waiter.PINNED_WORKFLOW_BLOB_SHA):
    return {
        "type": "file",
        "path": waiter.WORKFLOW_PATH,
        "sha": blob_sha,
    }


def run_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": 99,
        "workflow_id": 42,
        "workflow_url": (
            f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/workflows/42"
        ),
        "url": f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99",
        "repository": {"full_name": waiter.REPOSITORY},
        "head_repository": {"full_name": waiter.REPOSITORY},
        "head_branch": BRANCH,
        "head_sha": SHA,
        "head_commit": {"id": SHA},
        "event": "push",
        "display_title": f"Django Tests (push refs/heads/{BRANCH} @ {SHA})",
        "path": waiter.WORKFLOW_PATH,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": RUN_CREATED_AT,
    }
    payload.update(overrides)
    return payload


def ready_client(*run_responses: object) -> StubClient:
    return StubClient(
        api_response(user_payload()),
        api_response(installations_payload(installation_payload())),
        api_response(repositories_payload(waiter.REPOSITORY)),
        api_response(workflow_payload()),
        api_response(content_payload()),
        *run_responses,
    )


def build_waiter(client: StubClient, clock: FakeClock | None = None):
    clock = clock or FakeClock()
    deadline = waiter.Deadline(
        waiter.DEFAULT_DEADLINE_SECONDS,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return waiter.MatrixWaiter(client=client, deadline=deadline), clock


def test_token_is_required_only_in_environment_and_removed_immediately():
    environment = {waiter.TOKEN_ENV: TOKEN, "CANDIDATE_VALUE": "still-present"}

    assert waiter.take_token_from_environment(environment) == TOKEN
    assert waiter.TOKEN_ENV not in environment
    assert environment["CANDIDATE_VALUE"] == "still-present"


def test_cli_requires_python_isolation_before_candidate_argument_handling():
    source = (waiter.REPO_ROOT / "scripts/wait_for_github_django_matrix.py").read_text()

    assert source.startswith("#!/usr/bin/env -S python3 -I\n")
    main_source = source.split("def main(", 1)[1]
    assert main_source.index("take_token_from_environment") < main_source.index(
        "parse_args"
    )
    assert "sys.flags.isolated" in main_source


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {waiter.TOKEN_ENV: ""},
        {waiter.TOKEN_ENV: "ghp_" + "A" * 36},
        {waiter.TOKEN_ENV: "ghs_" + "A" * 36},
        {waiter.TOKEN_ENV: "ghu_too short"},
        {waiter.TOKEN_ENV: "github_pat_" + "A" * 80},
    ],
)
def test_missing_or_unverifiable_credentials_fail_before_api_use(environment):
    with pytest.raises(waiter.AuthenticationError):
        waiter.take_token_from_environment(environment)


@pytest.mark.parametrize(
    ("actions", "contents"),
    [("none", "read"), ("read", "none"), ("write", "read"), ("read", "write")],
)
def test_wrong_installation_permissions_fail_immediately(actions, contents):
    client = StubClient(
        api_response(user_payload()),
        api_response(
            installations_payload(
                installation_payload(actions=actions, contents=contents)
            )
        ),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="permission"):
        matrix_waiter.authenticate()

    assert len(client.calls) == 2


def test_extra_repository_permission_is_rejected_as_over_scoped():
    client = StubClient(
        api_response(user_payload()),
        api_response(
            installations_payload(
                installation_payload(extra_permissions={"issues": "read"})
            )
        ),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="only actions"):
        matrix_waiter.authenticate()

    assert len(client.calls) == 2


def test_token_without_exact_repository_access_fails_during_authentication():
    client = StubClient(
        api_response(user_payload()),
        api_response(installations_payload(installation_payload())),
        api_response(repositories_payload("emersonfelipesp/another-repo")),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="exact repository"):
        matrix_waiter.authenticate()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "59"},
        {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "999"},
    ],
)
def test_authentication_requires_authenticated_rate_budget(headers):
    client = StubClient(api_response(user_payload(), headers))
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="rate limit"):
        matrix_waiter.authenticate()


def test_invalid_or_suspended_installation_fails_before_repository_lookup():
    suspended = installation_payload()
    suspended["suspended_at"] = "2026-08-09T00:00:00Z"
    client = StubClient(
        api_response(user_payload()),
        api_response(installations_payload(suspended)),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="suspended"):
        matrix_waiter.authenticate()

    assert len(client.calls) == 2


def test_token_must_belong_to_exact_repository_owner():
    client = StubClient(api_response(user_payload("candidate-user")))
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="repository owner"):
        matrix_waiter.authenticate()

    assert len(client.calls) == 1


def test_installation_must_select_only_the_exact_repository():
    client = StubClient(
        api_response(user_payload()),
        api_response(installations_payload(installation_payload())),
        api_response(
            repositories_payload(waiter.REPOSITORY, "emersonfelipesp/another-repo")
        ),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="exactly one"):
        matrix_waiter.authenticate()


def test_token_with_multiple_accessible_installations_is_rejected():
    client = StubClient(
        api_response(user_payload()),
        api_response(
            installations_payload(
                installation_payload(),
                installation_payload(
                    installation_id=18,
                    owner="unrelated-private-owner",
                ),
            )
        ),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="exactly one accessible"):
        matrix_waiter.authenticate()

    assert len(client.calls) == 2


def test_installation_discovery_exhausts_pagination_before_accepting(monkeypatch):
    monkeypatch.setattr(waiter, "REPOSITORIES_PER_PAGE", 1)
    client = StubClient(
        api_response(user_payload()),
        api_response(
            {
                "total_count": 2,
                "installations": [installation_payload()],
            }
        ),
        api_response(
            {
                "total_count": 2,
                "installations": [
                    installation_payload(
                        installation_id=18,
                        owner="unrelated-private-owner",
                    )
                ],
            }
        ),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.AuthenticationError, match="exactly one accessible"):
        matrix_waiter.authenticate()

    assert client.calls[1:] == [
        ("/user/installations", {"page": 1, "per_page": 1}),
        ("/user/installations", {"page": 2, "per_page": 1}),
    ]


@pytest.mark.parametrize(
    ("branch", "sha"),
    [
        ("", SHA),
        ("refs/heads/develop", SHA),
        ("../develop", SHA),
        ("release~1", SHA),
        (BRANCH, "abc123"),
        (BRANCH, "A" * 40),
    ],
)
def test_candidate_branch_and_full_sha_are_strictly_validated(branch, sha):
    with pytest.raises(waiter.InputError):
        waiter.validate_candidate(branch, sha)


def test_current_run_selector_requires_expected_id_or_not_before_api_use():
    client = StubClient()
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.InputError, match="expected run ID or not-before"):
        matrix_waiter.wait_for_success(BRANCH, SHA)

    assert client.calls == []


@pytest.mark.parametrize(
    ("expected_run_id", "not_before"),
    [
        (0, None),
        (True, None),
        ("01", None),
        (None, "2026-08-09 20:00:00Z"),
        (None, "2026-02-30T20:00:00Z"),
    ],
)
def test_current_run_selector_is_strictly_validated(expected_run_id, not_before):
    with pytest.raises(waiter.InputError):
        waiter.validate_run_selector(expected_run_id, not_before)


def test_reviewed_workflow_pin_matches_the_committed_git_blob():
    workflow = waiter.REPO_ROOT / waiter.WORKFLOW_PATH
    body = workflow.read_bytes()
    git_blob = b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    digest = hashlib.sha1(git_blob, usedforsecurity=False).hexdigest()

    assert digest == waiter.PINNED_WORKFLOW_BLOB_SHA
    assert (
        b"run-name: Django Tests (${{ github.event_name }} ${{ github.ref }} @ "
        b"${{ github.sha }})" in body
    )


def test_success_requires_auth_blob_pin_and_exact_push_run_identity():
    client = ready_client(
        api_response({"total_count": 1, "workflow_runs": [run_payload()]})
    )
    matrix_waiter, _clock = build_waiter(client)

    run = matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert run["id"] == 99
    assert client.calls[-1] == (
        waiter.WORKFLOW_RUNS_PATH,
        {
            "branch": BRANCH,
            "event": "push",
            "head_sha": SHA,
            "per_page": waiter.RUNS_PER_PAGE,
        },
    )


def test_recorded_github_run_shape_with_bare_workflow_path_is_accepted():
    # Sanitized from the live repository response captured during review.  The
    # identity values use this hermetic test's constants, while the field set
    # and the bare ``path`` preserve GitHub's actual workflow-runs payload.
    recorded_run = run_payload(
        name="Django Tests",
        node_id="WFR_kwLORecordedPayload",
        run_number=884,
        check_suite_id=52345678901,
        check_suite_node_id="CS_kwDORecordedPayload",
        html_url=(f"https://github.com/{waiter.REPOSITORY}/actions/runs/99"),
        pull_requests=[],
        created_at=RUN_CREATED_AT,
        updated_at="2026-08-09T20:14:37Z",
        actor={
            "login": waiter.REPOSITORY_OWNER,
            "id": 123456,
            "type": "User",
        },
        triggering_actor={
            "login": waiter.REPOSITORY_OWNER,
            "id": 123456,
            "type": "User",
        },
        jobs_url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99/jobs",
        logs_url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99/logs",
        artifacts_url=(
            f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99/artifacts"
        ),
        cancel_url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99/cancel",
        rerun_url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/99/rerun",
        previous_attempt_url=None,
        path=waiter.WORKFLOW_PATH,
    )
    client = ready_client(
        api_response({"total_count": 1, "workflow_runs": [recorded_run]})
    )
    matrix_waiter, _clock = build_waiter(client)

    run = matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert run["id"] == 99
    assert run["path"] == waiter.WORKFLOW_PATH


def test_candidate_workflow_blob_mismatch_fails_before_polling():
    client = StubClient(
        api_response(user_payload()),
        api_response(installations_payload(installation_payload())),
        api_response(repositories_payload(waiter.REPOSITORY)),
        api_response(workflow_payload()),
        api_response(content_payload("b" * 40)),
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.WorkflowIdentityError, match="blob"):
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert all(path != waiter.WORKFLOW_RUNS_PATH for path, _query in client.calls)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"head_branch": "develop"}, "branch"),
        (
            {"head_branch": "v0.0.24"},
            "branch",
        ),
        ({"head_sha": "b" * 40}, "SHA"),
        ({"head_commit": {"id": "b" * 40}}, "commit"),
        ({"event": "pull_request"}, "push"),
        (
            {"display_title": f"Django Tests (push refs/tags/{BRANCH} @ {SHA})"},
            "branch-ref",
        ),
        ({"path": f"{waiter.WORKFLOW_PATH}@{BRANCH}"}, "workflow path"),
        ({"path": f"{waiter.WORKFLOW_PATH}@develop"}, "workflow path"),
        ({"created_at": None}, "creation time"),
        ({"workflow_id": 41}, "workflow"),
        ({"repository": {"full_name": "edgeuno/netbox-proxbox"}}, "repository"),
        ({"head_repository": {"full_name": "edgeuno/netbox-proxbox"}}, "repository"),
    ],
)
def test_same_sha_or_similar_run_with_wrong_identity_is_rejected(overrides, message):
    client = ready_client(
        api_response({"total_count": 1, "workflow_runs": [run_payload(**overrides)]})
    )
    matrix_waiter, _clock = build_waiter(client)

    with pytest.raises(waiter.RunIdentityError, match=message):
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out", "skipped"])
def test_terminal_non_success_conclusion_fails_immediately(conclusion):
    client = ready_client(
        api_response(
            {
                "total_count": 1,
                "workflow_runs": [run_payload(conclusion=conclusion)],
            }
        )
    )
    matrix_waiter, clock = build_waiter(client)

    with pytest.raises(waiter.WorkflowRunFailed, match=conclusion):
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert clock.sleeps == []


def test_queued_run_polls_then_accepts_completed_success():
    client = ready_client(
        api_response(
            {
                "total_count": 1,
                "workflow_runs": [run_payload(status="queued", conclusion=None)],
            }
        ),
        api_response({"total_count": 1, "workflow_runs": [run_payload()]}),
    )
    matrix_waiter, clock = build_waiter(client)

    assert (
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)["id"] == 99
    )
    assert clock.sleeps == [waiter.DEFAULT_POLL_INTERVAL_SECONDS]


def test_newer_queued_run_is_pinned_and_older_success_is_never_accepted():
    newer_created_at = "2026-08-09T20:02:00Z"
    newer_queued = run_payload(
        id=100,
        url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/100",
        status="queued",
        conclusion=None,
        created_at=newer_created_at,
    )
    older_success = run_payload(created_at=RUN_CREATED_AT)
    newer_in_progress = {
        **newer_queued,
        "status": "in_progress",
    }
    newer_success = {
        **newer_queued,
        "status": "completed",
        "conclusion": "success",
    }
    later_success = run_payload(
        id=101,
        url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/101",
        created_at="2026-08-09T20:03:00Z",
    )
    client = ready_client(
        api_response(
            {
                "total_count": 2,
                "workflow_runs": [newer_queued, older_success],
            }
        ),
        api_response(
            {
                "total_count": 3,
                "workflow_runs": [
                    later_success,
                    newer_in_progress,
                    older_success,
                ],
            }
        ),
        api_response(
            {
                "total_count": 3,
                "workflow_runs": [later_success, newer_success, older_success],
            }
        ),
    )
    matrix_waiter, clock = build_waiter(client)

    run = matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert run["id"] == 100
    assert clock.sleeps == [
        waiter.DEFAULT_POLL_INTERVAL_SECONDS,
        waiter.DEFAULT_POLL_INTERVAL_SECONDS,
    ]


def test_not_before_ignores_an_old_success_until_a_fresh_run_exists():
    old_success = run_payload(
        id=98,
        url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/98",
        created_at="2026-08-09T19:59:59Z",
    )
    client = ready_client(
        api_response(
            {
                "total_count": 1,
                "workflow_runs": [old_success],
            }
        ),
        api_response(
            {
                "total_count": 2,
                "workflow_runs": [run_payload(), old_success],
            }
        ),
    )
    matrix_waiter, clock = build_waiter(client)

    run = matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert run["id"] == 99
    assert clock.sleeps == [waiter.DEFAULT_POLL_INTERVAL_SECONDS]


def test_discovery_rejects_ambiguous_newest_creation_time():
    same_time_run = run_payload(
        id=100,
        url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/100",
    )
    client = ready_client(
        api_response(
            {
                "total_count": 2,
                "workflow_runs": [same_time_run, run_payload()],
            }
        )
    )
    matrix_waiter, clock = build_waiter(client)

    with pytest.raises(waiter.RunIdentityError, match="newest creation time"):
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)

    assert clock.sleeps == []


def test_expected_run_id_waits_for_only_the_supervisor_selected_run():
    expected_queued = run_payload(
        id=100,
        url=f"{waiter.API_ROOT}{waiter.REPOSITORY_PREFIX}/actions/runs/100",
        status="queued",
        conclusion=None,
    )
    expected_success = {
        **expected_queued,
        "status": "completed",
        "conclusion": "success",
    }
    client = ready_client(
        api_response(
            {
                "total_count": 2,
                "workflow_runs": [expected_queued, run_payload()],
            }
        ),
        api_response(
            {
                "total_count": 2,
                "workflow_runs": [expected_success, run_payload()],
            }
        ),
    )
    matrix_waiter, clock = build_waiter(client)

    run = matrix_waiter.wait_for_success(BRANCH, SHA, expected_run_id="100")

    assert run["id"] == 100
    assert clock.sleeps == [waiter.DEFAULT_POLL_INTERVAL_SECONDS]


def make_http_error(status: int, headers: dict[str, str] | None = None) -> HTTPError:
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return HTTPError(
        f"{waiter.API_ROOT}/user",
        status,
        "test error",
        message,
        io.BytesIO(b'{"message":"redacted test error"}'),
    )


def build_api(
    opener: FakeOpener,
    clock: FakeClock | None = None,
    *,
    seconds: float = 30.0,
    max_requests: int = waiter.DEFAULT_MAX_REQUESTS,
):
    clock = clock or FakeClock()
    deadline = waiter.Deadline(
        seconds,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return (
        waiter.GitHubApiClient(
            token=TOKEN,
            deadline=deadline,
            opener=opener,
            wall_clock=clock.time,
            max_requests=max_requests,
        ),
        clock,
    )


def test_api_client_uses_only_fixed_github_origin_and_bearer_header():
    opener = FakeOpener(FakeResponse({"ok": True}))
    api, _clock = build_api(opener)

    api.get_json("/user", query={"candidate": "a/b & tag"})

    request, timeout = opener.calls[0]
    assert request.full_url == ("https://api.github.com/user?candidate=a%2Fb+%26+tag")
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert 0 < timeout <= waiter.MAX_IO_SLICE_SECONDS
    with pytest.raises(waiter.ApiProtocolError, match="allowlisted"):
        api.get_json("https://attacker.invalid/collect")


def test_response_size_limit_rejects_content_length_and_stream_overflow():
    declared = FakeResponse({"ok": True}, headers={"Content-Length": "101"})
    streamed = FakeResponse("x" * 101)
    opener = FakeOpener(declared, streamed)
    api, _clock = build_api(opener)

    with pytest.raises(waiter.ResponseTooLarge):
        api.get_json("/user", max_bytes=100)
    with pytest.raises(waiter.ResponseTooLarge):
        api.get_json("/user", max_bytes=100)


def test_invalid_utf8_or_json_fails_closed():
    invalid = FakeResponse({"unused": True})
    invalid._body = io.BytesIO(b"not-json")
    opener = FakeOpener(invalid)
    api, _clock = build_api(opener)

    with pytest.raises(waiter.ApiProtocolError, match="JSON"):
        api.get_json("/user")


def test_non_rate_limit_403_is_never_retried():
    opener = FakeOpener(
        make_http_error(403, {"X-RateLimit-Remaining": "4999"}),
        FakeResponse({"must": "not run"}),
    )
    api, clock = build_api(opener)

    with pytest.raises(waiter.AuthenticationError, match="under-scoped"):
        api.get_json("/user")

    assert len(opener.calls) == 1
    assert clock.sleeps == []


def test_malformed_rate_limit_evidence_does_not_authorize_a_403_retry():
    opener = FakeOpener(
        make_http_error(403, {"Retry-After": "NaN"}),
        FakeResponse({"must": "not run"}),
    )
    api, clock = build_api(opener)

    with pytest.raises(waiter.AuthenticationError, match="under-scoped"):
        api.get_json("/user")

    assert len(opener.calls) == 1
    assert clock.sleeps == []


def test_invalid_401_credential_is_never_retried():
    opener = FakeOpener(
        make_http_error(401),
        FakeResponse({"must": "not run"}),
    )
    api, clock = build_api(opener)

    with pytest.raises(waiter.AuthenticationError, match="rejected"):
        api.get_json("/user")

    assert len(opener.calls) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "2", "X-RateLimit-Remaining": "12"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1002"},
    ],
)
def test_403_retries_only_with_header_rate_limit_evidence(headers):
    clock = FakeClock()
    opener = FakeOpener(
        make_http_error(403, headers),
        FakeResponse({"ok": True}),
        clock=clock,
    )
    api, _clock = build_api(opener, clock)

    assert api.get_json("/user").payload == {"ok": True}
    assert len(opener.calls) == 2
    assert clock.sleeps == [2.0]


def test_one_deadline_covers_connection_read_and_json_parse(monkeypatch):
    clock = FakeClock()
    connection = FakeOpener(FakeResponse({"ok": True}), clock=clock)
    connection.open_seconds = 6.0
    api, _clock = build_api(connection, clock, seconds=5.0)
    with pytest.raises(waiter.DeadlineExceeded, match="connection"):
        api.get_json("/user")

    clock = FakeClock()
    response = FakeResponse({"ok": True}, clock=clock, read_seconds=6.0)
    api, _clock = build_api(FakeOpener(response), clock, seconds=5.0)
    with pytest.raises(waiter.DeadlineExceeded, match="response"):
        api.get_json("/user")

    clock = FakeClock()
    api, _clock = build_api(FakeOpener(FakeResponse({"ok": True})), clock, seconds=5.0)
    real_loads = waiter.json.loads

    def slow_loads(value: str):
        clock.advance(6.0)
        return real_loads(value)

    monkeypatch.setattr(waiter.json, "loads", slow_loads)
    with pytest.raises(waiter.DeadlineExceeded, match="JSON"):
        api.get_json("/user")


def test_one_deadline_also_bounds_retry_rate_limit_and_poll_sleeps():
    clock = FakeClock()
    api, _clock = build_api(
        FakeOpener(make_http_error(503), clock=clock),
        clock,
        seconds=5.0,
    )
    with pytest.raises(waiter.DeadlineExceeded, match="retry"):
        api.get_json("/user")

    clock = FakeClock()
    api, _clock = build_api(
        FakeOpener(make_http_error(403, {"Retry-After": "5"}), clock=clock),
        clock,
        seconds=5.0,
    )
    with pytest.raises(waiter.DeadlineExceeded, match="rate-limit"):
        api.get_json("/user")

    clock = FakeClock()
    deadline = waiter.Deadline(
        5.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    matrix_waiter = waiter.MatrixWaiter(
        client=ready_client(
            api_response(
                {
                    "total_count": 1,
                    "workflow_runs": [
                        run_payload(status="in_progress", conclusion=None)
                    ],
                }
            )
        ),
        deadline=deadline,
    )
    with pytest.raises(waiter.DeadlineExceeded, match="polling"):
        matrix_waiter.wait_for_success(BRANCH, SHA, not_before=NOT_BEFORE)


def test_request_cap_is_independent_of_deadline():
    opener = FakeOpener(
        FakeResponse({"ok": 1}),
        FakeResponse({"ok": 2}),
        FakeResponse({"must": "not run"}),
    )
    api, _clock = build_api(opener, max_requests=2)

    api.get_json("/user")
    api.get_json("/user")
    with pytest.raises(waiter.RequestBudgetExceeded):
        api.get_json("/user")
    assert len(opener.calls) == 2


def test_four_default_gates_fit_the_authenticated_hourly_budget():
    nominal_polls = (
        waiter.DEFAULT_DEADLINE_SECONDS // waiter.DEFAULT_POLL_INTERVAL_SECONDS
    ) + 1

    assert nominal_polls + waiter.MAX_SETUP_REQUESTS <= waiter.DEFAULT_MAX_REQUESTS
    assert (
        waiter.DEFAULT_CONCURRENT_GATES * waiter.DEFAULT_MAX_REQUESTS
        + waiter.RATE_LIMIT_RESERVE
        <= waiter.MIN_AUTHENTICATED_RATE_LIMIT
    )
    assert waiter.MIN_STARTING_RATE_REMAINING == (
        waiter.DEFAULT_CONCURRENT_GATES * waiter.DEFAULT_MAX_REQUESTS
        + waiter.RATE_LIMIT_RESERVE
    )


def test_documentation_keeps_bootstrap_non_consuming_and_non_security_critical():
    developer_doc = (
        waiter.REPO_ROOT / "docs/developer/ci-e2e-workflows.md"
    ).read_text()
    agent_doc = (waiter.REPO_ROOT / "AGENTS.md").read_text()
    claude_doc = (waiter.REPO_ROOT / "CLAUDE.md").read_text()

    for document in (developer_doc, agent_doc, claude_doc):
        assert "GH_MATRIX_READ_TOKEN" in document
        assert "non-security evidence" in document
        assert "base-pinned external supervisor" in document
        assert "path@branch" not in document
        assert waiter.WORKFLOW_PATH in document
    assert "must not enable a Gitea consumer" in developer_doc
    assert "--expected-run-id" in developer_doc
    assert "--not-before" in developer_doc
    assert "exactly one accessible" in developer_doc


def test_bootstrap_does_not_enable_a_gitea_consumer():
    for workflow in (waiter.REPO_ROOT / ".gitea/workflows").glob("*.yml"):
        source = workflow.read_text()
        assert "wait_for_github_django_matrix" not in source
        assert waiter.TOKEN_ENV not in source
