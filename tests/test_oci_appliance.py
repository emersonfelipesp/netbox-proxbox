"""Contracts for the testing-only OCI appliance."""

from collections.abc import Iterator
from pathlib import Path
import http.client
import io
import re
import sys
import tomllib
import urllib.error

import pytest
import yaml
from packaging.tags import Tag
from packaging.version import Version

from scripts import resolve_oci_versions


ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _workflow_steps() -> dict[str, dict]:
    workflow = yaml.load(
        _read(".github/workflows/oci-appliance.yml"), Loader=yaml.BaseLoader
    )
    return {
        step.get("name", step.get("uses")): step
        for step in workflow["jobs"]["build"]["steps"]
    }


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
    _fake_pypi(
        monkeypatch,
        {
            "1.0.0": [
                {
                    "filename": "example-1.0.0-py3-none-any.whl",
                    "yanked": False,
                    "requires_python": ">=3.12",
                }
            ],
            "1.1.0": [
                {
                    "filename": "example-1.1.0-py3-none-any.whl",
                    "yanked": True,
                    "requires_python": ">=3.12",
                }
            ],
            "1.2.0": [
                {
                    "filename": "example-1.2.0-py3-none-any.whl",
                    "yanked": False,
                    "requires_python": ">=3.15",
                }
            ],
            "2.0.0rc1": [
                {
                    "filename": "example-2.0.0rc1-py3-none-any.whl",
                    "yanked": False,
                    "requires_python": ">=3.12",
                }
            ],
        },
    )

    assert resolve_oci_versions.latest_compatible(
        "example", Version("3.14")
    ) == Version("1.0.0")


def test_resolver_fails_when_no_compatible_stable_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pypi(
        monkeypatch,
        {
            "1.0.0": [
                {
                    "filename": "example-1.0.0-py3-none-any.whl",
                    "yanked": True,
                    "requires_python": ">=3.12",
                }
            ],
            "2.0.0": [
                {
                    "filename": "example-2.0.0-py3-none-any.whl",
                    "yanked": False,
                    "requires_python": ">=3.15",
                }
            ],
        },
    )

    with pytest.raises(RuntimeError, match="no stable example artifact"):
        resolve_oci_versions.latest_compatible("example", Version("3.14"))


def _simple_snapshot(releases: dict) -> dict:
    files = []
    for version, artifacts in releases.items():
        for artifact in artifacts:
            files.append(
                {
                    "filename": f"example-{version}-py3-none-any.whl",
                    "requires-python": artifact.get("requires_python"),
                    "yanked": artifact.get("yanked", False),
                }
            )
    return {"files": files}


def _fake_pypi(
    monkeypatch: pytest.MonkeyPatch,
    *snapshots: dict,
    simple_snapshots: tuple[dict, ...] | None = None,
) -> list[int]:
    calls: list[int] = []
    remaining = list(snapshots)
    simple_remaining = list(
        simple_snapshots
        if simple_snapshots is not None
        else tuple(_simple_snapshot(snapshot) for snapshot in snapshots)
    )

    def metadata(_package: str) -> dict:
        calls.append(1)
        current = remaining[0] if len(remaining) == 1 else remaining.pop(0)
        return {"releases": current}

    def simple_index(_package: str) -> dict:
        return (
            simple_remaining[0]
            if len(simple_remaining) == 1
            else simple_remaining.pop(0)
        )

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    monkeypatch.setattr(resolve_oci_versions, "_simple_index", simple_index)
    return calls


_STABLE_FILE = [
    {
        "filename": "example-1.0.0-py3-none-any.whl",
        "yanked": False,
        "requires_python": ">=3.12",
    }
]


def test_simple_index_requests_normalized_project_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    def urlopen(request, timeout: int) -> io.BytesIO:
        seen["url"] = request.full_url
        seen["accept"] = request.get_header("Accept")
        seen["timeout"] = timeout
        return io.BytesIO(b'{"files": []}')

    monkeypatch.setattr(resolve_oci_versions.urllib.request, "urlopen", urlopen)

    assert resolve_oci_versions._simple_index("NetBox_Proxbox") == {"files": []}
    assert seen == {
        "url": "https://pypi.org/simple/netbox-proxbox/",
        "accept": "application/vnd.pypi.simple.v1+json",
        "timeout": 30,
    }


def test_native_wheel_only_release_is_not_installable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_metadata = {
        "filename": "example-1.0.0-cp313-cp313-win_amd64.whl",
        "requires_python": ">=3.12",
        "yanked": False,
    }
    native_simple = {
        "filename": native_metadata["filename"],
        "requires-python": ">=3.12",
        "yanked": False,
    }
    _fake_pypi(
        monkeypatch,
        {"1.0.0": [native_metadata]},
        simple_snapshots=({"files": [native_simple]},),
    )

    with pytest.raises(
        RuntimeError,
        match="missing from JSON metadata API and simple install index",
    ):
        resolve_oci_versions.exact_compatible(
            "example", Version("1.0.0"), Version("3.14")
        )


@pytest.mark.parametrize("python_tag", ["py313", "py312", "py3", "py310"])
def test_older_minor_pure_python_wheel_is_installable_from_both_indexes(
    monkeypatch: pytest.MonkeyPatch, python_tag: str
) -> None:
    metadata_file = {
        "filename": f"example-1.0.0-{python_tag}-none-any.whl",
        "requires_python": ">=3.10",
        "yanked": False,
    }
    simple_file = {
        "filename": metadata_file["filename"],
        "requires-python": ">=3.10",
        "yanked": False,
    }
    _fake_pypi(
        monkeypatch,
        {"1.0.0": [metadata_file]},
        simple_snapshots=({"files": [simple_file]},),
    )

    assert resolve_oci_versions.exact_compatible(
        "example", Version("1.0.0"), Version("3.14")
    ) == Version("1.0.0")


def test_pure_python_tags_are_computed_once_per_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []
    compatible_tags = resolve_oci_versions.compatible_tags

    def counted_compatible_tags(*args, **kwargs) -> Iterator[Tag]:
        calls.append(kwargs["python_version"])
        return compatible_tags(*args, **kwargs)

    resolve_oci_versions._compatible_pure_python_tags.cache_clear()
    monkeypatch.setattr(
        resolve_oci_versions, "compatible_tags", counted_compatible_tags
    )
    _fake_pypi(monkeypatch, {"1.0.0": _STABLE_FILE})

    assert resolve_oci_versions.exact_compatible(
        "example", Version("1.0.0"), Version("3.14")
    ) == Version("1.0.0")
    assert calls == [(3, 14)]


def test_newer_minor_pure_python_wheel_is_not_installable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_file = {
        "filename": "example-1.0.0-py315-none-any.whl",
        "requires_python": ">=3.12",
        "yanked": False,
    }
    simple_file = {
        "filename": metadata_file["filename"],
        "requires-python": ">=3.12",
        "yanked": False,
    }
    _fake_pypi(
        monkeypatch,
        {"1.0.0": [metadata_file]},
        simple_snapshots=({"files": [simple_file]},),
    )

    with pytest.raises(
        RuntimeError,
        match="missing from JSON metadata API and simple install index",
    ):
        resolve_oci_versions.exact_compatible(
            "example", Version("1.0.0"), Version("3.14")
        )


@pytest.mark.parametrize(
    ("runtime", "wheel", "installable"),
    [
        ("3.14", "example-1.0.0-cp314-none-any.whl", True),
        ("3.13", "example-1.0.0-cp313-none-any.whl", True),
        ("3.14", "example-1.0.0-cp313-none-any.whl", False),
        ("3.13", "example-1.0.0-cp314-none-any.whl", False),
    ],
)
def test_interpreter_specific_pure_python_wheels_follow_the_runtime(
    monkeypatch: pytest.MonkeyPatch, runtime: str, wheel: str, installable: bool
) -> None:
    metadata_file = {"filename": wheel, "requires_python": ">=3.12", "yanked": False}
    simple_file = {"filename": wheel, "requires-python": ">=3.12", "yanked": False}
    _fake_pypi(
        monkeypatch,
        {"1.0.0": [metadata_file]},
        simple_snapshots=({"files": [simple_file]},),
    )

    if installable:
        assert resolve_oci_versions.exact_compatible(
            "example", Version("1.0.0"), Version(runtime)
        ) == Version("1.0.0")
        return
    with pytest.raises(RuntimeError, match="missing from JSON metadata API"):
        resolve_oci_versions.exact_compatible(
            "example", Version("1.0.0"), Version(runtime)
        )


@pytest.mark.parametrize("extension", ["tar.gz", "zip"])
def test_sdist_only_release_is_installable(
    monkeypatch: pytest.MonkeyPatch, extension: str
) -> None:
    metadata_file = {
        "filename": f"example-1.0.0.{extension}",
        "requires_python": ">=3.12",
        "yanked": False,
    }
    simple_file = {
        "filename": metadata_file["filename"],
        "requires-python": ">=3.12",
        "yanked": False,
    }
    _fake_pypi(
        monkeypatch,
        {"1.0.0": [metadata_file]},
        simple_snapshots=({"files": [simple_file]},),
    )

    assert resolve_oci_versions.exact_compatible(
        "example", Version("1.0.0"), Version("3.14")
    ) == Version("1.0.0")


def test_exact_version_waits_until_a_universal_wheel_reaches_both_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_metadata = {
        "filename": "example-1.0.0-cp313-cp313-win_amd64.whl",
        "requires_python": ">=3.12",
        "yanked": False,
    }
    universal_metadata = {
        "filename": "example-1.0.0-py3-none-any.whl",
        "requires_python": ">=3.12",
        "yanked": False,
    }
    native_simple = {
        "filename": native_metadata["filename"],
        "requires-python": ">=3.12",
        "yanked": False,
    }
    universal_simple = {
        "filename": universal_metadata["filename"],
        "requires-python": ">=3.12",
        "yanked": False,
    }
    native_release = {"1.0.0": [native_metadata]}
    universal_release = {"1.0.0": [universal_metadata]}
    calls = _fake_pypi(
        monkeypatch,
        native_release,
        native_release,
        native_release,
        universal_release,
        simple_snapshots=(
            {"files": [native_simple]},
            {"files": [native_simple]},
            {"files": [native_simple]},
            {"files": [universal_simple]},
        ),
    )
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    assert resolve_oci_versions.exact_compatible(
        "example",
        Version("1.0.0"),
        Version("3.14"),
        wait_seconds=90,
        poll_seconds=30,
        sleep=sleep,
        monotonic=lambda: now[0],
    ) == Version("1.0.0")
    assert now[0] == 90
    assert len(calls) == 4


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

    with pytest.raises(
        RuntimeError, match="no installable stable example 0.0.29.post2"
    ):
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

    with pytest.raises(
        RuntimeError, match="no installable stable example 0.0.29.post2"
    ):
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


def test_exact_version_waits_for_the_simple_index_after_json_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = "0.0.29.post3"
    calls = _fake_pypi(
        monkeypatch,
        {version: _STABLE_FILE},
        simple_snapshots=({"files": []},),
    )
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(
        RuntimeError,
        match=r"0\.0\.29\.post3.*missing from simple install index",
    ):
        resolve_oci_versions.exact_compatible(
            "example",
            Version(version),
            Version("3.14"),
            wait_seconds=90,
            poll_seconds=30,
            sleep=sleep,
            monotonic=lambda: now[0],
        )

    assert now[0] == 90
    assert len(calls) == 4


@pytest.mark.parametrize(
    "simple_file",
    [
        {
            "filename": "example-1.0.0-py3-none-any.whl",
            "requires-python": ">=3.12",
            "yanked": "broken artifact",
        },
        {
            "filename": "example-1.0.0-py3-none-any.whl",
            "requires-python": ">=3.15",
            "yanked": False,
        },
    ],
)
def test_exact_version_rejects_yanked_or_incompatible_simple_files(
    monkeypatch: pytest.MonkeyPatch, simple_file: dict
) -> None:
    _fake_pypi(
        monkeypatch,
        {"1.0.0": _STABLE_FILE},
        simple_snapshots=({"files": [simple_file]},),
    )

    with pytest.raises(RuntimeError, match="missing from simple install index"):
        resolve_oci_versions.exact_compatible(
            "example", Version("1.0.0"), Version("3.14")
        )


def test_transient_simple_index_failures_are_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda _package: {"releases": {"1.0.0": _STABLE_FILE}},
    )
    outcomes: list[object] = [
        urllib.error.URLError("simple index unavailable"),
        {"files": [_simple_snapshot({"1.0.0": _STABLE_FILE})["files"][0]]},
    ]

    def simple_index(_package: str) -> dict:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(resolve_oci_versions, "_simple_index", simple_index)
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    assert resolve_oci_versions.exact_compatible(
        "example",
        Version("1.0.0"),
        Version("3.14"),
        wait_seconds=90,
        poll_seconds=30,
        sleep=sleep,
        monotonic=lambda: now[0],
    ) == Version("1.0.0")
    assert now[0] == 30


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


def _compatibility_table(*rows: tuple[str, str]) -> str:
    lines = [
        "| netbox-proxbox | NetBox | Python | proxbox-api | netbox-sdk | proxmox-sdk |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {plugin} | 4.7.0 | >=3.12 | {backend} | v0.0.13 | v0.0.15 |"
        for plugin, backend in rows
    )
    return "\n".join(lines) + "\n"


def _write_compatibility(tmp_path: Path, *rows: tuple[str, str]) -> Path:
    compatibility_file = tmp_path / "COMPATIBILITY.md"
    compatibility_file.write_text(_compatibility_table(*rows), encoding="utf-8")
    return compatibility_file


def test_release_pairing_normalizes_v_prefix(tmp_path: Path) -> None:
    compatibility_file = _write_compatibility(tmp_path, ("v1.0.0", "v2.0.0"))

    assert resolve_oci_versions.paired_backend_version(
        Version("1.0.0"), compatibility_file
    ) == Version("2.0.0")


def test_release_pairing_rejects_duplicate_rows(tmp_path: Path) -> None:
    compatibility_file = _write_compatibility(
        tmp_path,
        ("v1.0.0", "v2.0.0"),
        ("v1.0.0", "v2.0.1"),
    )

    with pytest.raises(
        RuntimeError,
        match=rf"{re.escape(str(compatibility_file))}.*2 duplicate rows.*1\.0\.0",
    ):
        resolve_oci_versions.paired_backend_version(
            Version("1.0.0"), compatibility_file
        )


def test_release_pairing_rejects_malformed_backend_version(tmp_path: Path) -> None:
    compatibility_file = _write_compatibility(tmp_path, ("v1.0.0", "not-a-version"))

    with pytest.raises(
        RuntimeError,
        match=rf"{re.escape(str(compatibility_file))}.*malformed proxbox-api.*1\.0\.0",
    ):
        resolve_oci_versions.paired_backend_version(
            Version("1.0.0"), compatibility_file
        )


def test_release_resolution_rejects_missing_pairing_before_pypi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    compatibility_file = _write_compatibility(tmp_path, ("v1.0.1", "v2.0.0"))
    pypi_calls = []

    def unexpected_pypi_call(package: str) -> dict:
        pypi_calls.append(package)
        return {}

    monkeypatch.setattr(resolve_oci_versions, "_metadata", unexpected_pypi_call)
    monkeypatch.setattr(resolve_oci_versions, "_simple_index", unexpected_pypi_call)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--plugin-version",
            "v1.0.0",
            "--compatibility-file",
            str(compatibility_file),
        ],
    )

    with pytest.raises(
        RuntimeError,
        match=rf"{re.escape(str(compatibility_file))}.*no row.*1\.0\.0",
    ):
        resolve_oci_versions.main()

    assert pypi_calls == []


def test_committed_compatibility_table_pairs_the_current_package_version() -> None:
    source_version = Version(
        tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    )

    with pytest.raises(RuntimeError, match=r"malformed proxbox-api version"):
        resolve_oci_versions.paired_backend_version(
            source_version, ROOT / "COMPATIBILITY.md"
        )


def test_deleting_current_pairing_row_is_rejected(
    tmp_path: Path,
) -> None:
    source_version = Version(
        tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    )
    compatibility = _read("COMPATIBILITY.md")
    prefix = f"| v{source_version} |"
    retained_lines = [
        line for line in compatibility.splitlines() if not line.startswith(prefix)
    ]
    assert len(retained_lines) == len(compatibility.splitlines()) - 1
    compatibility_file = tmp_path / "COMPATIBILITY.md"
    compatibility_file.write_text("\n".join(retained_lines) + "\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError, match=rf"no row.*{re.escape(str(source_version))}"
    ):
        resolve_oci_versions.paired_backend_version(source_version, compatibility_file)


def test_release_resolution_emits_the_paired_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    releases = {
        "netbox-proxbox": {"0.0.29.post6": _STABLE_FILE},
        "proxbox-api": {
            "0.0.27.post4": _STABLE_FILE,
            "99.0.0": _STABLE_FILE,
        },
    }
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda package: {"releases": releases[package]},
    )
    monkeypatch.setattr(
        resolve_oci_versions,
        "_simple_index",
        lambda package: _simple_snapshot(releases[package]),
    )
    destination = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--plugin-version",
            "v0.0.29.post6",
            "--github-output",
            str(destination),
        ],
    )

    assert resolve_oci_versions.main() == 0
    assert destination.read_text(encoding="utf-8").splitlines() == [
        "netbox_proxbox_version=0.0.29.post6",
        "proxbox_api_version=0.0.27.post4",
        "proxbox_api_python=3.13",
    ]


def test_release_resolution_fails_when_paired_backend_is_not_installable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata_releases = {
        "netbox-proxbox": {"0.0.29.post6": _STABLE_FILE},
        "proxbox-api": {"0.0.27.post4": _STABLE_FILE},
    }
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda package: {"releases": metadata_releases[package]},
    )
    monkeypatch.setattr(
        resolve_oci_versions,
        "_simple_index",
        lambda package: (
            _simple_snapshot(metadata_releases[package])
            if package == "netbox-proxbox"
            else {"files": []}
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--plugin-version",
            "v0.0.29.post6",
            "--github-output",
            str(tmp_path / "out"),
        ],
    )

    with pytest.raises(
        RuntimeError,
        match=r"proxbox-api 0\.0\.27\.post4.*simple install index",
    ):
        resolve_oci_versions.main()


def test_non_release_resolution_keeps_newest_compatible_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = {
        "1.0.0": _STABLE_FILE,
        "2.0.0": _STABLE_FILE,
    }
    _fake_pypi(monkeypatch, releases)

    assert resolve_oci_versions.latest_compatible(
        "example", Version("3.14")
    ) == Version("2.0.0")


def test_prerelease_tag_is_never_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pypi(monkeypatch, {"0.0.29rc1": _STABLE_FILE})

    with pytest.raises(RuntimeError):
        resolve_oci_versions.exact_compatible(
            "example",
            resolve_oci_versions.tag_to_version("v0.0.29rc1"),
            Version("3.14"),
        )


def test_release_workflow_installs_the_released_version() -> None:
    steps = _workflow_steps()
    resolve = steps["Resolve current stable packages"]
    verify = steps["Verify the image contains the resolved package versions"]

    assert resolve["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    assert '--plugin-version "$RELEASE_TAG"' in resolve["run"]
    assert "--wait-seconds 18000" in resolve["run"]
    assert (
        verify["env"]["EXPECTED_PLUGIN_VERSION"]
        == "${{ steps.versions.outputs.netbox_proxbox_version }}"
    )
    assert (
        verify["env"]["EXPECTED_BACKEND_VERSION"]
        == "${{ steps.versions.outputs.proxbox_api_version }}"
    )
    assert 'test "$installed_plugin" = "$EXPECTED_PLUGIN_VERSION"' in verify["run"]
    assert 'test "$installed_backend" = "$EXPECTED_BACKEND_VERSION"' in verify["run"]


def test_release_publishes_the_exact_multiarch_image_smoke_tested_by_digest() -> None:
    steps = _workflow_steps()
    build = steps["Build the final release image once"]
    load = steps["Load the amd64 variant of the release image"]
    smoke = steps["Verify the appliance boots"]
    publish = steps["Publish the tested multi-architecture image"]

    assert build["if"] == "github.event_name == 'release'"
    assert build["id"] == "release_image"
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert build["with"]["outputs"] == (
        "type=image,name=${{ env.IMAGE_NAME }},push-by-digest=true,"
        "name-canonical=true,push=true"
    )
    assert load["env"]["BUILT_DIGEST"] == ("${{ steps.release_image.outputs.digest }}")
    assert (
        'docker pull --platform linux/amd64 "$IMAGE_NAME@$BUILT_DIGEST"' in load["run"]
    )
    assert "netbox-proxbox-oci:test" in smoke["run"]
    assert publish["if"] == "github.event_name == 'release'"
    assert publish["env"]["BUILT_DIGEST"] == (
        "${{ steps.release_image.outputs.digest }}"
    )
    assert '"$IMAGE_NAME@$BUILT_DIGEST"' in publish["run"]
    assert 'test "$published_digest" = "$BUILT_DIGEST"' in publish["run"]

    release_builds = [
        step
        for step in steps.values()
        if step.get("uses", "").startswith("docker/build-push-action@")
        and step.get("if") == "github.event_name == 'release'"
    ]
    assert release_builds == [build]


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
    monkeypatch.setattr(
        resolve_oci_versions,
        "_simple_index",
        lambda _package: _simple_snapshot({"0.0.29.post2": _STABLE_FILE}),
    )
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

    def metadata(package: str) -> dict:
        calls[0] += 1
        if calls[0] == 2:
            raise http.client.IncompleteRead(b"", 10)
        version = "1.0.0" if package == "netbox-proxbox" else "2.0.0"
        return {"releases": {version: _STABLE_FILE}}

    monkeypatch.setattr(resolve_oci_versions, "_metadata", metadata)
    monkeypatch.setattr(
        resolve_oci_versions,
        "_simple_index",
        lambda package: _simple_snapshot(
            {"1.0.0" if package == "netbox-proxbox" else "2.0.0": _STABLE_FILE}
        ),
    )
    monkeypatch.setattr(resolve_oci_versions.time, "sleep", lambda _s: None)
    compatibility_file = _write_compatibility(tmp_path, ("v1.0.0", "v2.0.0"))
    destination = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve",
            "--plugin-version",
            "v1.0.0",
            "--compatibility-file",
            str(compatibility_file),
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
    publish = workflow.index("Publish the tested multi-architecture image")
    decide = workflow.index('--check-promotion "$RELEASE_TAG"')
    move = workflow.index("Move the mutable tag to the published image")

    assert publish < decide < move
    assert "steps.promotion.outputs.publish_moving_tag == 'true'" in workflow
    assert ":oci" not in workflow[publish:decide]
