"""Contracts for the testing-only OCI appliance."""

from pathlib import Path
import http.client
import re
import sys
import urllib.error

import pytest
from packaging.version import Version

from scripts import resolve_oci_versions


ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_image_has_proxmox_lxc_init_and_health_contract() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert "RUN ln -s /usr/local/sbin/proxbox-stack-init /sbin/init" in dockerfile
    assert "EXPOSE 8080 8800" in dockerfile
    assert 'CMD ["/usr/local/sbin/proxbox-stack-healthcheck"]' in dockerfile


def test_image_installs_exact_resolved_releases() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert '"netbox-proxbox==${NETBOX_PROXBOX_VERSION}"' in dockerfile
    assert '"proxbox-api==${PROXBOX_API_VERSION}"' in dockerfile
    assert "PROXBOX_API_PYTHON=3.13" in dockerfile


def test_stateful_services_use_declared_volumes() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert "PROXBOX_DATABASE_PATH=/var/lib/proxbox-api/database.db" in dockerfile
    assert 'VOLUME ["/var/lib/postgresql", "/var/lib/redis", ' in dockerfile
    assert '"/var/lib/proxbox-api", "/var/lib/proxbox-stack"]' in dockerfile


def test_plugin_is_enabled_and_targets_embedded_backend() -> None:
    configuration = _read("oci/netbox-configuration.py")
    backend = _read("oci/bin/proxbox-stack-backend")

    assert 'PLUGINS = ["netbox_proxbox"]' in configuration
    assert '"backend_url": "http://127.0.0.1:8800"' in configuration
    assert 'API_TOKEN_PEPPERS = {1: _secret("api-token-pepper"' in configuration
    assert "${PROXBOX_BIND_HOST:-127.0.0.1}" in backend


def test_release_workflow_pins_third_party_actions() -> None:
    workflow = _read(".github/workflows/oci-appliance.yml")
    action_references = re.findall(r"uses: ([^\s]+)@([^\s]+)", workflow)

    assert action_references
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", revision) for _, revision in action_references
    )
    assert "oci-appliance-publication" in workflow
    assert "cancel-in-progress: false" in workflow


def test_resolver_skips_prerelease_yanked_and_incompatible_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda _package: {
            "releases": {
                "1.0.0": [{"yanked": False, "requires_python": ">=3.12"}],
                "1.1.0": [{"yanked": True, "requires_python": ">=3.12"}],
                "1.2.0": [{"yanked": False, "requires_python": ">=3.15"}],
                "2.0.0rc1": [{"yanked": False, "requires_python": ">=3.12"}],
            }
        },
    )

    assert resolve_oci_versions.latest_compatible(
        "example", Version("3.14")
    ) == Version("1.0.0")


def test_resolver_fails_when_no_compatible_stable_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda _package: {
            "releases": {
                "1.0.0": [{"yanked": True, "requires_python": ">=3.12"}],
                "2.0.0": [{"yanked": False, "requires_python": ">=3.15"}],
            }
        },
    )

    with pytest.raises(RuntimeError, match="no stable example artifact"):
        resolve_oci_versions.latest_compatible("example", Version("3.14"))


def _fake_pypi(monkeypatch: pytest.MonkeyPatch, *snapshots: dict) -> list[int]:
    calls: list[int] = []
    remaining = list(snapshots)

    def metadata(_package: str) -> dict:
        calls.append(1)
        current = remaining[0] if len(remaining) == 1 else remaining.pop(0)
        return {"releases": current}

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    return calls


_STABLE_FILE = [{"yanked": False, "requires_python": ">=3.12"}]


def test_exact_version_is_returned_when_pypi_serves_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pypi(
        monkeypatch,
        {"0.0.29.post1": _STABLE_FILE, "0.0.29.post2": _STABLE_FILE},
    )

    assert resolve_oci_versions.exact_compatible(
        "example", Version("0.0.29.post1"), Version("3.14")
    ) == Version("0.0.29.post1")


def test_exact_version_fails_when_absent_and_no_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pypi(monkeypatch, {"0.0.29.post1": _STABLE_FILE})

    with pytest.raises(RuntimeError, match="no stable example 0.0.29.post2"):
        resolve_oci_versions.exact_compatible(
            "example", Version("0.0.29.post2"), Version("3.14")
        )


def test_exact_version_rejects_yanked_and_incompatible_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pypi(
        monkeypatch,
        {
            "1.0.0": [{"yanked": True, "requires_python": ">=3.12"}],
            "1.1.0": [{"yanked": False, "requires_python": ">=3.15"}],
        },
    )

    for wanted in ("1.0.0", "1.1.0"):
        with pytest.raises(RuntimeError):
            resolve_oci_versions.exact_compatible(
                "example", Version(wanted), Version("3.14")
            )


def test_exact_version_waits_for_pypi_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_pypi(
        monkeypatch,
        {"0.0.29.post1": _STABLE_FILE},
        {"0.0.29.post1": _STABLE_FILE},
        {"0.0.29.post1": _STABLE_FILE, "0.0.29.post2": _STABLE_FILE},
    )
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    result = resolve_oci_versions.exact_compatible(
        "example",
        Version("0.0.29.post2"),
        Version("3.14"),
        wait_seconds=600,
        poll_seconds=30,
        sleep=sleep,
        monotonic=lambda: now[0],
    )

    assert result == Version("0.0.29.post2")
    assert slept == [30, 30]
    assert len(calls) == 3


def test_exact_version_times_out_when_pypi_never_serves_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pypi(monkeypatch, {"0.0.29.post1": _STABLE_FILE})
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(RuntimeError, match="no stable example 0.0.29.post2"):
        resolve_oci_versions.exact_compatible(
            "example",
            Version("0.0.29.post2"),
            Version("3.14"),
            wait_seconds=90,
            poll_seconds=30,
            sleep=sleep,
            monotonic=lambda: now[0],
        )

    assert now[0] == 90


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.0.29", "0.0.29"),
        ("v0.0.29.post2", "0.0.29.post2"),
        ("0.0.29.post1", "0.0.29.post1"),
    ],
)
def test_release_tag_maps_to_package_version(tag: str, expected: str) -> None:
    assert resolve_oci_versions.tag_to_version(tag) == Version(expected)


def test_prerelease_tag_is_never_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pypi(monkeypatch, {"0.0.29rc1": _STABLE_FILE})

    with pytest.raises(RuntimeError):
        resolve_oci_versions.exact_compatible(
            "example",
            resolve_oci_versions.tag_to_version("v0.0.29rc1"),
            Version("3.14"),
        )


def test_release_workflow_installs_the_released_version() -> None:
    workflow = _read(".github/workflows/oci-appliance.yml")

    assert "RELEASE_TAG: ${{ github.event.release.tag_name }}" in workflow
    assert '--plugin-version "$RELEASE_TAG"' in workflow
    assert "--wait-seconds" in workflow
    assert "timeout-minutes: 360" in workflow
    assert 'test "$installed" = "$EXPECTED_VERSION"' in workflow


def test_validation_runs_never_share_the_release_publication_group() -> None:
    workflow = _read(".github/workflows/oci-appliance.yml")

    assert "github.event_name == 'release' && 'oci-appliance-publication'" in workflow
    assert "oci-appliance-validation-" in workflow


def test_prerelease_tags_are_refused_before_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_pypi(monkeypatch, {})

    for tag in ("v0.0.29rc1", "v0.0.29.dev1"):
        with pytest.raises(RuntimeError, match="prerelease"):
            resolve_oci_versions.exact_compatible(
                "example",
                resolve_oci_versions.tag_to_version(tag),
                Version("3.14"),
                wait_seconds=18000,
            )

    assert calls == []


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("temporary failure"),
        urllib.error.HTTPError("https://pypi.org", 503, "unavailable", {}, None),
        TimeoutError("timed out"),
    ],
)
def test_transient_pypi_failures_are_retried_until_the_deadline(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    outcomes: list[object] = [failure, failure, {"0.0.29.post2": _STABLE_FILE}]

    def metadata(_package: str) -> dict:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"releases": outcome}

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    assert resolve_oci_versions.exact_compatible(
        "example",
        Version("0.0.29.post2"),
        Version("3.14"),
        wait_seconds=600,
        poll_seconds=30,
        sleep=sleep,
        monotonic=lambda: now[0],
    ) == Version("0.0.29.post2")
    assert now[0] == 60


def test_persistent_pypi_outage_fails_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def metadata(_package: str) -> dict:
        raise urllib.error.URLError("down")

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(RuntimeError, match="unavailable"):
        resolve_oci_versions.exact_compatible(
            "example",
            Version("1.0.0"),
            Version("3.14"),
            wait_seconds=90,
            poll_seconds=30,
            sleep=sleep,
            monotonic=lambda: now[0],
        )

    assert now[0] == 90


def _check_promotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tag: str, metadata
) -> str:
    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    monkeypatch.setattr(resolve_oci_versions.time, "sleep", lambda _s: None)
    destination = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--check-promotion",
            tag,
            "--wait-seconds",
            "600",
            "--github-output",
            str(destination),
        ],
    )
    assert resolve_oci_versions.main() == 0
    return destination.read_text(encoding="utf-8")


def test_older_release_does_not_move_the_mutable_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    releases = {"0.0.29.post1": _STABLE_FILE, "0.0.29.post2": _STABLE_FILE}
    outputs = {}
    for tag in ("v0.0.29.post1", "v0.0.29.post2"):
        directory = tmp_path / tag
        directory.mkdir()
        outputs[tag] = _check_promotion(
            monkeypatch, directory, tag, lambda _p: {"releases": releases}
        )

    assert outputs["v0.0.29.post1"].strip() == "publish_moving_tag=false"
    assert outputs["v0.0.29.post2"].strip() == "publish_moving_tag=true"


@pytest.mark.parametrize(
    "newer_file",
    [
        {"yanked": True, "requires_python": ">=3.12"},
        {"yanked": False, "requires_python": ">=3.15"},
    ],
)
def test_ineligible_newer_release_still_blocks_the_moving_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, newer_file: dict
) -> None:
    releases = {"1.0.0": _STABLE_FILE, "1.1.0": [newer_file]}

    output = _check_promotion(
        monkeypatch, tmp_path, "v1.0.0", lambda _p: {"releases": releases}
    )

    assert output.strip() == "publish_moving_tag=false"


def test_promotion_check_sees_a_release_published_during_the_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = {"1.0.0": _STABLE_FILE}
    after = {"1.0.0": _STABLE_FILE, "1.1.0": _STABLE_FILE}
    state = {"releases": before}

    early = _check_promotion(
        monkeypatch, tmp_path, "v1.0.0", lambda _p: {"releases": state["releases"]}
    )
    state["releases"] = after
    (tmp_path / "late").mkdir()
    late = _check_promotion(
        monkeypatch,
        tmp_path / "late",
        "v1.0.0",
        lambda _p: {"releases": state["releases"]},
    )

    assert early.strip() == "publish_moving_tag=true"
    assert late.strip() == "publish_moving_tag=false"


@pytest.mark.parametrize(
    "failure",
    [
        http.client.IncompleteRead(b"x" * 12, 88),
        http.client.RemoteDisconnected("closed"),
    ],
)
def test_truncated_responses_are_retried_on_every_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    calls = [0]

    def metadata(_package: str) -> dict:
        calls[0] += 1
        if calls[0] == 1:
            raise failure
        return {"releases": {"1.0.0": _STABLE_FILE}}

    output = _check_promotion(monkeypatch, tmp_path, "v1.0.0", metadata)

    assert output.strip() == "publish_moving_tag=true"
    assert calls[0] == 2


def test_main_resolution_retries_transient_failures_on_every_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = [0]

    def metadata(_package: str) -> dict:
        calls[0] += 1
        if calls[0] == 2:
            raise http.client.IncompleteRead(b"", 10)
        return {"releases": {"1.0.0": _STABLE_FILE}}

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    monkeypatch.setattr(resolve_oci_versions.time, "sleep", lambda _s: None)
    destination = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--plugin-version",
            "v1.0.0",
            "--wait-seconds",
            "600",
            "--github-output",
            str(destination),
        ],
    )

    assert resolve_oci_versions.main() == 0
    assert "netbox_proxbox_version=1.0.0" in destination.read_text(encoding="utf-8")
    assert calls[0] == 3


def test_mutable_tag_is_decided_after_the_versioned_image_is_published() -> None:
    workflow = _read(".github/workflows/oci-appliance.yml")
    publish = workflow.index("Publish multi-architecture image")
    decide = workflow.index('--check-promotion "$RELEASE_TAG"')
    move = workflow.index("docker buildx imagetools create")

    assert publish < decide < move
    assert "steps.promotion.outputs.publish_moving_tag == 'true'" in workflow
    assert ":oci" not in workflow[publish:decide]
