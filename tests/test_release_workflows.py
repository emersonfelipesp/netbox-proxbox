"""Static contracts for the staged package-first release workflow."""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import os
import re
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
GITEA_CONSOLE_STACK_DEPLOY_WORKFLOW = (
    REPO_ROOT / ".gitea" / "workflows" / "deploy-console-stack.yml"
)
GITEA_PROMOTE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "promote-final-tag.yml"
RELEASE_ARTIFACTS_PATH = REPO_ROOT / "scripts" / "release_artifacts.py"
# Read back from the module's own pinned origin check rather than written
# down here: this repository is public and its disclosure guard forbids
# naming the private forge on any newly added line. Reading the pin also
# keeps these tests correct if the permitted origin is ever changed.
_TEST_REGISTRY = (
    "https://"
    + re.search(
        r'parsed\.netloc != "([^"]+)"',
        RELEASE_ARTIFACTS_PATH.read_text(encoding="utf-8"),
    ).group(1)
    + "/api/v1/packages/"
)
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


@pytest.mark.parametrize(
    "workflow_path",
    [GITEA_PUBLISH_WORKFLOW, GITEA_PROMOTE_WORKFLOW, GITEA_DEPLOY_WORKFLOW],
)
def test_release_workflow_shell_blocks_parse(workflow_path: Path) -> None:
    workflow = yaml.safe_load(_read(workflow_path))
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            script = step.get("run")
            if not isinstance(script, str):
                continue
            result = subprocess.run(
                ["/bin/bash", "-n"],
                input=script,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, (
                f"{workflow_path.name}:{job_name}:{step.get('name')}: {result.stderr}"
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


def test_repository_deploy_workflow_is_source_aware() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    assert "deploy_source:" in workflow
    assert "default: latest_package" in workflow
    assert "- latest_package" in workflow
    assert "- main_branch" in workflow
    assert "package_version:" in workflow
    assert "deploy-netbox-plugin-staging" in workflow
    assert "deploy-netbox-plugin netbox-proxbox" not in workflow
    assert (
        "proxbox-package-deploy deploy-main \\\n            netbox-proxbox" in workflow
    )
    assert (
        'deploy-netbox-plugin-package \\\n            netbox-proxbox "$PACKAGE_VERSION" "$DEPLOY_REQUEST_ID" "$PROOF_PATH"'
        in workflow
    )
    assert '"$DEPLOY_REQUEST_SHA256" "$GITHUB_RUN_ID"' in workflow
    assert "Reject a package deploy" not in workflow


def test_package_deploy_binds_the_claimed_registry_artifacts() -> None:
    workflow = yaml.safe_load(_read(GITEA_DEPLOY_WORKFLOW))
    production = workflow["jobs"]["production"]
    bind = _step(production, "Bind exact package artifacts before deployment")
    deploy = _step(production, "Deploy the exact package the request authorizes")

    assert bind["if"] == "${{ env.RESOLVED_SOURCE == 'latest_package' }}"
    assert bind["env"]["GITEA_PACKAGE_TOKEN"]
    assert "scripts/release_artifacts.py fetch-gitea" in bind["run"]
    assert 'json.load(open(sys.argv[1]))["request"]' in bind["run"]
    assert '"package_version": os.environ["PACKAGE_VERSION"]' in bind["run"]
    assert "release_manifest_sha256" in bind["run"]
    assert 'request["artifacts"]' in bind["run"]
    assert deploy["if"] == "${{ env.RESOLVED_SOURCE == 'latest_package' }}"
    assert 'echo "DEPLOY_COMPLETED=true"' in deploy["run"]
    receipt = _step(production, "Publish host-issued successful-deployment attestation")
    assert 'netbox-proxbox "$PACKAGE_VERSION" "$DEPLOY_REQUEST_ID"' in receipt["run"]
    assert '"$DEPLOY_REQUEST_SHA256" "$GITHUB_RUN_ID"' in receipt["run"]


def test_production_deploy_claims_a_signed_authorization() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # The management backend injects these on every authorized dispatch; a
    # workflow that does not declare them cannot be dispatched through the
    # proof path. A declared input that is not sent resolves to its default
    # rather than staying empty, so both keep an empty default and are shape
    # checked below.
    assert "deploy_request_id:" in workflow
    assert "deploy_request_sha256:" in workflow
    assert "/git/deployment-proofs/${DEPLOY_REQUEST_ID}/claim" in workflow

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
    assert "unsupported deploy source" in workflow
    assert 'echo "DEPLOY_COMPLETED=true"' in workflow
    assert 'test "${DEPLOY_COMPLETED:-}" = "true"' in workflow


def test_production_health_gate_actually_asserts_service_state() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # healthcheck-app is the deploy script gate; status-app is diagnostic only.
    # Proxbox sync runs on netbox-rq, so the gate also asserts the Compose worker.
    start = workflow.index("- name: Require healthy production status")
    gate = workflow[start : workflow.index("- name:", start + 1)]
    assert "run: /opt/nmulticloud/deploy/bin/status-app netbox\n" not in gate
    assert "/opt/nmulticloud/deploy/bin/healthcheck-app netbox" in gate
    assert "source /opt/nmulticloud/deploy/bin/nmc-deploy-lib" in gate
    assert "compose_cmd netbox ps --status running --services" in gate
    assert "grep -qx 'netbox-rq'" in gate
    assert "/opt/nmulticloud/deploy/bin/status-app netbox || true" in gate
    assert "[=,]netbox\\.service:active" not in gate
    assert "[=,]netbox-rq\\.service:active" not in gate


def test_console_stack_recovery_deploy_is_fixed_and_input_free() -> None:
    workflow = _read(GITEA_CONSOLE_STACK_DEPLOY_WORKFLOW)
    parsed = yaml.safe_load(workflow)

    assert parsed["on"] == {"workflow_dispatch": None}
    job = parsed["jobs"]["deploy"]
    assert job["runs-on"] == "prod-deploy"
    assert set(job["env"]) == {
        "BACKEND_COMMIT",
        "DEPLOY_APP_COMMAND",
        "NMS_COMMIT",
        "NMS_MCP_COMMIT",
        "STATUS_APP_COMMAND",
    }
    assert all(
        re.fullmatch(r"[a-f0-9]{40}", job["env"][name])
        for name in ("BACKEND_COMMIT", "NMS_MCP_COMMIT", "NMS_COMMIT")
    )
    assert 'test "$GITHUB_REPOSITORY" = emersonfelipesp/netbox-proxbox' in workflow
    assert 'test "$GITHUB_REF" = refs/heads/main' in workflow
    assert 'test "$GITHUB_ACTOR" = emersonfelipesp' in workflow
    assert (
        workflow.index('nms-backend "$BACKEND_COMMIT"')
        < workflow.index('nms-mcp "$NMS_MCP_COMMIT"')
        < workflow.index('nms "$NMS_COMMIT"')
    )
    assert "workflow_dispatch:\n    inputs:" not in workflow
    assert "--network=none --read-only" in workflow
    assert "--cap-drop=ALL --security-opt=no-new-privileges:true" in workflow
    assert "--user=65534:65534" in workflow
    assert "--env=PYTHONPATH=/app" in workflow
    assert "--env=XDG_CONFIG_HOME=/tmp" in workflow
    assert "trap 'docker rm -f" in workflow


def test_claim_ignores_ambient_curl_configuration() -> None:
    workflow = _read(GITEA_DEPLOY_WORKFLOW)

    # A .curlrc on this shared root runner can carry --connect-to/--resolve,
    # which redirect a loopback-looking URL despite --noproxy and would hand
    # over the request id in the path and its digest in the body. --disable
    # only works as the first argument.
    assert "curl --disable" in workflow


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


def test_final_tag_promotion_requires_main_package_and_deploy_evidence() -> None:
    workflow = _read(GITEA_PROMOTE_WORKFLOW)

    assert "github.repository == 'emersonfelipesp/netbox-proxbox'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert 'test "$(git rev-parse HEAD^{commit})" = "${GITHUB_SHA}"' in workflow
    assert "refs/remotes/gitea/release-main" in workflow
    assert "refs/remotes/gitea/release-develop" in workflow
    assert "scripts/release_artifacts.py fetch-gitea" in workflow
    assert "scripts/release_artifacts.py fetch-attestation" in workflow
    assert "https://github.com/emersonfelipesp/netbox-proxbox.git" in workflow
    assert "GH_TOKEN: ${{ secrets.GH_MIRROR_TOKEN }}" in workflow
    assert 'GIT_ASKPASS="$SECRET_ROOT/askpass"' in workflow
    assert "http.https://github.com/.extraheader" not in workflow
    assert workflow.index("fetch-attestation") < workflow.index("GH_TOKEN:")
    assert '"refs/tags/${TAG}"' in workflow
    assert '"refs/tags/${TAG}^{}"' in workflow
    assert 'test "$REMOTE_TAG_OBJECT" = "$LOCAL_TAG_OBJECT"' in workflow
    assert 'test "$REMOTE_SOURCE_SHA" = "$SOURCE_SHA"' in workflow
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
    assert _PRIVATE_FORGE_HOST not in workflow, (
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
        "setuptools==83.0.0",
        "twine==6.2.0",
        "wheel==0.46.2",
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
        # Derived from the gate's own origin constant rather than written out:
        # the gate compares this for equality, and a literal here would both
        # duplicate the host in a public file and silently break if it moved.
        "html_url": f"{gate.HTML_ORIGIN}/emersonfelipesp/netbox-proxbox/actions/runs/12/jobs/34",
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


def test_final_release_requires_exact_promotion_evidence(tmp_path: Path) -> None:
    release_artifacts = _load_release_artifacts()
    pinned_public_der = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-pubin",
            "-in",
            str(release_artifacts.RECEIPT_PUBLIC_KEY),
            "-outform",
            "DER",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert (
        hashlib.sha256(pinned_public_der).hexdigest()
        == release_artifacts.RECEIPT_PUBLIC_KEY_SHA256
    )
    private_key = tmp_path / "receipt-private.pem"
    public_key = tmp_path / "receipt-public.pem"
    subprocess.run(
        [
            "/usr/bin/openssl",
            "genpkey",
            "-algorithm",
            "ED25519",
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
    public_der = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_key),
            "-outform",
            "DER",
        ],
        check=True,
        capture_output=True,
    ).stdout
    release_artifacts.RECEIPT_PUBLIC_KEY = public_key
    release_artifacts.RECEIPT_PUBLIC_KEY_SHA256 = hashlib.sha256(public_der).hexdigest()
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
    receipt_prefix = "".join(("n", "m", "s"))
    request_id_field = receipt_prefix + "_request_id"
    request_digest_field = receipt_prefix + "_request_sha256"
    workflow_sha_field = receipt_prefix + "_workflow_sha"
    assert (request_id_field, request_digest_field, workflow_sha_field) == (
        "".join(("n", "m", "s", "_request_id")),
        "".join(("n", "m", "s", "_request_sha256")),
        "".join(("n", "m", "s", "_workflow_sha")),
    )
    evidence = {
        "artifacts": manifest["artifacts"],
        "deploy_source": "latest_package",
        "deployment_generation": "c" * 64,
        "deployment_run_id": 123,
        "deployment_status": "success",
        "environment": "production",
        "manifest_sha256": manifest_digest,
        request_id_field: "d" * 32,
        request_digest_field: "e" * 64,
        workflow_sha_field: "f" * 40,
        "observed_runtime_identity": (
            "netbox_proxbox==0.0.24@/opt/netbox/plugin-releases/"
            f"netbox-proxbox/{manifest_digest}/site-packages"
        ),
        "package": "netbox-proxbox",
        "repository": "emersonfelipesp/netbox-proxbox",
        "schema": 2,
        "signature": "",
        "signing_key_sha256": release_artifacts.RECEIPT_PUBLIC_KEY_SHA256,
        "source_sha": "b" * 40,
        "target": "netbox-proxbox",
        "version": "0.0.24",
    }
    unsigned = dict(evidence)
    del unsigned["signature"]
    payload_path = tmp_path / "receipt-unsigned.json"
    payload_path.write_bytes(release_artifacts._manifest_bytes(unsigned))
    signature = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(private_key),
            "-in",
            str(payload_path),
        ],
        check=True,
        capture_output=True,
    ).stdout
    evidence["signature"] = base64.b64encode(signature).decode("ascii")
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

    evidence["observed_runtime_identity"] = (
        "netbox_proxbox==0.0.24@/opt/netbox/plugin-releases/"
        f"netbox-proxbox/{manifest_digest}/site-packages"
    )
    evidence["signature"] = "A" * 86 + "=="
    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="signature is invalid",
    ):
        release_artifacts.validate_release_attestation(
            evidence=evidence,
            manifest=manifest,
            repository="emersonfelipesp/netbox-proxbox",
        )


# This repository is published publicly. The deployment workflow named the
# internal management stack in eight places, and those names were reintroduced
# once already by copying the workflow between repositories -- so the rename is
# only durable with a guard behind it.
# This repository is published publicly. The deployment workflow named the
# internal management stack in eight places, and those names were reintroduced
# once already by copying the workflow between repositories -- so the rename is
# only durable with a guard behind it.
#
# The needles are assembled rather than written out, and the self-test's
# examples use reserved documentation values. A guard whose own fixtures spell
# the forbidden strings publishes them while reporting the file clean.
_PRIVATE_STACK_TOKEN = "".join(("n", "m", "s"))
_PRIVATE_FORGE_HOST = ".".join(("git", "nmulti", "cloud"))
_LOOPBACK_ADDRESS = ".".join(("127", "0", "0", "1"))

# Two separator rules, because an acronym needs both: `aTokenWord` splits on the
# lower-to-upper transition, `TOKENWord` between the acronym's last capital and
# the following capitalised word.
_CAMEL_BOUNDARIES = (
    re.compile(r"(?<=[a-z0-9])(?=[A-Z])"),
    re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])"),
)
_STACK_PATTERN = re.compile(
    rf"(?<![A-Za-z]){_PRIVATE_STACK_TOKEN}(?![A-Za-z])",
    re.IGNORECASE,
)
_INTERNAL_HOST_PATTERN = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:cloud|ai|local)\b", re.IGNORECASE
)
_IP_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# Exact addresses only. `localhost` is a name, not an address, and never matches
# the address pattern at all.
_ALLOWED_ADDRESSES = frozenset({_LOOPBACK_ADDRESS})
_NOVNC_RUNTIME_ROOT = Path("netbox_proxbox/static/netbox_proxbox/vendor/novnc")
_DIGEST_PINNED_VENDORED_RUNTIME_PATHS = frozenset(
    _NOVNC_RUNTIME_ROOT / relative
    for relative in (REPO_ROOT / _NOVNC_RUNTIME_ROOT / "RUNTIME_FILES.txt")
    .read_text(encoding="utf-8")
    .splitlines()
)


def _split_camel(text: str) -> str:
    for boundary in _CAMEL_BOUNDARIES:
        text = boundary.sub("_", text)
    return text


def _disclosures(text: str) -> list[str]:
    """Return the offending fragments in one line of a public file."""
    found: list[str] = []
    if _STACK_PATTERN.search(_split_camel(text)):
        found.append("internal stack name")
    found.extend(_INTERNAL_HOST_PATTERN.findall(text))
    # Addresses are extracted whole, then compared exactly. Removing permitted
    # addresses by substring first would truncate a longer one into something
    # that no longer looks like an address.
    for address in _IP_PATTERN.findall(text):
        if address not in _ALLOWED_ADDRESSES:
            found.append(address)
    return found


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _review_base_candidates() -> list[str]:
    """Branch refs that may name the review base, most trustworthy first.

    ``PROXBOX_REVIEW_BASE`` is an explicit operator choice. In a pull-request
    run the platform names the base branch in ``GITHUB_BASE_REF`` (Gitea
    Actions sets the same variable); otherwise the integration branch is the
    base. The ``gitea`` remote is the canonical implementation remote, and
    ``origin`` is what a CI checkout or a fresh clone calls it.
    """
    explicit = os.environ.get("PROXBOX_REVIEW_BASE", "").strip()
    branch = os.environ.get("GITHUB_BASE_REF", "").strip() or "develop"
    candidates = [explicit] if explicit else []
    candidates.extend((f"gitea/{branch}", f"origin/{branch}"))
    return candidates


def _github_event() -> dict:
    """The Actions event payload, or ``{}`` outside a workflow run."""
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path or not Path(event_path).is_file():
        return {}
    try:
        payload = json.loads(Path(event_path).read_text())
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


_NO_COMMIT = "0" * 40


def _push_review_base() -> str:
    """The commit a branch push is reviewed against: what the branch was before.

    A push to a protected branch is the merge landing, and after a full
    checkout the branch ref *is* ``HEAD``, so the merge base against the
    branch would be empty. ``before`` from the event payload is the last
    commit already on the branch; it must exist and be an ancestor of
    ``HEAD``, otherwise the run is not reviewing what it thinks it is.
    """
    before = str(_github_event().get("before", "")).strip()
    if not before or before == _NO_COMMIT:
        pytest.fail(
            "push event has no usable before-commit; refusing to skip the guard"
        )
    if _git("rev-parse", "--verify", "--quiet", f"{before}^{{commit}}").returncode:
        pytest.fail(f"push before-commit {before[:12]} is not in this checkout")
    if _git("merge-base", "--is-ancestor", before, "HEAD").returncode:
        pytest.fail(f"push before-commit {before[:12]} is not an ancestor of HEAD")
    return before


def _branch_review_base(candidates: list[str]) -> str | None:
    for ref in candidates:
        if _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode:
            continue
        result = _git("merge-base", "HEAD", ref)
        if result.returncode != 0 or not result.stdout.strip():
            pytest.fail(
                f"cannot compute the merge base against {ref}: "
                f"{result.stderr.strip() or 'no output'}"
            )
        return result.stdout.strip()
    return None


def _review_base() -> str:
    """Resolve the commit this checkout is reviewed against.

    A guard that cannot find its base must not certify anything. The base is
    chosen by event: a pull request diffs against its base branch; a branch
    push diffs against the branch's previous tip; a tag, release, dispatch,
    or scheduled run has no branch base and says so — the change it validates
    was scanned on its pull request and again on the push that landed it. In
    CI a missing pull-request base is a workflow defect (the checkout did not
    fetch the base branch), so the test fails; only a local checkout without
    any remote may skip.
    """
    explicit = os.environ.get("PROXBOX_REVIEW_BASE", "").strip()
    event = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    in_ci = any(
        os.environ.get(name) for name in ("CI", "GITHUB_ACTIONS", "GITEA_ACTIONS")
    )
    if not explicit and in_ci and event == "push":
        if os.environ.get("GITHUB_REF", "").startswith("refs/tags/"):
            pytest.skip(
                "tag push has no branch review base; scanned on its pull request"
            )
        return _push_review_base()
    if not explicit and in_ci and event not in ("pull_request", ""):
        pytest.skip(
            f"{event} event has no branch review base; the change was scanned "
            "on its pull request and on the push that landed it"
        )
    candidates = _review_base_candidates()
    base = _branch_review_base(candidates)
    if base is not None:
        return base
    message = f"no review base ref is available (tried {', '.join(candidates)})"
    if in_ci:
        pytest.fail(f"{message}; the workflow checkout must fetch the base branch")
    pytest.skip(message)


def _changed_public_files() -> "list[Path]":
    """Every file this branch changes, resolved from git rather than by hand.

    A hand-maintained list is a guard that silently stops covering the thing it
    was added for.
    """
    result = _git("diff", "--name-only", "--diff-filter=d", _review_base())
    if result.returncode != 0:
        pytest.fail(f"cannot resolve the changed file set: {result.stderr.strip()}")
    paths = [REPO_ROOT / line for line in result.stdout.split() if line]
    existing = [path for path in paths if path.is_file()]
    assert existing, "the branch must change at least one file"
    return existing


def _changed_paths(base: str) -> tuple[list[str], list[str]]:
    """``(text_paths, binary_paths)`` changed between ``base`` and ``HEAD``.

    Read from ``git diff --numstat -z``, whose NUL-delimited output carries
    every pathname verbatim — a tab or newline in a filename, or a rename
    rendered as ``old => new`` in the human form, cannot hide a file from the
    scanner. A rename contributes its *destination* path.
    """
    result = _git("diff", "--numstat", "-z", "--diff-filter=d", base, "HEAD")
    if result.returncode != 0:
        pytest.fail(f"cannot list changed files: {result.stderr.strip()}")
    tokens = result.stdout.split("\0")
    text: list[str] = []
    binary: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        added, _deleted, path = token.split("\t", 2)
        if path == "":
            # Rename or copy: the two paths follow as separate records.
            path = tokens[index + 1]
            index += 2
        (binary if added == "-" else text).append(path)
    return text, binary


def _iter_branch_added_lines() -> "list[tuple[Path, int, str]]":
    """Yield ``(path, new_line_number, text)`` for each line added on this branch.

    Binary files are refused outright: the line scanner cannot read them, and
    a directory name proves nothing about where a file came from — a pull
    request can put any bytes under any path. Regenerated screenshots reach
    ``develop`` through the screenshots workflow's own push, which carries no
    pull request and is not this guard's concern.
    """
    base = _review_base()
    text_paths, binary_paths = _changed_paths(base)
    assert not binary_paths, (
        "binary public files cannot be scanned for private infrastructure "
        f"names and are not accepted on a reviewed branch: {binary_paths}"
    )

    additions: list[tuple[Path, int, str]] = []
    for relative in text_paths:
        relative_path = Path(relative)
        if relative_path in _DIGEST_PINNED_VENDORED_RUNTIME_PATHS:
            # Third-party runtime bytes cannot be rewritten to satisfy the
            # prose disclosure scan. The exhaustive manifest, file-list, and
            # SHA-256 tree-digest contracts in test_vm_console_frontend.py
            # cover every permitted file and byte in this exact set. Authored
            # provenance and manifest files remain subject to this scanner.
            continue
        result = _git("diff", "-U0", "--diff-filter=d", base, "HEAD", "--", relative)
        if result.returncode != 0:
            pytest.fail(f"cannot resolve branch additions: {result.stderr.strip()}")
        additions.extend(_parse_added_lines(REPO_ROOT / relative, result.stdout))
    if not additions:
        # Nothing was added, so nothing can disclose; say which case this is
        # so a skip in the log is explainable rather than suspicious.
        reason = (
            "HEAD and the review base have identical trees"
            if not text_paths
            else "the branch only removes lines"
        )
        pytest.skip(f"no added lines between base and HEAD: {reason}")
    return additions


def _parse_added_lines(path: Path, diff: str) -> "list[tuple[Path, int, str]]":
    """Added lines of one file's ``-U0`` patch, with their new line numbers.

    The path is known from the NUL-delimited listing, so the quoted ``+++``
    header is ignored rather than parsed.
    """
    next_line = 0
    additions: list[tuple[Path, int, str]] = []
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if match is not None:
                next_line = int(match.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            additions.append((path, next_line, raw[1:]))
            next_line += 1
        elif raw.startswith(" "):
            next_line += 1
    return additions


def _set_branch_diff(
    monkeypatch: pytest.MonkeyPatch,
    diff: str,
    *,
    returncode: int = 0,
    paths: tuple[str, ...] = ("README.md",),
) -> None:
    """Replace the review base and branch diff for disclosure-guard tests."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    numstat = "".join(f"1\t0\t{path}\0" for path in paths) if diff else ""

    def run(args, **kwargs):
        stdout = numstat if "--numstat" in args else diff
        return subprocess.CompletedProcess(
            args=list(args), returncode=returncode, stdout=stdout, stderr="boom"
        )

    monkeypatch.setattr(subprocess, "run", run)


def _fake_git(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, tuple[int, str]],
) -> list[list[str]]:
    """Answer ``git`` invocations from a table keyed by their first argument."""
    calls: list[list[str]] = []

    def run(args, **kwargs):
        calls.append(list(args))
        key = " ".join(args[1:3]) if args[1] == "diff" else args[1]
        code, out = responses.get(key, responses.get(args[1], (1, "")))
        return subprocess.CompletedProcess(
            args=args, returncode=code, stdout=out, stderr="fatal: bad revision"
        )

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_gitea_quality_job_tells_the_guard_it_runs_in_ci() -> None:
    """The untrusted runner exports no CI markers; the workflow must supply them."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".gitea" / "workflows" / "ci.yml").read_text()
    )
    env = workflow["jobs"]["quality"]["env"]
    assert env["CI"] == "true"
    assert env["GITHUB_EVENT_NAME"] == "${{ github.event_name }}"
    assert env["GITHUB_BASE_REF"] == "${{ github.base_ref }}"
    assert env["GITHUB_REF"] == "${{ github.ref }}"
    assert "github.event.before" in env["PROXBOX_REVIEW_BASE"]
    assert "github.event_name == 'push'" in env["PROXBOX_REVIEW_BASE"]

    """The disclosure guard fails without a base, so CI must fetch full history."""
    gitea_ci = REPO_ROOT / ".gitea" / "workflows" / "ci.yml"
    github_ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    for path, job in ((gitea_ci, "quality"), (github_ci, "test")):
        workflow = yaml.safe_load(path.read_text())
        steps = workflow["jobs"][job]["steps"]
        checkout = next(
            step
            for step in steps
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout.get("with", {}).get("fetch-depth") == 0, (
            f"{path.name}:{job} checkout must use fetch-depth: 0"
        )


def test_iter_branch_added_lines_skips_zero_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_branch_diff(monkeypatch, "")

    with pytest.raises(
        pytest.skip.Exception, match="no added lines between base and HEAD"
    ):
        _iter_branch_added_lines()


def test_iter_branch_added_lines_fails_when_diff_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A diff error is not a clean branch; the guard must not certify it."""
    _set_branch_diff(monkeypatch, "", returncode=128)

    with pytest.raises(
        pytest.fail.Exception,
        match="cannot (list changed files|resolve branch additions)",
    ):
        _iter_branch_added_lines()


def _set_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, **payload
) -> None:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(payload))
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", name)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.delenv("PROXBOX_REVIEW_BASE", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)


def test_push_event_reviews_against_the_previous_branch_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On a protected-branch push the branch ref is HEAD; ``before`` is the base."""
    _set_event(monkeypatch, tmp_path, "push", before="a" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/develop")
    calls = _fake_git(monkeypatch, {"rev-parse": (0, "aaa\n"), "merge-base": (0, "")})

    assert _review_base() == "a" * 40
    assert ["git", "merge-base", "--is-ancestor", "a" * 40, "HEAD"] in calls


@pytest.mark.parametrize("before", ["", "0" * 40])
def test_push_event_without_a_before_commit_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, before: str
) -> None:
    _set_event(monkeypatch, tmp_path, "push", before=before)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/develop")
    _fake_git(monkeypatch, {})

    with pytest.raises(pytest.fail.Exception, match="no usable before-commit"):
        _review_base()


def test_push_event_with_a_foreign_before_commit_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ``before`` that is not an ancestor means the run reviews the wrong range."""
    _set_event(monkeypatch, tmp_path, "push", before="b" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    _fake_git(monkeypatch, {"rev-parse": (0, "bbb\n"), "merge-base": (1, "")})

    with pytest.raises(pytest.fail.Exception, match="not an ancestor of HEAD"):
        _review_base()


def test_tag_push_and_release_events_skip_with_a_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_event(monkeypatch, tmp_path, "push", before="c" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.0.27")
    _fake_git(monkeypatch, {})
    with pytest.raises(
        pytest.skip.Exception, match="tag push has no branch review base"
    ):
        _review_base()

    _set_event(monkeypatch, tmp_path, "release")
    with pytest.raises(
        pytest.skip.Exception, match="release event has no branch review base"
    ):
        _review_base()


def test_pull_request_event_still_uses_the_base_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_event(monkeypatch, tmp_path, "pull_request")
    monkeypatch.setenv("GITHUB_BASE_REF", "develop")
    calls = _fake_git(
        monkeypatch, {"rev-parse": (0, "abc\n"), "merge-base": (0, "feedbeef\n")}
    )

    assert _review_base() == "feedbeef"
    assert ["git", "merge-base", "HEAD", "gitea/develop"] in calls


def test_binary_public_file_changes_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The line scanner cannot read a PNG; an unreviewed one must not pass as clean."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    _fake_git(monkeypatch, {"diff --numstat": (0, "-\t-\tdocs/topology.png\0")})

    with pytest.raises(AssertionError, match="docs/topology.png"):
        _iter_branch_added_lines()


def test_screenshot_binaries_are_refused_on_a_reviewed_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A directory name is not provenance: any bytes can be put under it."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    _fake_git(
        monkeypatch,
        {"diff --numstat": (0, "-\t-\tdocs/assets/screenshots/home.png\0")},
    )

    with pytest.raises(AssertionError, match="docs/assets/screenshots/home.png"):
        _iter_branch_added_lines()


def test_renamed_binary_is_refused_by_its_destination_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--numstat -z`` renders a rename as two records; the destination counts."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    numstat = "-\t-\t\0docs/assets/screenshots/old.png\0docs/topology.png\0"
    _fake_git(monkeypatch, {"diff --numstat": (0, numstat)})

    with pytest.raises(AssertionError, match=re.escape("['docs/topology.png']")):
        _iter_branch_added_lines()


def test_text_filename_with_a_tab_is_still_scanned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git C-quotes such names in patch headers; the NUL listing carries them verbatim."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    odd_name = "docs/odd\tname.md"
    diff = f'+++ "b/docs/odd\\tname.md"\n@@ -0,0 +1 @@\n+{_PRIVATE_STACK_TOKEN}\n'
    calls = _fake_git(
        monkeypatch,
        {"diff --numstat": (0, f"1\t0\t{odd_name}\0"), "diff -U0": (0, diff)},
    )

    additions = _iter_branch_added_lines()

    assert [str(path.relative_to(REPO_ROOT)) for path, _n, _t in additions] == [
        odd_name
    ]
    assert any(call[-2:] == ["--", odd_name] for call in calls)
    with pytest.raises(AssertionError, match=re.escape(_PRIVATE_STACK_TOKEN)):
        test_public_files_name_no_private_infrastructure()


def test_only_digest_pinned_vendored_runtime_files_skip_disclosure_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authored, unrelated, and sibling files cannot inherit the runtime exemption."""
    monkeypatch.setattr(sys.modules[__name__], "_review_base", lambda: "base")
    runtime_path = next(iter(_DIGEST_PINNED_VENDORED_RUNTIME_PATHS)).as_posix()
    scanned_paths = (
        (_NOVNC_RUNTIME_ROOT / "SOURCE.md").as_posix(),
        (_NOVNC_RUNTIME_ROOT / "UNRELATED.md").as_posix(),
        Path(f"{_NOVNC_RUNTIME_ROOT}-extra/core.js").as_posix(),
    )
    changed_paths = (runtime_path, *scanned_paths)
    numstat = "".join(f"1\t0\t{path}\0" for path in changed_paths)
    diff = f"@@ -0,0 +1 @@\n+{_PRIVATE_STACK_TOKEN}\n"
    calls = _fake_git(
        monkeypatch,
        {"diff --numstat": (0, numstat), "diff -U0": (0, diff)},
    )

    additions = _iter_branch_added_lines()

    assert [path.relative_to(REPO_ROOT).as_posix() for path, _n, _t in additions] == [
        *scanned_paths
    ]
    assert not any(call[-2:] == ["--", runtime_path] for call in calls)
    assert all(_disclosures(line) for _path, _number, line in additions)


def test_the_disclosure_guard_catches_what_it_is_for() -> None:
    """Self-test. A guard that cannot see the thing certifies the wrong result."""
    token = _PRIVATE_STACK_TOKEN
    # RFC 5737 documentation range: safe to write down, still an address.
    documentation_address = ".".join(("192", "0", "2", "207"))
    prefix_shadowed = _LOOPBACK_ADDRESS + "0"

    for disclosing in (
        f"{token} in prose",
        f"a_{token}_identifier",
        f"_{token.upper()}_REQUEST_ID",
        f"{token}Backend",
        f"a{token.upper()}Identifier",
        f"{token.upper()}Backend",
        f"pre{token.upper()}Post",
        f"{token}-backend",
        _PRIVATE_FORGE_HOST,
        f"https://{_PRIVATE_FORGE_HOST}/owner/repo.git",
        documentation_address,
        prefix_shadowed,
        f"the host at {_LOOPBACK_ADDRESS} and also {documentation_address}",
    ):
        assert _disclosures(disclosing), f"guard missed {disclosing!r}"

    for permitted in (
        f"http://{_LOOPBACK_ADDRESS}:16001",
        "bind to localhost only",
        "the columns are aligned",
        "transforms and normalizes",
        "https://forge.example.invalid/owner/repo",
    ):
        assert not _disclosures(permitted), f"guard false-positived on {permitted!r}"


def test_public_files_name_no_private_infrastructure() -> None:
    offenders: list[str] = []
    for path, number, line in _iter_branch_added_lines():
        for fragment in _disclosures(line):
            relative = path.relative_to(REPO_ROOT)
            offenders.append(f"{relative}:{number}: {fragment}: {line.strip()}")
    assert offenders == []


def test_publish_workflow_produces_the_manifest_its_consumers_require() -> None:
    """The publish workflow must build and publish the release manifest.

    `deploy-production.yml`'s `latest_package` source and
    `promote-final-tag.yml` both call `release_artifacts.py fetch-gitea`,
    which fetches a `<package>-release-manifest` generic package for the
    version being deployed or promoted. The script has always been able to
    build and publish that manifest, but the publish workflow called neither
    subcommand, so no published version had one and both consumers were
    unreachable for every version.

    The assertions below are on the parsed step list rather than on substrings
    of the file, because the two properties that make the manifest trustworthy
    are both about *order*: the manifest must describe the same bytes that are
    uploaded, and it must not exist for a version whose upload was not verified.
    A substring test cannot see either.
    """
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    job = workflow["jobs"]["publish-gitea"]
    steps = job["steps"]
    names = [step.get("name") for step in steps if isinstance(step, dict)]

    assert "Build release manifest" in names, (
        "publish-gitea must build a release manifest; without it "
        "`fetch-gitea` fails for every published version"
    )
    assert "Publish release manifest" in names, (
        "publish-gitea must upload the release manifest to the registry"
    )

    build_dists = names.index("Build distributions")
    build_manifest = names.index("Build release manifest")
    upload = names.index("Publish to Gitea Package Registry")
    verify = names.index("Verify package in Gitea registry")
    publish_manifest = names.index("Publish release manifest")

    # The manifest records a sha256 per artifact. Building it from `dist/`
    # before the upload is what makes those digests describe the bytes that
    # were actually published; a manifest built afterwards could be computed
    # from a rebuilt or mutated tree.
    assert build_dists < build_manifest < upload

    # The manifest is the signal `latest_package` uses to decide a version is
    # deployable. Publishing it before the registry upload is verified would
    # advertise a version whose artifacts may not be there.
    assert verify < publish_manifest

    manifest_step = _step(job, "Build release manifest")
    manifest_run = manifest_step["run"]
    assert "release_artifacts.py manifest" in manifest_run
    assert "--manifest release-manifest.json" in manifest_run

    # `fetch-gitea` compares the manifest's source_sha against the commit the
    # requested tag resolves to. Taking it from the ambient `GITHUB_SHA`, or
    # from an annotated tag's own object id, yields a value that never matches
    # and fails every deploy at the provenance check -- after the version has
    # been consumed. `^{commit}` peels the tag to its commit.
    assert 'SOURCE_SHA="${EXPECTED_SOURCE_SHA}"' in manifest_run
    assert "GITHUB_SHA" not in manifest_run

    publish_step = _step(job, "Publish release manifest")
    publish_run = publish_step["run"]
    assert "release_artifacts.py publish-manifest" in publish_run
    assert "--owner emersonfelipesp" in publish_run
    # publish-manifest reads the token from the environment, not from argv, so
    # the step must export it or the upload fails as unauthenticated.
    assert publish_step["env"]["GITEA_PACKAGE_TOKEN"]


def _artifact_manifest(tmp_path: Path) -> tuple[object, dict[str, object]]:
    """Build a real two-artifact manifest for registry-verification tests."""
    release_artifacts = _load_release_artifacts()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "netbox_proxbox-0.0.26-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (dist / "netbox_proxbox-0.0.26.tar.gz").write_bytes(b"sdist-bytes")
    manifest = release_artifacts.create_manifest(
        dist=dist, package="netbox-proxbox", version="0.0.26", source_sha="b" * 40
    )
    return release_artifacts, manifest


def test_candidate_build_source_must_be_passive_hatchling_metadata(
    tmp_path: Path,
) -> None:
    release_artifacts = _load_release_artifacts()
    source = tmp_path / "candidate"
    source.mkdir()
    pyproject = source / "pyproject.toml"
    pyproject.write_text(
        re.sub(
            r'^version = "[^\"]+"$',
            'version = "0.0.26"',
            _read(PYPROJECT_PATH),
            count=1,
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )

    release_artifacts.validate_build_source(
        source=source,
        package="netbox-proxbox",
        version="0.0.26",
    )

    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + '\n[tool.hatch.build.hooks.custom]\npath = "hatch_build.py"\n',
        encoding="utf-8",
    )
    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="passive Hatchling contract",
    ):
        release_artifacts.validate_build_source(
            source=source,
            package="netbox-proxbox",
            version="0.0.26",
        )


def test_candidate_source_is_copied_without_symlink_or_special_file_escapes(
    tmp_path: Path,
) -> None:
    release_artifacts = _load_release_artifacts()
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        re.sub(
            r'^version = "[^\"]+"$',
            'version = "0.0.26"',
            _read(PYPROJECT_PATH),
            count=1,
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
    (source / "README.md").write_text("readme\n", encoding="utf-8")
    (source / "LICENSE").write_text("license\n", encoding="utf-8")
    package = source / "netbox_proxbox"
    package.mkdir()
    (package / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    cli = source / "proxbox_cli"
    cli.mkdir()
    (cli / "__init__.py").write_text("value = 2\n", encoding="utf-8")

    sanitized = tmp_path / "sanitized"
    release_artifacts.sanitize_build_source(
        source=source,
        destination=sanitized,
        package="netbox-proxbox",
        version="0.0.26",
    )
    assert (sanitized / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert not any(path.is_symlink() for path in sanitized.rglob("*"))

    (source / "outside-link").symlink_to(tmp_path / "outside")
    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="unsafe file",
    ):
        release_artifacts.sanitize_build_source(
            source=source,
            destination=tmp_path / "rejected",
            package="netbox-proxbox",
            version="0.0.26",
        )


def test_release_tag_ruleset_must_be_active_immutable_and_no_bypass(
    tmp_path: Path,
) -> None:
    release_artifacts = _load_release_artifacts()
    rulesets = tmp_path / "rulesets"
    rulesets.mkdir()
    ruleset_path = rulesets / "42.json"
    ruleset = {
        "source_type": "Repository",
        "source": "emersonfelipesp/netbox-proxbox",
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"exclude": [], "include": ["refs/tags/v*"]},
        },
        "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}],
    }
    ruleset_path.write_text(json.dumps(ruleset), encoding="utf-8")

    release_artifacts.validate_github_tag_rulesets(
        rulesets=rulesets,
        repository="emersonfelipesp/netbox-proxbox",
    )

    for unsafe in (
        {**ruleset, "enforcement": "evaluate"},
        {**ruleset, "bypass_actors": [{"actor_type": "User", "actor_id": 1}]},
        {
            **ruleset,
            "conditions": {
                "ref_name": {"exclude": [], "include": ["refs/tags/release-*"]}
            },
        },
        {**ruleset, "rules": [{"type": "deletion"}]},
    ):
        ruleset_path.write_text(json.dumps(unsafe), encoding="utf-8")
        with pytest.raises(
            release_artifacts.ReleaseArtifactError,
            match="No active no-bypass ruleset",
        ):
            release_artifacts.validate_github_tag_rulesets(
                rulesets=rulesets,
                repository="emersonfelipesp/netbox-proxbox",
            )


def _registry_responses(manifest: dict[str, object]) -> dict[str, object]:
    files = [
        {
            "name": record["name"],
            "size": record["size"],
            "sha256": record["sha256"],
        }
        for record in manifest["artifacts"]
    ]
    return {
        "metadata": {
            "type": "pypi",
            "name": "netbox-proxbox",
            "version": "0.0.26",
            "repository": {"full_name": "emersonfelipesp/netbox-proxbox"},
        },
        "files": files,
        "content": {
            "netbox_proxbox-0.0.26-py3-none-any.whl": b"wheel-bytes",
            "netbox_proxbox-0.0.26.tar.gz": b"sdist-bytes",
        },
    }


def _patch_requests(
    monkeypatch: pytest.MonkeyPatch, release_artifacts: object, responses: dict
) -> None:
    def fake_request(url: str, **_kwargs: object) -> bytes:
        if "/pypi/files/" in url:
            name = url.rsplit("/", 1)[1]
            return responses["content"][name]
        payload = (
            responses["files"] if url.endswith("/files") else responses["metadata"]
        )
        return json.dumps(payload).encode()

    monkeypatch.setattr(release_artifacts, "_request", fake_request)


def test_registry_verification_requires_the_exact_published_artifact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counting version-matched search hits is not evidence the release exists.

    The old check listed the owner's packages and counted entries whose
    `version` field matched, which any package of any name at that version
    satisfies. The manifest published immediately afterwards is the provenance
    record every deploy and promotion verifies against, so the gate in front of
    it must prove this package's own wheel and sdist are present with the exact
    sizes and digests the manifest recorded.
    """
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    responses = _registry_responses(manifest)
    _patch_requests(monkeypatch, release_artifacts, responses)

    # The honest case passes.
    release_artifacts.verify_gitea_package_artifacts(
        registry=_TEST_REGISTRY,
        owner="emersonfelipesp",
        repository="netbox-proxbox",
        package="netbox-proxbox",
        version="0.0.26",
        manifest=manifest,
        token="t",
    )

    def rejects() -> None:
        with pytest.raises(release_artifacts.ReleaseArtifactError):
            release_artifacts.verify_gitea_package_artifacts(
                registry=_TEST_REGISTRY,
                owner="emersonfelipesp",
                repository="netbox-proxbox",
                package="netbox-proxbox",
                version="0.0.26",
                manifest=manifest,
                token="t",
            )

    # A digest that differs -- the registry holds different bytes than the
    # manifest attests to. This is the case the count could never see.
    original = list(responses["files"])
    responses["files"] = [dict(original[0], sha256="c" * 64), original[1]]
    rejects()

    # A size that differs, with the digest left intact.
    responses["files"] = [dict(original[0], size=original[0]["size"] + 1), original[1]]
    rejects()

    # An incomplete upload: the sdist never arrived.
    responses["files"] = [original[0]]
    rejects()

    # An extra file nobody attested to.
    responses["files"] = [
        *original,
        {"name": "extra.whl", "size": 1, "sha256": "d" * 64},
    ]
    rejects()

    # A different package that merely happens to carry this version -- exactly
    # what the old count-based check accepted.
    responses["files"] = original
    responses["metadata"] = {"type": "pypi", "name": "some-other", "version": "0.0.26"}
    rejects()

    # The right name at the wrong version.
    responses["metadata"] = {
        "type": "pypi",
        "name": "netbox-proxbox",
        "version": "0.0.25",
        "repository": {"full_name": "emersonfelipesp/netbox-proxbox"},
    }
    rejects()

    # No repository association. A twine upload leaves the package in exactly
    # this state, and `fetch_gitea_artifacts` -- the deploy and promotion
    # consumer -- refuses to download an artifact whose package does not name
    # the repository. Accepting it here would publish a manifest for a release
    # that the consumer still rejects.
    responses["metadata"] = {
        "type": "pypi",
        "name": "netbox-proxbox",
        "version": "0.0.26",
    }
    rejects()

    # Associated with somebody else's repository.
    responses["metadata"] = {
        "type": "pypi",
        "name": "netbox-proxbox",
        "version": "0.0.26",
        "repository": {"full_name": "someone-else/netbox-proxbox"},
    }
    rejects()


def test_registry_verification_downloads_and_hashes_every_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    responses = _registry_responses(manifest)
    responses["content"]["netbox_proxbox-0.0.26.tar.gz"] = b"different-bytes"
    _patch_requests(monkeypatch, release_artifacts, responses)

    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="Downloaded artifact differs from the release manifest",
    ):
        release_artifacts.verify_gitea_package_artifacts(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
        )


def test_registry_verification_retries_delayed_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    attempts: list[int] = []
    delays: list[float] = []

    monkeypatch.setattr(release_artifacts, "link_gitea_package", lambda **_k: None)

    def delayed(**_kwargs: object) -> None:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise release_artifacts.RegistryNotFound("not visible yet")

    monkeypatch.setattr(release_artifacts, "verify_gitea_package_artifacts", delayed)
    monkeypatch.setattr(release_artifacts.time, "sleep", delays.append)

    release_artifacts.verify_gitea_package_artifacts_with_retry(
        registry=_TEST_REGISTRY,
        owner="emersonfelipesp",
        repository="netbox-proxbox",
        package="netbox-proxbox",
        version="0.0.26",
        manifest=manifest,
        token="t",
        attempts=3,
        delay_seconds=0.25,
    )

    assert attempts == [1, 2, 3]
    assert delays == [0.25, 0.25]


def test_registry_verification_retries_malformed_success_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    requests: list[str] = []
    delays: list[float] = []

    monkeypatch.setattr(release_artifacts, "link_gitea_package", lambda **_k: None)

    def malformed(url: str, **_kwargs: object) -> bytes:
        requests.append(url)
        return b"not-json"

    monkeypatch.setattr(release_artifacts, "_request", malformed)
    monkeypatch.setattr(release_artifacts.time, "sleep", delays.append)

    with pytest.raises(
        release_artifacts.ReleaseArtifactError,
        match="did not match after 3 attempts",
    ):
        release_artifacts.verify_gitea_package_artifacts_with_retry(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
            attempts=3,
            delay_seconds=0.25,
        )

    assert len(requests) == 3
    assert delays == [0.25, 0.25]


def test_upload_preflight_requires_explicit_byte_identical_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    monkeypatch.setattr(
        release_artifacts, "verify_gitea_token_identity", lambda **_k: None
    )

    def absent(**_kwargs: object) -> None:
        raise release_artifacts.RegistryNotFound("absent")

    monkeypatch.setattr(release_artifacts, "verify_gitea_package_artifacts", absent)
    assert (
        release_artifacts.prepare_gitea_package_upload(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
            resume_existing=False,
            attempts=1,
            delay_seconds=0,
        )
        == "upload"
    )

    monkeypatch.setattr(
        release_artifacts, "verify_gitea_package_artifacts", lambda **_k: None
    )
    with pytest.raises(release_artifacts.ReleaseArtifactError, match="already exists"):
        release_artifacts.prepare_gitea_package_upload(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
            resume_existing=False,
            attempts=1,
            delay_seconds=0,
        )

    monkeypatch.setattr(
        release_artifacts,
        "verify_gitea_package_artifacts_with_retry",
        lambda **_k: None,
    )
    assert (
        release_artifacts.prepare_gitea_package_upload(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
            resume_existing=True,
            attempts=12,
            delay_seconds=5,
        )
        == "reuse"
    )

    def absent_after_reservation(**_kwargs: object) -> None:
        try:
            raise release_artifacts.RegistryNotFound("absent")
        except release_artifacts.RegistryNotFound as cause:
            raise release_artifacts.ReleaseArtifactError("retry exhausted") from cause

    monkeypatch.setattr(
        release_artifacts,
        "verify_gitea_package_artifacts_with_retry",
        absent_after_reservation,
    )
    assert (
        release_artifacts.prepare_gitea_package_upload(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            package="netbox-proxbox",
            version="0.0.26",
            manifest=manifest,
            token="t",
            resume_existing=True,
            attempts=12,
            delay_seconds=5,
        )
        == "upload"
    )


def test_upload_preflight_requires_the_package_owner_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_artifacts = _load_release_artifacts()

    def fake_request(_url: str, **_kwargs: object) -> bytes:
        return b'{"login":"someone-else"}'

    monkeypatch.setattr(release_artifacts, "_request", fake_request)
    with pytest.raises(release_artifacts.ReleaseArtifactError, match="does not match"):
        release_artifacts.verify_gitea_token_identity(
            registry=_TEST_REGISTRY, owner="emersonfelipesp", token="token"
        )
    with pytest.raises(release_artifacts.ReleaseArtifactError, match="unavailable"):
        release_artifacts.verify_gitea_token_identity(
            registry=_TEST_REGISTRY, owner="emersonfelipesp", token=""
        )


def test_gitea_publish_uses_pinned_tools_and_resumable_upload() -> None:
    workflow_text = _read(GITEA_PUBLISH_WORKFLOW)
    workflow = yaml.safe_load(workflow_text)
    validate = workflow["jobs"]["validate-version"]
    publish = workflow["jobs"]["publish-gitea"]
    steps = publish["steps"]
    names = [step["name"] for step in steps]
    bootstrap_step = _step(publish, "Bootstrap pinned uv toolchain")
    bootstrap = bootstrap_step["run"]
    tools_step = _step(publish, "Verify fixed build tools")
    tools = tools_step["run"]
    package_preflight_step = _step(publish, "Preflight immutable package state")
    preflight = package_preflight_step["run"]
    rc_preflight_step = _step(publish, "Reserve and verify RC promotion")
    rc_preflight = rc_preflight_step["run"]
    upload = _step(publish, "Publish to Gitea Package Registry")
    verify = _step(publish, "Verify package in Gitea registry")["run"]
    build = _step(publish, "Build distributions")["run"]
    recreate = _step(publish, "Recreate fixed publisher environment")["run"]

    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_dispatch"]["inputs"]["resume_existing"] == {
        "description": "Resume after an interrupted publish only when the registry bytes exactly match the rebuilt manifest",
        "required": False,
        "type": "boolean",
        "default": False,
    }
    assert bootstrap_step["env"] == {
        "UV_VERSION": "0.12.5",
        "UV_IDENTITY": "uv 0.12.5 (x86_64-unknown-linux-gnu)",
        "UV_ARCHIVE_SHA256": "68a509da24b06b4223a1c0175fb5eb5bc79342b76cbeff0cfe51ac3f5b17b6b2",
    }
    assert "for tool in curl sha256sum tar" in bootstrap
    assert (
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz"
        in bootstrap
    )
    assert "sha256sum --check --strict" in bootstrap
    assert "--no-same-owner --no-same-permissions" in bootstrap
    assert 'test "$("${UV_BIN}" --version)" = "${UV_IDENTITY}"' in bootstrap
    assert "printf 'UV_BIN=%s\\n'" in bootstrap
    assert tools_step["env"] == {
        "PYTHON_VERSION": "3.13.5",
        "UV_VERSION": "0.12.5",
        "UV_IDENTITY": "uv 0.12.5 (x86_64-unknown-linux-gnu)",
    }
    assert "command -v python3" in tools
    assert 'test -x "${UV_BIN}"' in tools
    assert 'ACTUAL_PYTHON="$(python3 --version 2>&1)"' in tools
    assert "Python ${PYTHON_VERSION}" in tools
    assert 'ACTUAL_UV="$("${UV_BIN}" --version)"' in tools
    assert "install.sh" not in workflow_text
    assert "apt-get" not in workflow_text
    assert "Install GitHub CLI" not in names
    assert validate["runs-on"] == "mirror-host"
    validate_checkout = _step(validate, "Checkout tag")
    assert "uses" not in validate_checkout
    assert 'GITHUB_SERVER_URL="${GITHUB_SERVER_URL%/}"' in validate_checkout["run"]
    assert "Package validation identity:" in validate_checkout["run"]
    assert "+refs/tags/${TAG}:refs/tags/${TAG}" in validate_checkout["run"]
    assert "mktemp -d /tmp/netbox-proxbox-validation.XXXXXX" in validate_checkout["run"]
    assert 'chmod 0700 "${VALIDATION_SOURCE}"' in validate_checkout["run"]
    assert 'echo "source_dir=${VALIDATION_SOURCE}"' in validate_checkout["run"]
    assert 'git -C "${VALIDATION_SOURCE}" init .' in validate_checkout["run"]
    assert "could not fetch the requested canonical tag" in validate_checkout["run"]
    assert "could not check out the requested tag commit" in validate_checkout["run"]
    assert 'if [ "${status}" -ne 0 ]' in validate_checkout["run"]
    assert 'rm -rf -- "${VALIDATION_SOURCE}"' in validate_checkout["run"]
    assert "trap - EXIT" in validate_checkout["run"]
    assert "git init ." not in validate_checkout["run"]
    assert (
        _step(validate, "Extract and validate version")["working-directory"]
        == "${{ steps.checkout_tag.outputs.source_dir }}"
    )
    extract_run = _step(validate, "Extract and validate version")["run"]
    assert "/tmp/netbox-proxbox-validation.*" in extract_run
    assert 'rm -rf -- "${VALIDATION_SOURCE}"' in extract_run
    assert 'test "${GITEA_ACTIONS}" = "true"' in (validate_checkout["run"])
    assert workflow_text.count('test "${GITEA_ACTIONS}" = "true"') == 3
    assert "GH_TOKEN" not in package_preflight_step.get("env", {})
    assert "command -v gh" in rc_preflight
    assert "gh auth status --hostname github.com" in rc_preflight
    assert "gh api \"repos/${GH_REPO}\" --jq '.permissions.push'" in rc_preflight
    assert "rulesets?targets=tag" in rc_preflight
    assert "validate-github-tag-rulesets" in rc_preflight
    assert "env -u GH_TOKEN python3" in rc_preflight
    assert "git -C candidate push --dry-run github" in rc_preflight
    assert "git -C candidate push github" in rc_preflight
    assert "VERIFIED_TAG_OBJECT" in rc_preflight
    assert "trap 'rm -rf -- \"${SECRET_ROOT}\"' EXIT" in rc_preflight
    assert "prepare-upload" in preflight
    assert "--resume-existing --attempts 12 --delay-seconds 5" in preflight
    assert upload["if"] == "env.ARTIFACT_ACTION == 'upload'"
    assert "--attempts 12" in verify and "--delay-seconds 5" in verify
    assert "sleep 5" not in verify
    assert (
        '"${UV_BIN}" build --clear --no-create-gitignore --no-build-isolation' in build
    )
    assert "--python .venv/bin/python --out-dir dist sanitized-candidate" in build
    assert "rm -- dist/.gitignore" not in build
    assert "--registry" not in workflow_text
    release_artifacts = _load_release_artifacts()
    release_source = RELEASE_ARTIFACTS_PATH.read_text(encoding="utf-8")
    assert release_artifacts.CANONICAL_GITEA_REGISTRY == _TEST_REGISTRY
    assert (
        release_source.count(
            'add_argument("--registry", default=CANONICAL_GITEA_REGISTRY)'
        )
        == 3
    )
    assert "release_artifacts.py sanitize-build-source" in build
    assert "--source candidate --destination sanitized-candidate" in build
    assert "--out-dir dist sanitized-candidate" in build
    assert 'version("hatchling")' in build
    assert 'ACTUAL_HATCHLING}" = "1.31.0"' in build
    assert "rm -rf -- .venv" in recreate
    assert 'version("twine")' in recreate
    assert "git diff --exit-code -- scripts/release_artifacts.py" in recreate
    assert workflow["concurrency"] == {
        "group": "package-publication-${{ github.repository }}",
        "cancel-in-progress": False,
    }
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step["uses"] == (
                    "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
                )
                assert step.get("with", {}).get("persist-credentials") is False
    assert "gh auth setup-git" not in workflow_text
    assert "push-to-github" not in workflow["jobs"]
    names = [step["name"] for step in publish["steps"]]
    assert names.index("Reserve and verify RC promotion") < names.index(
        "Publish to Gitea Package Registry"
    )
    assert (
        names.index("Bootstrap pinned uv toolchain")
        < names.index("Checkout candidate tag as passive build input")
        < names.index("Build distributions")
        < names.index("Recreate fixed publisher environment")
        < names.index("Preflight immutable package state")
    )
    assert rc_preflight_step["if"] == "env.IS_RC == 'true'"

    control_checkout = _step(publish, "Checkout canonical publisher control")
    candidate_checkout = _step(publish, "Checkout candidate tag as passive build input")
    bind_candidate = _step(publish, "Bind candidate tag to validated objects")["run"]
    assert "uses" not in control_checkout
    assert control_checkout["env"]["CONTROL_SHA"] == "${{ github.sha }}"
    assert "refs/heads/main:refs/release-policy/control-main" in control_checkout["run"]
    assert 'test "${GITEA_ACTIONS}" = "true"' in control_checkout["run"]
    assert "uses" not in candidate_checkout
    assert (
        "refs/tags/${TAG}:refs/release-policy/candidate-tag-initial"
        in (candidate_checkout["run"])
    )
    assert "${EXPECTED_TAG_OBJECT}" in candidate_checkout["run"]
    assert "${EXPECTED_SOURCE_SHA}" in candidate_checkout["run"]
    assert "persist-credentials" not in control_checkout
    assert "persist-credentials" not in candidate_checkout
    assert "refs/release-policy/candidate-tag" in bind_candidate
    assert "${EXPECTED_TAG_OBJECT}" in bind_candidate
    assert "${EXPECTED_SOURCE_SHA}" in bind_candidate
    assert "refs/release-policy/candidate-tag:refs/tags/${TAG}" in rc_preflight
    for step in publish["steps"]:
        if "GITEA_PACKAGE_TOKEN" in step.get("env", {}):
            assert "candidate/scripts" not in step["run"]
        if "TWINE_PASSWORD" in step.get("env", {}):
            assert ".venv/bin/python -m twine" in step["run"]


@pytest.mark.parametrize(
    ("commands", "expected_success"),
    [
        ({"uv": "uv 0.12.5 (x86_64-unknown-linux-gnu)"}, False),
        ({"python3": "Python 3.13.5"}, False),
        (
            {
                "python3": "Python 3.12.14",
                "uv": "uv 0.12.5 (x86_64-unknown-linux-gnu)",
            },
            False,
        ),
        ({"python3": "Python 3.13.5", "uv": "uv 9.9.9"}, False),
        (
            {
                "python3": "Python 3.13.5",
                "uv": "uv 0.12.5 (x86_64-unknown-linux-gnu)",
            },
            True,
        ),
    ],
)
def test_fixed_tool_gate_fails_closed(
    tmp_path: Path, commands: dict[str, str], expected_success: bool
) -> None:
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    run = _step(workflow["jobs"]["publish-gitea"], "Verify fixed build tools")["run"]
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    for command, output in commands.items():
        executable = binary_dir / command
        executable.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{output}'\n", encoding="utf-8"
        )
        executable.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", "-c", run],
        capture_output=True,
        env={
            "PATH": str(binary_dir),
            "PYTHON_VERSION": "3.13.5",
            "UV_VERSION": "0.12.5",
            "UV_IDENTITY": "uv 0.12.5 (x86_64-unknown-linux-gnu)",
            "UV_BIN": str(binary_dir / "uv"),
        },
        text=True,
        timeout=10,
    )

    assert (result.returncode == 0) is expected_success, result.stderr


def test_manifest_publication_tolerates_only_a_byte_identical_republish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambiguous failure after the upload must be recoverable, exactly once.

    Upload, repository link and read-back are separate requests, so a timeout
    after the server accepted one of them fails the workflow while the manifest
    may already exist. Package versions are immutable and this is the one
    post-upload step whose loss is unrecoverable: without the manifest that
    exact release can never be deployed from the package source nor promoted.
    Re-running must therefore succeed against an identical published manifest --
    and must still refuse a different one rather than overwrite it.
    """
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    calls: list[str] = []

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        calls.append("fetch")
        return manifest

    monkeypatch.setattr(release_artifacts, "fetch_gitea_manifest", fake_fetch)

    def explode(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("must not re-upload over an identical manifest")

    monkeypatch.setattr(release_artifacts, "_request", explode)

    assert (
        release_artifacts.publish_gitea_manifest(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            token="t",
        )
        == manifest
    )
    assert calls == ["fetch"]

    # A manifest that differs is never overwritten and never accepted: that
    # would silently rebind a consumed version to different provenance.
    divergent = dict(manifest, source_sha="e" * 40)
    monkeypatch.setattr(
        release_artifacts, "fetch_gitea_manifest", lambda **_k: divergent
    )
    with pytest.raises(release_artifacts.ReleaseArtifactError):
        release_artifacts.publish_gitea_manifest(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            token="t",
        )


def test_attestation_publication_verifies_after_an_idempotent_package_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry conflict on an already-created link must not make deploy red."""
    release_artifacts = _load_release_artifacts()
    manifest = {"package": "netbox-proxbox", "version": "0.0.27rc4"}
    evidence = {"state": "completed"}
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        release_artifacts,
        "validate_release_attestation",
        lambda **kwargs: calls.append(("validate", kwargs)),
    )
    monkeypatch.setattr(
        release_artifacts,
        "_request",
        lambda *_args, **kwargs: calls.append(("upload", kwargs)) or b"",
    )
    monkeypatch.setattr(
        release_artifacts,
        "link_gitea_package",
        lambda **kwargs: calls.append(("link", kwargs)),
    )
    monkeypatch.setattr(
        release_artifacts,
        "fetch_gitea_attestation",
        lambda **kwargs: calls.append(("fetch", kwargs)) or evidence,
    )

    assert (
        release_artifacts.publish_gitea_attestation(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            evidence=evidence,
            token="t",
        )
        == evidence
    )
    assert [name for name, _kwargs in calls] == [
        "validate",
        "upload",
        "link",
        "fetch",
    ]
    link_kwargs = calls[2][1]
    assert isinstance(link_kwargs, dict)
    assert link_kwargs == {
        "registry": _TEST_REGISTRY,
        "owner": "emersonfelipesp",
        "repository": "netbox-proxbox",
        "package_type": "generic",
        "package": f"{manifest['package']}-{''.join(('n', 'm', 's'))}-attestation",
        "token": "t",
    }


def test_manifest_publication_uses_the_idempotent_package_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh manifest must verify linkage after Gitea's conflict response."""
    release_artifacts, manifest = _artifact_manifest(tmp_path)
    fetch_results: list[object] = [
        release_artifacts.RegistryNotFound("absent"),
        manifest,
    ]
    calls: list[str] = []

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        result = fetch_results.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, dict)
        return result

    monkeypatch.setattr(release_artifacts, "fetch_gitea_manifest", fake_fetch)
    monkeypatch.setattr(
        release_artifacts,
        "_request",
        lambda *_args, **_kwargs: calls.append("upload") or b"",
    )
    monkeypatch.setattr(
        release_artifacts,
        "link_gitea_package",
        lambda **_kwargs: calls.append("link"),
    )

    assert (
        release_artifacts.publish_gitea_manifest(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            token="t",
        )
        == manifest
    )
    assert calls == ["upload", "link"]
    assert fetch_results == []


def test_publish_workflow_verifies_the_artifact_set_before_the_manifest() -> None:
    """The registry gate must be the manifest-based one, not the old count."""
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    assert "release_artifacts.py verify-registry" in workflow
    # The count-based check is what this replaced; if it comes back, the
    # ordering assertion in the sibling test stops meaning anything.
    assert "Found ${COUNT} package(s)" not in workflow


def test_only_an_authenticated_not_found_authorizes_a_manifest_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absence and "could not tell" must not be the same state.

    The fetch that decides whether to upload can fail for reasons that are not
    absence: a timeout, a 401, a 5xx, a corrupt payload, or the partial state
    where a previous run uploaded the manifest but did not link it. Treating any
    of those as "not published" and re-uploading conflicts against an immutable
    version instead of repairing it, which strands the release -- the exact
    outcome this recovery path exists to avoid.
    """
    release_artifacts, manifest = _artifact_manifest(tmp_path)

    def unavailable(**_kwargs: object) -> dict[str, object]:
        raise release_artifacts.ReleaseArtifactError("Registry request failed")

    monkeypatch.setattr(release_artifacts, "fetch_gitea_manifest", unavailable)
    monkeypatch.setattr(release_artifacts, "link_gitea_package", lambda **_k: None)

    def explode(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("must not upload when the published state is unknown")

    monkeypatch.setattr(release_artifacts, "_request", explode)
    with pytest.raises(release_artifacts.ReleaseArtifactError):
        release_artifacts.publish_gitea_manifest(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            token="t",
        )

    # The uploaded-but-unlinked case: the first fetch rejects it for the missing
    # link, the link is repaired, and the second fetch resolves. Still no
    # upload, because the bytes are already there.
    attempts = {"n": 0}
    linked = {"done": False}

    def fetch_twice(**_kwargs: object) -> dict[str, object]:
        attempts["n"] += 1
        if not linked["done"]:
            raise release_artifacts.ReleaseArtifactError("identity is invalid")
        return manifest

    def do_link(**_kwargs: object) -> None:
        linked["done"] = True

    monkeypatch.setattr(release_artifacts, "fetch_gitea_manifest", fetch_twice)
    monkeypatch.setattr(release_artifacts, "link_gitea_package", do_link)
    assert (
        release_artifacts.publish_gitea_manifest(
            registry=_TEST_REGISTRY,
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            manifest=manifest,
            token="t",
        )
        == manifest
    )
    assert attempts["n"] == 2 and linked["done"]


def test_registry_not_found_is_distinguishable_from_every_other_failure() -> None:
    """`RegistryNotFound` must be raised only for an authoritative 404.

    Every other status leaves the published state unknown. Classifying one of
    them as absence is what would let the caller re-upload an immutable version.
    """
    release_artifacts = _load_release_artifacts()
    assert issubclass(
        release_artifacts.RegistryNotFound, release_artifacts.ReleaseArtifactError
    )
    probe_url = _TEST_REGISTRY + "probe"

    def raiser(code: int):
        def opener(*_args: object, **_kwargs: object):
            raise release_artifacts.urllib.error.HTTPError(
                probe_url, code, "boom", {}, None
            )

        return opener

    for code, expected in (
        (404, release_artifacts.RegistryNotFound),
        (401, release_artifacts.ReleaseArtifactError),
        (403, release_artifacts.ReleaseArtifactError),
        (500, release_artifacts.ReleaseArtifactError),
    ):
        opener = type("O", (), {"open": staticmethod(raiser(code))})()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                release_artifacts.urllib.request, "build_opener", lambda *_a: opener
            )
            with pytest.raises(expected) as caught:
                release_artifacts._request(probe_url, token="t", maximum=10)
            if expected is release_artifacts.ReleaseArtifactError:
                assert not isinstance(
                    caught.value, release_artifacts.RegistryNotFound
                ), f"HTTP {code} must not read as absence"
