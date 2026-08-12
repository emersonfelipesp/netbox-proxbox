"""Static contracts for the staged package-first release workflow."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GITEA_PUBLISH_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "publish-gitea.yml"
GITEA_ARTIFACT_WORKFLOW = (
    REPO_ROOT / ".gitea" / "workflows" / "artifact-v3-compatibility.yml"
)
GITHUB_PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-testpypi.yml"
GITEA_DEPLOY_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "deploy-production.yml"
GITEA_PROMOTE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "promote-final-tag.yml"
RELEASE_ARTIFACTS_PATH = REPO_ROOT / "scripts" / "release_artifacts.py"
CI_GATE_PATH = REPO_ROOT / "scripts" / "gitea_ci_gate.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load_release_artifacts():
    spec = importlib.util.spec_from_file_location(
        "release_artifacts", RELEASE_ARTIFACTS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_ci_gate():
    spec = importlib.util.spec_from_file_location("gitea_ci_gate", CI_GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gitea_publish_promotes_only_rc_tags_to_github() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)

    assert "needs.validate-source.outputs.is_rc == 'true'" in workflow
    assert "gh release create" not in workflow
    assert "Create GitHub Release" not in workflow
    assert "refs/heads/develop:refs/remotes/gitea/release-develop" in workflow
    assert "release-manifest.json" in workflow
    assert "fetch-gitea" in workflow
    assert "scripts/release_artifacts.py release-transfer/" in workflow
    assert "release-transfer/release_artifacts.py" in workflow
    assert "/-/link/netbox-proxbox" in workflow
    assert "publish-manifest" in workflow
    assert "scripts/gitea_ci_gate.py" in workflow
    assert "/commits/${SOURCE_SHA}/statuses" not in workflow
    assert (
        "actions/upload-artifact@c6a3b2bd78b3985e4b2f15397fec357f0fd808de" in workflow
    )
    assert (
        "actions/download-artifact@ad191675b41f6a5b46da9a048cb6893812da158b" in workflow
    )
    parsed = yaml.safe_load(workflow)
    assert all(
        job["runs-on"] == "ci-untrusted-python312" for job in parsed["jobs"].values()
    )
    assert parsed["jobs"]["publish-gitea"]["permissions"] == {
        "contents": "read",
        "packages": "read",
    }
    assert "astral-sh/setup-uv@" not in workflow
    assert "RUNNER_TOOL_CACHE" not in workflow
    assert "UV_MANAGED_PYTHON" not in workflow
    assert "mirror-host" not in workflow
    assert "packages: write" not in workflow
    assert (
        workflow.count(
            "https://github.com/astral-sh/uv/releases/download/0.11.28/"
            "uv-x86_64-unknown-linux-gnu.tar.gz"
        )
        == 2
    )
    assert (
        workflow.count(
            "e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224"
        )
        == 2
    )
    assert workflow.count("sha256sum --check --strict") == 2
    assert workflow.count("UV_PYTHON_INSTALL_DIR=%s") == 2
    assert workflow.count("while IFS='=' read -r VARIABLE _; do") == 4
    assert workflow.count('case "$VARIABLE" in UV_*) unset "$VARIABLE" ;; esac') == 4
    assert workflow.count("--no-config") == 4
    assert workflow.count("--managed-python") == 4
    assert workflow.count("--no-python-downloads") == 2
    assert workflow.count('"$MANAGED_PYTHON_ROOT"/*) ;;') == 2
    assert "GITEA_TOKEN: ${{ secrets.PKG_TOKEN }}" in workflow
    assert "GITEA_TOKEN: ${{ github.token }}" not in workflow
    assert "Fetch validated publisher tool anonymously" in workflow
    assert '"$PUBLISHER_UV" sync' in workflow
    assert '"$PUBLISHER_PYTHON" -m twine upload' in workflow
    assert '"$BUILD_ROOT/venv/bin/python" -m build --no-isolation' in workflow
    assert "uvx --from twine" not in workflow


def test_gitea_artifact_v3_compatibility_probe_is_bounded_and_disposable() -> None:
    workflow = _read(GITEA_ARTIFACT_WORKFLOW)
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)

    assert parsed["on"] == {"pull_request": "", "workflow_dispatch": ""}
    assert parsed["permissions"] == {"contents": "read"}
    assert set(parsed["jobs"]) == {"upload-probe", "download-probe"}
    assert all(
        job["runs-on"] == "ci-untrusted-python312" for job in parsed["jobs"].values()
    )
    assert parsed["jobs"]["download-probe"]["needs"] == "upload-probe"
    assert (
        workflow.count(
            "9b8fb938761ebbe4a50970b582dc793275d113da31ea12bcb55e50bec71c3d14"
        )
        == 2
    )
    assert (
        "actions/upload-artifact@c6a3b2bd78b3985e4b2f15397fec357f0fd808de" in workflow
    )
    assert (
        "actions/download-artifact@ad191675b41f6a5b46da9a048cb6893812da158b" in workflow
    )
    assert "mirror-host" not in workflow


def test_gitea_publish_does_not_bypass_nms_production_deployment() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)

    assert "Deploy to production" not in workflow
    assert "deploy-netbox-plugin" not in workflow
    assert "nmc-prod-207" not in workflow


def test_github_publish_accepts_rc_pushes_and_final_release_events_only() -> None:
    workflow = _read(GITHUB_PUBLISH_WORKFLOW)

    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    dispatch_inputs = parsed["on"]["workflow_dispatch"]["inputs"]

    assert '- "v*rc*"' in workflow
    assert "Published release events must use a final version" in workflow
    assert "Unsupported release event/ref combination" in workflow
    assert "publish_target = 'testpypi'" in workflow
    assert "publish_target = 'pypi'" in workflow
    dispatch_block = workflow.split("workflow_dispatch:", 1)[1].split(
        "permissions:", 1
    )[0]
    assert "- testpypi" in dispatch_block
    assert "- pypi" not in dispatch_block
    assert "Manual dispatch is TestPyPI-only and requires an RC version" in workflow
    assert set(dispatch_inputs) == {
        "publish_target",
        "source_ref",
        "expected_version",
        "proxbox_api_version",
    }
    assert dispatch_inputs["source_ref"]["type"] == "string"


def test_repository_deploy_workflow_is_nms_source_aware() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    assert "deploy_source:" in workflow
    assert "default: latest_package" in workflow
    assert "- latest_package" in workflow
    assert "- main_branch" in workflow
    assert "package_version:" in workflow
    assert "deploy-netbox-plugin-staging" in workflow
    assert "deploy-netbox-plugin-package netbox-proxbox" in workflow
    assert "deploy-netbox-plugin netbox-proxbox" in workflow
    assert "create-attestation" in workflow
    assert "publish-attestation" in workflow


def test_final_tag_promotion_requires_main_package_and_nms_evidence() -> None:
    workflow = _read(GITEA_PROMOTE_WORKFLOW)

    assert "github.ref == 'refs/heads/main'" in workflow
    assert "refs/remotes/gitea/release-main" in workflow
    assert "refs/remotes/gitea/release-develop" in workflow
    assert "scripts/release_artifacts.py fetch-gitea" in workflow
    assert "scripts/release_artifacts.py fetch-attestation" in workflow
    assert "https://github.com/emersonfelipesp/netbox-proxbox.git" in workflow
    assert "GH_TOKEN: ${{ secrets.GH_MIRROR_TOKEN }}" in workflow
    assert workflow.index("fetch-attestation") < workflow.index("GH_TOKEN:")
    assert "gh release create" not in workflow
    assert (
        "rc[0-9]" not in workflow.split('python3 - "$VERSION"', 1)[1].split("PY", 1)[0]
    )


def test_release_uploads_never_reuse_consumed_package_versions() -> None:
    github_workflow = _read(GITHUB_PUBLISH_WORKFLOW)
    assert "--skip-existing" not in github_workflow
    assert "already_on_pypi" not in github_workflow
    assert "--skip-existing" not in _read(GITEA_PUBLISH_WORKFLOW)


def test_github_promotion_uses_exact_gitea_artifacts_and_nms_evidence() -> None:
    workflow = _read(GITHUB_PUBLISH_WORKFLOW)

    assert "scripts/release_artifacts.py fetch-gitea" in workflow
    assert "scripts/release_artifacts.py fetch-attestation" in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "Build distribution" not in workflow
    assert "validate-gitea-artifacts:" in workflow
    assert "kind: [wheel, sdist]" in workflow


def test_public_publish_workflow_uses_immutable_locked_tooling() -> None:
    workflow = _read(GITHUB_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)
    project = tomllib.loads(_read(PYPROJECT_PATH))

    expected_actions = {
        "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    }
    for job in parsed["jobs"].values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []):
            action = step.get("uses") if isinstance(step, dict) else None
            if isinstance(action, str) and not action.startswith("./"):
                assert action in expected_actions
                assert len(action.rsplit("@", 1)[1]) == 40
            if isinstance(action, str) and action.startswith("astral-sh/setup-uv@"):
                assert step.get("with", {}).get("version") == "0.11.28"

    assert project["dependency-groups"]["publish"] == [
        "build==1.5.0",
        "packaging==26.0",
        "setuptools==80.9.0",
        "twine==6.2.0",
        "wheel==0.45.1",
    ]
    assert workflow.count("uv sync --only-group publish --locked") == 3
    assert "uv run --with twine python -m twine upload" not in workflow
    assert workflow.count(".venv/bin/python -m twine upload") == 2


def test_release_manifest_binds_exact_artifact_bytes(tmp_path: Path) -> None:
    release_artifacts = _load_release_artifacts()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "netbox_proxbox-0.0.24-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "netbox_proxbox-0.0.24.tar.gz").write_bytes(b"sdist")
    manifest_path = tmp_path / "release-manifest.json"
    sha = "a" * 40

    manifest = release_artifacts.write_manifest(
        dist=dist,
        package="netbox-proxbox",
        version="0.0.24",
        source_sha=sha,
        output=manifest_path,
    )
    assert (
        release_artifacts.verify_manifest(
            manifest_path=manifest_path,
            dist=dist,
            package="netbox-proxbox",
            version="0.0.24",
            source_sha=sha,
        )
        == manifest
    )

    (dist / "netbox_proxbox-0.0.24.tar.gz").write_bytes(b"changed")
    with pytest.raises(release_artifacts.ReleaseArtifactError):
        release_artifacts.verify_manifest(
            manifest_path=manifest_path,
            dist=dist,
            package="netbox-proxbox",
            version="0.0.24",
            source_sha=sha,
        )


def test_ci_gate_binds_status_to_authenticated_run_and_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_ci_gate()
    sha = "a" * 40
    context = "CI / Static checks and mocked regressions (push)"
    responses = {
        f"/repos/emersonfelipesp/netbox-proxbox/commits/{sha}/statuses?limit=100": [
            {
                "id": 8,
                "context": context,
                "status": "success",
                "target_url": "/emersonfelipesp/netbox-proxbox/actions/runs/12/jobs/34",
            }
        ],
        "/repos/emersonfelipesp/netbox-proxbox/actions/runs/12": {
            "id": 12,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_sha": sha,
            "head_branch": "develop",
            "path": "ci.yml@refs/heads/develop",
            "actor": {"login": "emersonfelipesp"},
        },
        "/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34": {
            "id": 34,
            "run_id": 12,
            "name": "Static checks and mocked regressions",
            "status": "completed",
            "conclusion": "success",
            "head_sha": sha,
            "runner_name": "ci-untrusted-netbox-proxbox",
            "labels": ["ci-untrusted-python312"],
            "html_url": "https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox/actions/runs/12/jobs/34",
        },
    }
    monkeypatch.setattr(gate, "_request_json", lambda path, *, token: responses[path])

    evidence = gate.validate_ci_gate(
        owner="emersonfelipesp",
        repository="netbox-proxbox",
        source_sha=sha,
        required_contexts=[context],
        trusted_actor="emersonfelipesp",
        token="test-token",
    )
    assert evidence == {context: {"job_id": 34, "run_id": 12}}

    responses["/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34"]["head_sha"] = (
        "b" * 40
    )
    with pytest.raises(gate.CIGateError, match="job does not match"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )


def test_registry_fetch_rejects_rebinding_original_artifacts_to_moved_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_artifacts = _load_release_artifacts()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "netbox_proxbox-0.0.24-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "netbox_proxbox-0.0.24.tar.gz").write_bytes(b"sdist")
    original = release_artifacts.create_manifest(
        dist=dist,
        package="netbox-proxbox",
        version="0.0.24",
        source_sha="a" * 40,
    )
    monkeypatch.setattr(
        release_artifacts,
        "fetch_gitea_manifest",
        lambda **_kwargs: original,
    )

    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="does not match the protected tag",
    ):
        release_artifacts.fetch_gitea_artifacts(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.24",
            source_sha="b" * 40,
            dist=tmp_path / "download",
        )


def test_final_release_requires_exact_nms_promotion_evidence(tmp_path: Path) -> None:
    release_artifacts = _load_release_artifacts()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "netbox_proxbox-0.0.24-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "netbox_proxbox-0.0.24.tar.gz").write_bytes(b"sdist")
    manifest = release_artifacts.create_manifest(
        dist=dist,
        package="netbox-proxbox",
        version="0.0.24",
        source_sha="b" * 40,
    )
    evidence = release_artifacts.create_deployment_attestation(
        manifest=manifest,
        repository="emersonfelipesp/netbox-proxbox",
        run_id=123,
    )
    assert (
        release_artifacts.validate_release_attestation(
            evidence=evidence,
            manifest=manifest,
            repository="emersonfelipesp/netbox-proxbox",
        )
        == evidence
    )

    evidence["deploy_source"] = "main_branch"
    with pytest.raises(release_artifacts.ReleaseArtifactError):
        release_artifacts.validate_release_attestation(
            evidence=evidence,
            manifest=manifest,
            repository="emersonfelipesp/netbox-proxbox",
        )
