"""Exercise E2E prerequisite refusal and matrix preservation without network I/O."""

from __future__ import annotations

import itertools
import json
import subprocess

import pytest
import yaml

from scripts import e2e_prerequisites as gate

DEFAULTS = {
    "backend_version": "0.0.29",
    "backend_image": "emersonfelipesp/proxbox-api",
    "mock_image": "emersonfelipesp/proxmox-sdk",
    "mock_tag_prefix": "latest",
}
DIGEST = "sha256:" + "a" * 64


def plan(event="schedule", **inputs):
    return gate.build_plan(event, inputs, DEFAULTS)


def metadata(name="netbox-proxbox", version="0.0.31", **artifact):
    return {
        "info": {"name": name, "version": version, "provides_extra": ["pyo3-rust"]},
        "urls": [
            {
                "filename": f"{name.replace('-', '_')}-{version}-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "requires_python": ">=3.12",
                "url": "https://files.pythonhosted.org/packages/test/package.whl",
                "digests": {"sha256": "b" * 64},
                **artifact,
            }
        ],
    }


@pytest.mark.parametrize(
    "event,count,runtimes,services",
    [
        ("schedule", 198, ["python", "pyo3-rust"], ["pve", "pbs", "pdm"]),
        ("workflow_dispatch", 198, ["python", "pyo3-rust"], ["pve", "pbs", "pdm"]),
        ("workflow_call", 198, ["python", "pyo3-rust"], ["pve", "pbs", "pdm"]),
        ("pull_request", 33, ["python"], ["pve"]),
    ],
)
def test_all_supported_default_matrix_rows_remain(event, count, runtimes, services):
    matrix = plan(event)["matrix"]
    expected = set(
        itertools.product(
            ["local", "pypi", "container"],
            gate.NETBOX_IMAGES,
            ["ipv4"],
            runtimes,
            services,
        )
    )
    actual = set(itertools.product(*matrix.values()))
    assert actual == expected
    assert len(actual) == count


@pytest.mark.parametrize("source", ["local", "pypi", "container", "testpypi"])
def test_explicit_selection_retains_every_selected_axis(source):
    selected = plan(
        install_source=source,
        proxbox_api_runtime="pyo3-rust",
        proxmox_service="pbs",
        netbox_image="test/netbox:v4.6.6",
    )
    assert selected["matrix"] == {
        "install_source": [source],
        "netbox_image": ["test/netbox:v4.6.6"],
        "network_stack": ["ipv4"],
        "proxbox_api_runtime": ["pyo3-rust"],
        "proxmox_service": ["pbs"],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("install_source", "unknown"),
        ("proxbox_api_runtime", "rust-ish"),
        ("proxmox_service", "none"),
        ("dependency_mode", "fallback"),
        ("netbox_image", "--help"),
        ("netbox_image", "image\nINJECTED=1"),
    ],
)
def test_invalid_selection_never_becomes_a_different_matrix(field, value):
    with pytest.raises(ValueError):
        plan(**{field: value})


def test_local_only_admission_does_not_require_unselected_packages(monkeypatch):
    monkeypatch.setattr(
        gate,
        "admit_package",
        lambda *args, **kwargs: pytest.fail("Unselected package checked"),
    )
    calls = []
    monkeypatch.setattr(
        gate, "resolve_image", lambda ref: calls.append(ref) or f"{ref}@{DIGEST}"
    )
    result = gate.admit_plan(plan("pull_request", install_source="local"), "0.0.31")
    assert result["plugin_specs"] == {}
    assert result["backend_specs"] == {}
    assert "emersonfelipesp/proxmox-sdk:latest-nginx" in calls
    assert not any("latest-pbs" in ref or "pyo3-rust" in ref for ref in calls)
    assert len(calls) == 15


@pytest.mark.parametrize(
    "source,index,requested",
    [
        ("pypi", "pypi", "0.0.31"),
        ("container", "pypi", ""),
        ("testpypi", "testpypi", "0.0.31"),
    ],
)
def test_package_admission_uses_only_the_selected_index(
    monkeypatch, source, index, requested
):
    calls = []

    def admit(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "version": "0.0.31",
            "spec": "https://test-files.pythonhosted.org/a.whl#sha256=" + "a" * 64,
        }

    monkeypatch.setattr(gate, "admit_package", admit)
    monkeypatch.setattr(gate, "resolve_image", lambda ref: f"{ref}@{DIGEST}")
    result = gate.admit_plan(plan("pull_request", install_source=source), "0.0.31")
    assert calls == [(("netbox-proxbox", requested, index, "3.12"), {})]
    assert result["plugin_versions"] == {source: "0.0.31"}
    assert result["plugin_specs"][source].startswith("https://test-files.")


def test_missing_package_stops_before_images_or_matrix_outputs(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ValueError("Exact release unavailable")

    monkeypatch.setattr(gate, "admit_package", unavailable)
    monkeypatch.setattr(
        gate,
        "resolve_image",
        lambda ref: pytest.fail("Matrix input published after missing package"),
    )
    with pytest.raises(ValueError, match="Exact release unavailable"):
        gate.admit_plan(plan(), "0.0.31")


def test_package_backend_requires_selected_rust_extra_without_image_fallback(
    monkeypatch,
):
    calls = []

    def admit(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "version": "0.0.29",
            "spec": "https://test-files.pythonhosted.org/api.whl#sha256=" + "b" * 64,
        }

    monkeypatch.setattr(gate, "admit_package", admit)
    images = []
    monkeypatch.setattr(
        gate, "resolve_image", lambda ref: images.append(ref) or f"{ref}@{DIGEST}"
    )
    result = gate.admit_plan(
        plan(install_source="local", dependency_mode="testpypi-package"), "0.0.31"
    )
    assert calls == [(("proxbox-api", "0.0.29", "testpypi", "3.13"), {"rust": True})]
    assert result["backend_specs"]["pyo3-rust"].startswith(
        "proxbox-api[pyo3-rust] @ https://test-files."
    )
    assert not any(ref.startswith("emersonfelipesp/proxbox-api:") for ref in images)
    assert "python:3.13-slim" in images


@pytest.mark.parametrize(
    "change",
    [
        {"yanked": True},
        {"requires_python": ">=3.14"},
        {"digests": {}},
        {"url": "https://example.com/package.whl"},
        {"url": "https://files.pythonhosted.org/x;touch"},
    ],
)
def test_unusable_package_artifact_is_refused(monkeypatch, change):
    monkeypatch.setattr(
        gate, "fetch_package_metadata", lambda *args: metadata(**change)
    )
    with pytest.raises(ValueError):
        gate.admit_package("netbox-proxbox", "0.0.31", "pypi", "3.12")


def test_release_admission_binds_artifact_hash(monkeypatch):
    monkeypatch.setattr(gate, "fetch_package_metadata", lambda *args: metadata())
    admitted = gate.admit_package("netbox-proxbox", "0.0.31", "pypi", "3.12")
    assert admitted == {
        "version": "0.0.31",
        "spec": "https://files.pythonhosted.org/packages/test/package.whl#sha256="
        + "b" * 64,
    }


def test_wrong_release_or_missing_extra_is_refused(monkeypatch):
    document = metadata(name="proxbox-api", version="0.0.29")
    document["info"]["provides_extra"] = []
    monkeypatch.setattr(gate, "fetch_package_metadata", lambda *args: document)
    with pytest.raises(ValueError, match="pyo3-rust extra"):
        gate.admit_package("proxbox-api", "0.0.29", "pypi", "3.13", rust=True)
    with pytest.raises(ValueError, match="Wrong package version"):
        gate.admit_package("proxbox-api", "0.0.30", "pypi", "3.13")


def test_image_index_resolution_binds_existing_pin_and_platform(monkeypatch):
    manifest = {
        "digest": DIGEST,
        "manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}],
    }
    monkeypatch.setattr(gate, "run_checked", lambda argv: json.dumps(manifest))
    assert gate.resolve_image("test/image:v1") == f"test/image:v1@{DIGEST}"
    assert gate.resolve_image(f"test/image:v1@{DIGEST}") == f"test/image:v1@{DIGEST}"
    with pytest.raises(ValueError, match="does not match"):
        gate.resolve_image("test/image@sha256:" + "c" * 64)


@pytest.mark.parametrize(
    "manifest",
    [
        {"digest": "bad"},
        {"digest": DIGEST, "manifests": []},
        {
            "digest": DIGEST,
            "manifests": [{"platform": {"os": "linux", "architecture": "arm64"}}],
        },
    ],
)
def test_unavailable_digest_or_platform_is_refused(monkeypatch, manifest):
    monkeypatch.setattr(gate, "run_checked", lambda argv: json.dumps(manifest))
    with pytest.raises(ValueError):
        gate.resolve_image("test/image:v1")


def test_missing_image_propagates_and_does_not_substitute(monkeypatch):
    def unavailable(argv):
        raise subprocess.CalledProcessError(1, argv, stderr="manifest unknown")

    monkeypatch.setattr(gate, "run_checked", unavailable)
    with pytest.raises(subprocess.CalledProcessError):
        gate.resolve_image("test/image:v1")


def test_single_manifest_checks_linux_amd64_configuration(monkeypatch):
    replies = iter([{"digest": DIGEST}, {"os": "linux", "architecture": "amd64"}])
    monkeypatch.setattr(gate, "run_checked", lambda argv: json.dumps(next(replies)))
    assert gate.resolve_image("test/image:v1") == f"test/image:v1@{DIGEST}"


def test_development_backend_is_bound_to_exact_head_without_published_image(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        gate, "run_checked", lambda argv: calls.append(argv) or "d" * 40 + "\tHEAD\n"
    )
    monkeypatch.setattr(gate, "resolve_image", lambda ref: f"{ref}@{DIGEST}")
    result = gate.admit_plan(
        plan("pull_request", install_source="local", dependency_mode="dev"), "0.0.31"
    )
    assert result["backend_sha"] == "d" * 40
    assert calls == [["git", "ls-remote", gate.BACKEND_REPOSITORY, "HEAD"]]
    assert not any(key.startswith("api_") for key in result["images"])


def test_workflow_waits_for_shared_admission_and_uses_bound_inputs():
    from pathlib import Path

    workflow = yaml.load(
        Path(".github/workflows/e2e-docker.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    matrix = jobs["e2e-docker-stack"]
    assert matrix["needs"] == "prerequisites"
    assert (
        matrix["strategy"]["matrix"]
        == "${{ fromJSON(needs.prerequisites.outputs.matrix) }}"
    )
    assert "plugin_specs" in jobs["prerequisites"]["outputs"]
    source = Path(".github/workflows/e2e-docker.yml").read_text()
    assert "Falling back" not in source
    assert "unsafe-best-match" not in source
    assert '"${PROXBOX_API_IMAGE_REF}"' in source
    assert '"${ADMITTED_PLUGIN_SPEC}"' not in source  # transported through GITHUB_ENV
    assert "NETBOX_PLUGIN_INSTALL_SPEC=${ADMITTED_PLUGIN_SPEC}" in source
    assert '--required "${required[@]}" --timeout 1200' in source


def test_selected_testpypi_artifact_cannot_use_the_pypi_file_host(monkeypatch):
    monkeypatch.setattr(gate, "fetch_package_metadata", lambda *args: metadata())
    with pytest.raises(ValueError, match="selected public index"):
        gate.admit_package("netbox-proxbox", "0.0.31", "testpypi", "3.12")


def test_selected_testpypi_artifact_preserves_its_index_and_hash(monkeypatch):
    document = metadata(
        url="https://test-files.pythonhosted.org/packages/test/package.whl"
    )
    monkeypatch.setattr(gate, "fetch_package_metadata", lambda *args: document)
    result = gate.admit_package("netbox-proxbox", "0.0.31", "testpypi", "3.12")
    assert (
        result["spec"]
        == "https://test-files.pythonhosted.org/packages/test/package.whl#sha256="
        + "b" * 64
    )


def test_source_archive_is_retained_when_release_has_no_universal_wheel(monkeypatch):
    document = metadata(
        filename="netbox_proxbox-0.0.31.tar.gz",
        packagetype="sdist",
        url="https://files.pythonhosted.org/packages/test/netbox_proxbox-0.0.31.tar.gz",
    )
    monkeypatch.setattr(gate, "fetch_package_metadata", lambda *args: document)
    result = gate.admit_package("netbox-proxbox", "0.0.31", "pypi", "3.12")
    assert result["spec"].endswith(".tar.gz#sha256=" + "b" * 64)


@pytest.mark.parametrize(
    "response", ["", "not-a-sha\tHEAD", "d" * 40 + "\trefs/heads/other"]
)
def test_development_identity_never_falls_back_on_missing_or_invalid_source(
    monkeypatch, response
):
    monkeypatch.setattr(gate, "run_checked", lambda argv: response)
    with pytest.raises(ValueError, match="exact source identity"):
        gate.development_source("dev")


def test_missing_image_cannot_publish_matrix_outputs(monkeypatch, tmp_path):
    monkeypatch.setenv("E2E_INPUTS", json.dumps({"install_source": "local"}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PROXBOX_API_RELEASE_VERSION", "0.0.29")
    monkeypatch.setenv("PROXBOX_API_IMAGE", "emersonfelipesp/proxbox-api")
    monkeypatch.setenv("PROXMOX_SDK_IMAGE", "emersonfelipesp/proxmox-sdk")
    monkeypatch.setenv("PROXMOX_SDK_TAG_PREFIX", "latest")
    output = tmp_path / "output"
    output.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def unavailable(reference):
        raise ValueError("manifest unknown")

    monkeypatch.setattr(gate, "resolve_image", unavailable)
    with pytest.raises(ValueError, match="manifest unknown"):
        gate.main()
    assert output.read_text() == ""


def test_success_publishes_all_admitted_inputs_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("E2E_INPUTS", "null")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    for name, value in {
        "PROXBOX_API_RELEASE_VERSION": "0.0.29",
        "PROXBOX_API_IMAGE": "test/api",
        "PROXMOX_SDK_IMAGE": "test/mock",
        "PROXMOX_SDK_TAG_PREFIX": "latest",
    }.items():
        monkeypatch.setenv(name, value)
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    admitted = {
        "matrix": {"install_source": ["local"]},
        "images": {"postgres": "postgres@" + DIGEST},
        "backend_sha": "",
    }
    seen = []
    monkeypatch.setattr(
        gate,
        "admit_plan",
        lambda resolved, version: seen.append((resolved, version)) or admitted,
    )
    assert gate.main() == 0
    captured = {
        line.split("=", 1)[0]: json.loads(line.split("=", 1)[1])
        for line in output.read_text().splitlines()
    }
    assert captured == admitted
    assert len(seen[0][0]["matrix"]["netbox_image"]) == 11


def test_prerequisite_commands_are_bounded_and_report_registry_diagnostics(monkeypatch):
    observed = []

    def run(argv, **kwargs):
        observed.append((argv, kwargs))
        raise subprocess.CalledProcessError(1, argv, stderr="manifest unknown")

    monkeypatch.setattr(gate.subprocess, "run", run)
    with pytest.raises(ValueError, match="manifest unknown"):
        gate.run_checked(["docker", "buildx", "imagetools", "inspect", "test/image:v1"])
    assert observed[0][1] == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 90,
    }


def test_package_metadata_is_bound_to_exact_selected_endpoint(monkeypatch):
    from io import BytesIO

    calls = []

    def open_url(url, **kwargs):
        calls.append((url, kwargs))
        return BytesIO(json.dumps(metadata()).encode())

    monkeypatch.setattr(gate.urllib.request, "urlopen", open_url)
    assert (
        gate.fetch_package_metadata("netbox-proxbox", "0.0.31", "testpypi")["info"][
            "version"
        ]
        == "0.0.31"
    )
    assert calls == [
        ("https://test.pypi.org/pypi/netbox-proxbox/0.0.31/json", {"timeout": 20})
    ]


def test_package_metadata_response_limit_fails_closed(monkeypatch):
    from io import BytesIO

    monkeypatch.setattr(
        gate.urllib.request,
        "urlopen",
        lambda *args, **kwargs: BytesIO(b" " * (2 * 1024 * 1024 + 1)),
    )
    with pytest.raises(ValueError, match="response limit"):
        gate.fetch_package_metadata("netbox-proxbox", "", "pypi")


def test_wrong_package_identity_is_not_admitted(monkeypatch):
    monkeypatch.setattr(
        gate, "fetch_package_metadata", lambda *args: metadata(name="another-project")
    )
    with pytest.raises(ValueError, match="Wrong package identity"):
        gate.admit_package("netbox-proxbox", "0.0.31", "pypi", "3.12")


def test_moving_single_manifest_tag_cannot_verify_another_digests_platform(monkeypatch):
    captured_digest = "sha256:" + "a" * 64
    commands = []

    def inspect(argv):
        commands.append(argv)
        if argv[-1] == "{{json .Manifest}}":
            return json.dumps({"digest": captured_digest})
        architecture = "arm64" if "@" in argv[4] else "amd64"
        return json.dumps({"os": "linux", "architecture": architecture})

    monkeypatch.setattr(gate, "run_checked", inspect)
    with pytest.raises(ValueError, match="linux/amd64"):
        gate.resolve_image("test/image:moving")
    assert commands[1][4] == f"test/image:moving@{captured_digest}"


def test_single_manifest_success_uses_one_immutable_identity(monkeypatch):
    commands = []

    def inspect(argv):
        commands.append(argv)
        if argv[-1] == "{{json .Manifest}}":
            return json.dumps({"digest": DIGEST})
        assert argv[4] == f"test/image:moving@{DIGEST}"
        return json.dumps({"os": "linux", "architecture": "amd64"})

    monkeypatch.setattr(gate, "run_checked", inspect)
    assert gate.resolve_image("test/image:moving") == f"test/image:moving@{DIGEST}"
    assert commands[0][4] == "test/image:moving"
    assert commands[1][4] == f"test/image:moving@{DIGEST}"


def test_missing_selected_package_identifies_request_on_stderr_without_outputs(
    monkeypatch, tmp_path, capsys
):
    import runpy
    import urllib.error
    from pathlib import Path

    script = Path(gate.__file__)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    monkeypatch.setenv("E2E_INPUTS", json.dumps({"install_source": "testpypi"}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    for name, value in {
        "PROXBOX_API_RELEASE_VERSION": "0.0.29",
        "PROXBOX_API_IMAGE": "test/api",
        "PROXMOX_SDK_IMAGE": "test/mock",
        "PROXMOX_SDK_TAG_PREFIX": "latest",
    }.items():
        monkeypatch.setenv(name, value)
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def unavailable(url, **kwargs):
        assert url == "https://test.pypi.org/pypi/netbox-proxbox/1.2.3/json"
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(gate.urllib.request, "urlopen", unavailable)
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(script), run_name="__main__")
    assert result.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "netbox-proxbox==1.2.3" in captured.err
    assert "on testpypi" in captured.err
    assert "404" in captured.err
    assert not output.exists()


def test_latest_selection_and_bounded_transport_reason_are_diagnostic_only(
    monkeypatch, capsys
):
    import urllib.error

    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("reason\n" + "x" * 500)

    monkeypatch.setattr(gate.urllib.request, "urlopen", unavailable)
    with pytest.raises(ValueError, match="netbox-proxbox==latest on pypi") as result:
        gate.fetch_package_metadata("netbox-proxbox", "", "pypi")
    assert len(str(result.value)) < 400
    assert "\n" not in str(result.value)
    assert capsys.readouterr().out == ""
