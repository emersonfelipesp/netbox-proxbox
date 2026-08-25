"""Static contracts for the staged package-first release workflow."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

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
RUNNER_GATE_PATH = REPO_ROOT / "scripts" / "gitea_release_runner_gate.py"
RUNNER_ACCEPTANCE_PATH = REPO_ROOT / ".gitea" / "release-runner-acceptance.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
RELEASE_CONTROL_DOC_PATHS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "developer" / "release-publishing.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.24.md",
)
CANARY_DOC_PATHS = RELEASE_CONTROL_DOC_PATHS[:3]


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


def _load_runner_gate():
    spec = importlib.util.spec_from_file_location(
        "gitea_release_runner_gate", RUNNER_GATE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return next(
        step for step in steps if isinstance(step, dict) and step.get("name") == name
    )


def test_release_runner_gate_rejects_sentinel_and_wrong_runner(tmp_path: Path) -> None:
    gate = _load_runner_gate()
    with pytest.raises(gate.RunnerGateError, match="not activated"):
        gate.validate_release_runner(
            acceptance_path=RUNNER_ACCEPTANCE_PATH,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            run_id=12,
            job_name="Build exact publisher-credential-free release-control request",
            source_sha="a" * 40,
            token="",
            jobs_payload={"jobs": [], "total_count": 0},
        )

    acceptance = {
        "attestation_public_key_sha256": "",
        "network_attestation_sha256": "b" * 64,
        "registered_labels": [
            "ci-release-netbox-proxbox",
        ],
        "runner_id": 41,
        "runner_label": "ci-release-netbox-proxbox",
        "runner_name": "ci-release-netbox-proxbox-runner",
        "runner_scope_sha256": "e" * 64,
        "runtime_attestation_sha256": "a" * 64,
        "runtime_image_digest": "c" * 64,
        "schema": 1,
        "supervisor_policy_sha256": "d" * 64,
        "validation_runner_id": 42,
        "validation_runner_name": "ci-release-netbox-proxbox-validate",
        "validation_runner_scope_sha256": "f" * 64,
    }
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    subprocess.run(
        [
            "/usr/bin/openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    acceptance["attestation_public_key_sha256"] = hashlib.sha256(
        public_key.read_bytes()
    ).hexdigest()
    assert gate.TRUSTED_EXTERNAL_UID == 0
    with pytest.raises(gate.RunnerGateError, match="metadata is unsafe"):
        gate._open_external_file(
            public_key,
            "attestation public key",
            16384,
            trusted_uid=os.geteuid() + 1,
        )
    public_key.chmod(0o666)
    with pytest.raises(gate.RunnerGateError, match="metadata is unsafe"):
        gate._open_external_file(
            public_key,
            "attestation public key",
            16384,
            trusted_uid=os.geteuid(),
        )
    public_key.chmod(0o644)
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_bytes(gate._canonical_json(acceptance))
    job = {
        "conclusion": None,
        "head_sha": "a" * 40,
        "id": 34,
        "labels": ["ci-release-netbox-proxbox"],
        "name": "Build exact publisher-credential-free release-control request",
        "run_attempt": 1,
        "run_id": 12,
        "runner_id": 41,
        "runner_name": "ci-release-netbox-proxbox-runner",
        "status": "in_progress",
    }
    attestation_root = tmp_path / "attestations"
    attestation_root.mkdir()
    attestation_path = attestation_root / "run-12-job-34.json"
    signature_path = attestation_root / "run-12-job-34.sig"
    attestation = {
        "expires_at": 1200,
        "issued_at": 1000,
        "job_id": 34,
        "network_attestation_sha256": acceptance["network_attestation_sha256"],
        "registered_labels": acceptance["registered_labels"],
        "repository": "emersonfelipesp/netbox-proxbox",
        "run_attempt": 1,
        "run_id": 12,
        "runner_id": 41,
        "runner_name": "ci-release-netbox-proxbox-runner",
        "runner_scope_sha256": acceptance["runner_scope_sha256"],
        "runtime_attestation_sha256": acceptance["runtime_attestation_sha256"],
        "runtime_image_digest": acceptance["runtime_image_digest"],
        "schema": 1,
        "source_sha": "a" * 40,
        "supervisor_policy_sha256": acceptance["supervisor_policy_sha256"],
        "workflow_path": gate.WORKFLOW_RELATIVE_PATH,
        "workflow_sha256": hashlib.sha256(gate.WORKFLOW_PATH.read_bytes()).hexdigest(),
    }

    def sign(value: dict[str, object]) -> None:
        attestation_path.write_bytes(gate._canonical_json(value))
        subprocess.run(
            [
                "/usr/bin/openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(private_key),
                "-out",
                str(signature_path),
                str(attestation_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    sign(attestation)
    assert (
        gate.validate_release_runner(
            acceptance_path=acceptance_path,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            run_id=12,
            job_name=job["name"],
            source_sha="a" * 40,
            token="",
            jobs_payload={"jobs": [job], "total_count": 1},
            attestation_root=attestation_root,
            public_key_path=public_key,
            now=1100,
            trusted_external_uid=os.geteuid(),
        )["runner_id"]
        == 41
    )
    with pytest.raises(gate.RunnerGateError, match="exact accepted"):
        gate.validate_release_runner(
            acceptance_path=acceptance_path,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            run_id=12,
            job_name=job["name"],
            source_sha="a" * 40,
            token="",
            jobs_payload={"jobs": [{**job, "runner_id": 42}], "total_count": 1},
            attestation_root=attestation_root,
            public_key_path=public_key,
            now=1100,
        )
    for label, changed in (
        ("stale", {"issued_at": 800, "expires_at": 1000}),
        ("runtime", {"runtime_image_digest": "e" * 64}),
        ("network", {"network_attestation_sha256": "f" * 64}),
        ("repository-scope", {"runner_scope_sha256": "f" * 64}),
        ("run-attempt", {"run_attempt": 2}),
        ("workflow-path", {"workflow_path": ".gitea/workflows/other.yml"}),
        ("workflow-digest", {"workflow_sha256": "f" * 64}),
        (
            "labels",
            {
                "registered_labels": [
                    *acceptance["registered_labels"],
                    "ci-untrusted-extra",
                ]
            },
        ),
    ):
        sign({**attestation, **changed})
        with pytest.raises(gate.RunnerGateError, match="differs"):
            gate.validate_release_runner(
                acceptance_path=acceptance_path,
                owner="emersonfelipesp",
                repository="netbox-proxbox",
                run_id=12,
                job_name=job["name"],
                source_sha="a" * 40,
                token="",
                jobs_payload={"jobs": [job], "total_count": 1},
                attestation_root=attestation_root,
                public_key_path=public_key,
                now=1100,
                trusted_external_uid=os.geteuid(),
            )


def test_release_jobs_require_distinct_job_bound_ephemeral_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _load_runner_gate()
    acceptance = {
        "attestation_public_key_sha256": "a" * 64,
        "network_attestation_sha256": "b" * 64,
        "registered_labels": ["ci-release-netbox-proxbox"],
        "runner_id": 41,
        "runner_label": "ci-release-netbox-proxbox",
        "runner_name": "ci-release-netbox-proxbox-build",
        "runner_scope_sha256": "c" * 64,
        "runtime_attestation_sha256": "d" * 64,
        "runtime_image_digest": "e" * 64,
        "schema": 1,
        "supervisor_policy_sha256": "f" * 64,
        "validation_runner_id": 42,
        "validation_runner_name": "ci-release-netbox-proxbox-validate",
        "validation_runner_scope_sha256": "a" * 64,
    }
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_bytes(gate._canonical_json(acceptance))
    observed_scopes: list[str] = []

    def verify_attestation(**kwargs: object) -> str:
        observed_scopes.append(str(kwargs["expected_runner_scope_sha256"]))
        return "0" * 64

    monkeypatch.setattr(gate, "_verify_live_attestation", verify_attestation)
    jobs = (
        (
            gate.VALIDATION_JOB_NAME,
            acceptance["validation_runner_id"],
            acceptance["validation_runner_name"],
            acceptance["validation_runner_scope_sha256"],
        ),
        (
            gate.BUILD_JOB_NAMES["netbox-proxbox"],
            acceptance["runner_id"],
            acceptance["runner_name"],
            acceptance["runner_scope_sha256"],
        ),
    )
    for index, (job_name, runner_id, runner_name, runner_scope) in enumerate(
        jobs, start=1
    ):
        job = {
            "conclusion": None,
            "head_sha": "a" * 40,
            "id": 30 + index,
            "labels": [acceptance["runner_label"]],
            "name": job_name,
            "run_attempt": 1,
            "run_id": 12,
            "runner_id": runner_id,
            "runner_name": runner_name,
            "status": "in_progress",
        }
        evidence = gate.validate_release_runner(
            acceptance_path=acceptance_path,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            run_id=12,
            job_name=job_name,
            source_sha="a" * 40,
            token="",
            jobs_payload={"jobs": [job], "total_count": 1},
        )
        assert evidence["runner_id"] == runner_id
        assert observed_scopes[-1] == runner_scope
    acceptance["validation_runner_id"] = acceptance["runner_id"]
    acceptance_path.write_bytes(gate._canonical_json(acceptance))
    with pytest.raises(gate.RunnerGateError, match="not activated"):
        gate.validate_release_runner(
            acceptance_path=acceptance_path,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            run_id=12,
            job_name=gate.BUILD_JOB_NAMES["netbox-proxbox"],
            source_sha="a" * 40,
            token="",
            jobs_payload={"jobs": [], "total_count": 0},
        )


def test_authenticated_release_evidence_rejects_ambient_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ci_gate = _load_ci_gate()
    runner_gate = _load_runner_gate()
    for name in tuple(os.environ):
        if name.casefold() in ci_gate.PROXY_ENVIRONMENT_NAMES:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.invalid")
    with pytest.raises(ci_gate.CIGateError, match="ambient proxy"):
        ci_gate._request_json("/repos/owner/repository/actions/runs", token="token")
    with pytest.raises(runner_gate.RunnerGateError, match="ambient proxy"):
        runner_gate._request_jobs("owner", "repository", 1, "token")


@pytest.mark.skipif(os.name != "posix", reason="UID isolation requires POSIX")
def test_dropped_build_uid_cannot_inherit_or_read_parent_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.geteuid() != 0 or not Path("/proc/self/environ").exists():
        pytest.skip("release runner UID boundary requires root with procfs")

    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "parent-only-sentinel")

    def drop_privileges() -> None:
        os.setgroups([])
        os.setgid(65532)
        os.setuid(65532)

    try:
        result = subprocess.run(
            [
                "/bin/sh",
                "-c",
                'test -z "${ACTIONS_RUNTIME_TOKEN:-}" && '
                'test ! -r "/proc/$BOUNDARY_PARENT_PID/environ"',
            ],
            check=False,
            capture_output=True,
            env={
                "BOUNDARY_PARENT_PID": str(os.getpid()),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            },
            preexec_fn=drop_privileges,
            text=True,
        )
    except subprocess.SubprocessError:
        pytest.skip("UID transitions are disabled in this test sandbox")

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(
    sys.platform != "linux" or os.uname().machine != "x86_64",
    reason="release seccomp contract requires x86-64 Linux",
)
@pytest.mark.skipif(
    sys.platform != "linux" or os.uname().machine != "x86_64",
    reason="release seccomp contract requires x86-64 Linux",
)
@pytest.mark.parametrize(
    ("syscall_number", "arguments"),
    [
        (425, "ctypes.c_uint(1), ctypes.c_void_p()"),
        (
            0x40000000 | 41,
            "ctypes.c_int(socket.AF_INET), ctypes.c_int(socket.SOCK_STREAM), ctypes.c_int(0)",
        ),
    ],
)
def _artifact_handoff_code() -> str:
    parsed = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    bind_run = _step(
        parsed["jobs"]["build-request"],
        "Bind exact artifacts into the control request",
    )["run"]
    return bind_run.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


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
    # The production path no longer calls the raw host scripts. Both rejected
    # the workflow's argv after the deploy host was hardened -- two arguments
    # where six are required -- so a deploy could not succeed by that route.
    assert "deploy-netbox-plugin-package" not in workflow
    assert "deploy-netbox-plugin netbox-proxbox" not in workflow
    assert (
        "proxbox-package-deploy deploy-main \\\n"
        "            netbox-proxbox" in workflow
    )


def test_production_deploy_claims_a_signed_nms_authorization() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # nms-backend injects these on every authorized dispatch; a workflow that
    # does not declare them cannot be dispatched through the proof path.
    assert "nms_request_id:" in workflow
    assert "nms_request_sha256:" in workflow
    assert "/git/deployment-proofs/${NMS_REQUEST_ID}/claim" in workflow

    # A re-run keeps GITHUB_RUN_ID and only bumps the attempt, so without this
    # it would present the first attempt's binding as its own.
    assert 'test "${GITHUB_RUN_ATTEMPT:-1}" = "1"' in workflow

    # The endpoint is operator-overridable, and the request id plus digest are
    # the whole capability -- pin the transport before sending them.
    assert "--noproxy '*'" in workflow
    assert "--proto '=http,https'" in workflow
    assert "127\\.0\\.0\\.1|localhost" in workflow


def test_production_deploy_cannot_report_success_without_deploying() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # The health check passes against the NetBox already running, so a job that
    # deployed nothing would otherwise look green. Both guards matter: the
    # source is resolved by a checked command rather than inside `echo`, where
    # a KeyError's exit status would vanish, and a completion marker is
    # asserted before the run may pass.
    assert 'resolved_source="$(python3 - "$proof_path"' in workflow
    assert 'test -n "$resolved_source"' in workflow
    assert 'unsupported deploy source' in workflow
    assert 'echo "DEPLOY_COMPLETED=true"' in workflow
    assert 'test "${DEPLOY_COMPLETED:-}" = "true"' in workflow


def test_claimed_proof_is_destroyed_on_every_exit_path() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # Traps do not survive across step shells, so cleanup cannot live in the
    # deploy step: a signed authorization left in RUNNER_TEMP on a root
    # self-hosted runner is readable by any later root job.
    assert "name: Destroy the claimed proof" in workflow
    assert "if: always()" in workflow
    assert 'rm -rf -- "$proof_root"' in workflow
    assert "create-attestation" not in workflow
    assert "export-package-deploy-receipt" in workflow
    assert "GITEA_PACKAGE_TOKEN: ${{ secrets.PKG_TOKEN }}" in workflow
    assert "GITEA_PACKAGE_TOKEN: ${{ github.token }}" not in workflow
    assert "packages: write" not in workflow
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
    assert 'GIT_ASKPASS="$SECRET_ROOT/askpass"' in workflow
    assert "http.https://github.com/.extraheader" not in workflow
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


def test_github_promotion_publishes_only_the_tagged_source() -> None:
    """Artifacts reaching an index must correspond to the tagged commit.

    Provenance previously came from re-fetching artifacts out of the private
    forge. A GitHub-hosted runner cannot reach it, so that step failed and every
    downstream publish skipped. Provenance now comes from building the
    checked-out tag in place, which is stronger in one respect -- there is no
    second copy of the artifacts that could diverge from the source -- and the
    manifest records what was built.
    """
    workflow = _read(GITHUB_PUBLISH_WORKFLOW)

    # Built from the tag this workflow was triggered by, not fetched.
    assert "Build distributions from the exact tagged source" in workflow
    assert "uv build --sdist --wheel --out-dir dist" in workflow
    assert 'SOURCE_SHA="$(git rev-parse HEAD^{commit})"' in workflow

    # The private forge must not be a runtime dependency of public publishing.
    assert "git.nmulti.cloud" not in workflow, (
        "the public publish workflow must not depend on the private forge; "
        "a GitHub-hosted runner cannot reach it"
    )
    assert "fetch-gitea" not in workflow

    # What was built is recorded, and a version mismatch fails closed.
    assert "release-manifest.json" in workflow
    assert "do not carry version" in workflow

    # Every built distribution is still installed and smoke-tested, both kinds
    # across both supported interpreters.
    assert "validate-gitea-artifacts:" in workflow
    assert "kind: [wheel, sdist]" in workflow
    assert "python-version: ['3.12', '3.13']" in workflow


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
        "hatchling==1.31.0",
        "packaging==26.0",
        "setuptools==80.9.0",
        "twine==6.2.0",
        "wheel==0.45.1",
    ]
    assert workflow.count("uv sync --only-group publish --locked") == 3
    assert "uv run --with twine python -m twine upload" not in workflow
    assert workflow.count(".venv/bin/python -m twine upload") == 2
    assert workflow.count("TWINE_PASSWORD: ${{ secrets.") == 2
    assert workflow.count("TWINE_USERNAME: ${{ secrets.") == 2
    assert "--password" not in workflow
    assert "--username" not in workflow


@pytest.mark.parametrize("job_name", ["publish-testpypi", "publish-pypi"])
def test_public_upload_job_has_its_own_exact_locked_checkout(job_name: str) -> None:
    parsed = yaml.safe_load(_read(GITHUB_PUBLISH_WORKFLOW))
    steps = parsed["jobs"][job_name]["steps"]
    names = [step["name"] for step in steps]
    checkout_index = names.index("Checkout exact locked publisher metadata")
    sync_index = names.index(
        "Install locked publisher toolchain without registry authority"
    )
    upload_index = next(
        index for index, name in enumerate(names) if name.startswith("Upload to ")
    )
    checkout = steps[checkout_index]
    sync = steps[sync_index]

    assert checkout["with"] == {
        "ref": "${{ needs.prepare-release.outputs.source_sha }}",
        "persist-credentials": False,
    }
    assert checkout_index < sync_index < upload_index
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in sync["run"]
    assert "test -f pyproject.toml" in sync["run"]
    assert "test -f uv.lock" in sync["run"]
    assert "uv sync --only-group publish --locked" in sync["run"]
    assert "--no-install-project" in sync["run"]


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


def test_ci_gate_binds_latest_actions_run_to_authenticated_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_ci_gate()
    sha = "a" * 40
    context = "CI / Static checks and mocked regressions (push)"
    runs_path = (
        "/repos/emersonfelipesp/netbox-proxbox/actions/runs?"
        f"branch=develop&event=push&head_sha={sha}&limit=100&page=1"
    )
    jobs_path = "/repos/emersonfelipesp/netbox-proxbox/actions/runs/12/jobs"
    run = {
        "id": 12,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_sha": sha,
        "head_branch": "develop",
        "path": "ci.yml@refs/heads/develop",
        "run_attempt": 0,
        "actor": {"login": "emersonfelipesp"},
    }
    job = {
        "id": 34,
        "run_id": 12,
        "run_attempt": 1,
        "name": "Static checks and mocked regressions",
        "status": "completed",
        "conclusion": "success",
        "head_sha": sha,
        "runner_name": "ci-untrusted-netbox-proxbox",
        "labels": ["ci-untrusted-python312"],
        "html_url": "https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox/actions/runs/12/jobs/34",
    }
    responses = {
        runs_path: {"workflow_runs": [run], "total_count": 1},
        jobs_path: {"jobs": [job], "total_count": 1},
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
    assert evidence == {context: {"job_id": 34, "run_attempt": 1, "run_id": 12}}

    runs = responses[runs_path]["workflow_runs"]
    assert isinstance(runs, list)
    runs.insert(
        0,
        {
            **run,
            "id": 13,
            "status": "completed",
            "conclusion": "failure",
        },
    )
    responses[runs_path]["total_count"] = 2
    with pytest.raises(gate.CIGateError, match="run does not match"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    runs.pop(0)
    responses[runs_path]["total_count"] = 1

    run["run_attempt"] = 1
    assert gate.validate_ci_gate(
        owner="emersonfelipesp",
        repository="netbox-proxbox",
        source_sha=sha,
        required_contexts=[context],
        trusted_actor="emersonfelipesp",
        token="test-token",
    ) == {context: {"job_id": 34, "run_attempt": 1, "run_id": 12}}

    run["run_attempt"] = 2
    with pytest.raises(gate.CIGateError, match="run attempt is invalid"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    run["run_attempt"] = 0

    job["run_attempt"] = 2
    with pytest.raises(gate.CIGateError, match="job does not match"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    job["run_attempt"] = 1

    job["labels"] = ["ci-untrusted-python312", "prod-deploy"]
    with pytest.raises(gate.CIGateError, match="trusted CI runner class"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    job["labels"] = ["ci-untrusted-python312"]

    job["head_sha"] = "b" * 40
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
    manifest_digest = release_artifacts.manifest_sha256(manifest)
    evidence = {
        "artifacts": manifest["artifacts"],
        "deploy_source": "latest_package",
        "deployment_run_id": 123,
        "deployment_status": "success",
        "environment": "production",
        "manifest_sha256": manifest_digest,
        "observed_runtime_identity": (
            "netbox_proxbox==0.0.24@/opt/netbox/plugin-releases/"
            f"netbox-proxbox/{manifest_digest}/site-packages"
        ),
        "package": "netbox-proxbox",
        "repository": "emersonfelipesp/netbox-proxbox",
        "schema": 2,
        "source_sha": "b" * 40,
        "target": "netbox-proxbox",
        "version": "0.0.24",
    }
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

    evidence["deploy_source"] = "latest_package"
    evidence["observed_runtime_identity"] = "netbox_proxbox==0.0.24@/tmp/forged"
    with pytest.raises(release_artifacts.ReleaseArtifactError):
        release_artifacts.validate_release_attestation(
            evidence=evidence,
            manifest=manifest,
            repository="emersonfelipesp/netbox-proxbox",
        )
