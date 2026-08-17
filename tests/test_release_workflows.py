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


def test_gitea_tag_workflow_builds_only_a_release_control_request() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)

    assert set(parsed["jobs"]) == {"validate-source", "build-request"}
    assert all(
        job["runs-on"] == "ci-release-netbox-proxbox" for job in parsed["jobs"].values()
    )
    assert "refs/heads/develop:refs/remotes/gitea/release-develop" in workflow
    assert workflow.count("actions/checkout@") == 1
    assert "release-manifest.json" in workflow
    assert "scripts/gitea_ci_gate.py" in workflow
    assert "/commits/${SOURCE_SHA}/statuses" not in workflow
    assert (
        "actions/upload-artifact@c6a3b2bd78b3985e4b2f15397fec357f0fd808de" in workflow
    )
    assert "actions/download-artifact@" not in workflow
    assert "astral-sh/setup-uv@" not in workflow
    assert "RUNNER_TOOL_CACHE" not in workflow
    assert "UV_MANAGED_PYTHON" not in workflow
    assert "mirror-host" not in workflow
    assert "packages: write" not in workflow
    assert "secrets." not in workflow
    assert "PKG_TOKEN" not in workflow
    assert "GH_MIRROR_TOKEN" not in workflow
    assert "release-publisher" not in workflow
    assert "twine upload" not in workflow
    assert "gh release create" not in workflow
    assert "git push" not in workflow
    assert "/api/packages/" not in workflow
    assert (
        workflow.count(
            "https://github.com/astral-sh/uv/releases/download/0.11.28/"
            "uv-x86_64-unknown-linux-gnu.tar.gz"
        )
        == 1
    )
    assert (
        workflow.count(
            "e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224"
        )
        == 1
    )
    assert workflow.count("sha256sum --check --strict") == 6
    assert workflow.count("UV_PYTHON_INSTALL_DIR=%s") == 1
    assert workflow.count('test ! -L "$BOOTSTRAP_') == 3
    assert workflow.count("--no-config") == 2
    assert workflow.count("--managed-python") == 2
    assert workflow.count("--no-python-downloads") == 1
    assert '"$BUILD_ROOT/venv/bin/python" -m build --no-isolation' in workflow
    assert "uvx --from twine" not in workflow


def test_token_bearing_ci_gate_uses_the_pinned_reviewed_script() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)
    policy_run = _step(
        parsed["jobs"]["validate-source"],
        "Bind tag, version, canonical develop, and successful CI",
    )["run"]
    expected_digest = hashlib.sha256(CI_GATE_PATH.read_bytes()).hexdigest()
    isolated_invocation = "python3 -I scripts/gitea_ci_gate.py"

    assert expected_digest == (
        "1e7f4270ae0d9abc18ea674c71a682a734f448628895e96915fb808d5da41f11"
    )
    assert 'python3 -I - "$VERSION"' in policy_run
    assert "test -f scripts/gitea_ci_gate.py" in policy_run
    assert "test ! -L scripts/gitea_ci_gate.py" in policy_run
    assert expected_digest in policy_run
    assert "scripts/gitea_ci_gate.py | sha256sum --check --strict" in policy_run
    assert isolated_invocation in policy_run
    assert policy_run.index(expected_digest) < policy_run.index(isolated_invocation)
    assert policy_run.index("sha256sum --check --strict") < policy_run.index(
        isolated_invocation
    )


def test_release_control_request_binds_exact_repository_run_and_artifacts() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)
    build_job = parsed["jobs"]["build-request"]
    build_source = yaml.safe_dump(build_job)
    upload_step = build_job["steps"][-1]
    completion_run = _step(build_job, "Obtain supervisor-signed completion evidence")[
        "run"
    ]
    assert isinstance(completion_run, str)
    completion_source = completion_run.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    completion_tree = ast.parse(completion_source)
    completion_imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(completion_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert build_job["needs"] == "validate-source"
    assert build_job["name"] == (
        "Build exact publisher-credential-free release-control request"
    )
    assert upload_step["with"] == {
        "name": "release-control-request",
        "path": (
            "release-transfer/*.whl\n"
            "release-transfer/*.tar.gz\n"
            "release-transfer/release-manifest.json\n"
            "release-transfer/release-request.json\n"
            "release-transfer/runner-completion-attestation.json\n"
            "release-transfer/runner-completion-attestation.sig\n"
        ),
        "if-no-files-found": "error",
        "retention-days": 1,
        "compression-level": 0,
    }
    assert '"repository_id": 38' in workflow
    assert '"owner": "emersonfelipesp"' in workflow
    assert '"repository": "netbox-proxbox"' in workflow
    assert '"schema": 1' in workflow
    assert '"workflow_sha256"' in workflow
    assert '"release_manifest_sha256"' in workflow
    assert '"initiating_run_id"' in workflow
    assert '"initiating_run_attempt"' in workflow
    assert "release-request.json" in workflow
    assert (
        'test "$(find release-transfer -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 4'
        in workflow
    )
    assert (
        'test "$(find release-transfer -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 6'
        in workflow
    )
    assert "/usr/local/bin/nmc-release-attestation-client" in workflow
    assert (
        "2b0bee25d755f284b5e8eee3b8a84536825328913040c8757374efe51c57f75f" in workflow
    )
    assert "os.O_NOFOLLOW" in workflow
    assert "pass_fds=(snapshot,)" in workflow
    assert 'os.memfd_create("nmc-release-client", flags)' in workflow
    assert "fcntl.fcntl(snapshot, 1033, seals)" in workflow
    assert {"ctypes", "fcntl", "hashlib", "os", "stat", "subprocess", "sys"} <= (
        completion_imports
    )
    compile(completion_source, "publish-gitea-completion", "exec")
    assert '"--public-key"' in workflow
    assert "runner-completion-attestation.json" in workflow
    assert "runner-completion-attestation.sig" in workflow
    assert "secrets." not in build_source
    assert build_source.count("github.token") == 1
    assert "actions/checkout@" not in build_source
    assert "https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git" in build_source
    assert (
        'git fetch --quiet --force --no-tags --depth=1 origin "$SOURCE_SHA"'
        in build_source
    )
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in build_source
    assert "export GIT_CONFIG_NOSYSTEM=1" in build_source
    assert "export GIT_CONFIG_GLOBAL=/dev/null" in build_source
    assert 'test -z "$(find . -mindepth 1 -maxdepth 1 -print -quit)"' in build_source
    assert (
        'test -z "$(git status --porcelain=v1 --untracked-files=all)"' in build_source
    )


def test_gitea_candidate_build_isolated_from_runner_tokens() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)
    validate_source = yaml.safe_dump(parsed["jobs"]["validate-source"])
    build_source = yaml.safe_dump(parsed["jobs"]["build-request"])

    assert "permissions" not in parsed
    assert parsed["jobs"]["validate-source"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert parsed["jobs"]["build-request"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert validate_source.count("github.token") == 2
    assert "GITEA_API_TOKEN" in validate_source
    assert build_source.count("github.token") == 1
    assert build_source.count("GITEA_API_TOKEN") == 1
    boundary_step = _step(
        parsed["jobs"]["build-request"],
        "Build artifacts across a token-free UID boundary",
    )
    boundary_run = boundary_step["run"]
    boundary_code = boundary_run.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    compile(boundary_code, "publish-gitea-token-boundary", "exec")

    assert 'test -z "${GITHUB_TOKEN:-}"' in boundary_run
    assert 'test -z "${GITEA_TOKEN:-}"' in boundary_run
    assert 'test -z "${ACTIONS_RUNTIME_TOKEN:-}"' in boundary_run
    assert 'test -z "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}"' in boundary_run
    assert 'test ! -r "/proc/$BOUNDARY_PARENT_PID/environ"' in boundary_run
    assert 'test ! -L "$BUILD_ROOT"' in boundary_run
    assert "build_root.exists() or build_root.is_symlink()" in boundary_code
    assert "os.setgroups([])" in boundary_code
    assert "os.setgid(BUILD_GID)" in boundary_code
    assert "os.setuid(BUILD_UID)" in boundary_code
    assert "preexec_fn=drop_privileges" in boundary_code
    assert "start_new_session=True" in boundary_code
    assert "kill_remaining_build_processes()" in boundary_code
    assert "stdout=subprocess.PIPE" in boundary_code
    assert "stderr=subprocess.STDOUT" in boundary_code
    assert "selectors.DefaultSelector()" in boundary_code
    assert "base64.b64encode" in boundary_code
    assert "output_limit = 1024 * 1024" in boundary_code
    assert "deadline = time.monotonic() + 900" in boundary_code
    assert "resource.RLIMIT_AS" in boundary_code
    assert "resource.RLIMIT_CPU" in boundary_code
    assert "restrict_writes_to_build_root(build_root)" in boundary_code
    assert "Landlock ABI 3 or newer is required" in boundary_code
    assert "Landlock syscall mapping requires x86-64" in boundary_code
    assert "write_file = 1 << 1" in boundary_code
    assert "truncate = 1 << 14" in boundary_code
    assert "build_tree_usage()" in boundary_code
    assert "build_process_usage()" in boundary_code
    assert "available_filesystem_bytes(build_root)" in boundary_code
    assert "consumed_bytes > disk_limit" in boundary_code
    assert "process_cpu_ticks(stat_row)" in boundary_code
    assert "verify_kernel_quotas(build_root)" in boundary_code
    assert 'mount_rows != ["tmpfs"]' in boundary_code
    assert 'cgroup_root / "cpu.max"' in boundary_code
    assert 'cgroup_root / "memory.max"' in boundary_code
    assert 'cgroup_root / "memory.swap.max"' in boundary_code
    assert 'cgroup_root / "memory.current"' in boundary_code
    assert 'cgroup_root / "memory.swap.current"' in boundary_code
    assert 'raise SystemExit("Hard cgroup policy must disable swap")' in boundary_code
    assert "memory_bytes > CGROUP_MEMORY_MAX" in boundary_code
    assert 'cgroup_root / "pids.max"' in boundary_code
    assert "TMPFS_BYTES_MAX = 1024 * 1024 * 1024" in boundary_code
    assert "TMPFS_INODES_MAX = 50000" in boundary_code
    assert 'raise SystemExit("Cannot inspect reserved build UID")' in boundary_code
    assert "::set-env name=NMC_RELEASE_BOUNDARY_INJECTED::yes" in boundary_code
    assert "::add-path::/tmp/nmc-release-boundary-injected" in boundary_code
    bind_run = _step(
        parsed["jobs"]["build-request"],
        "Bind exact artifacts into the control request",
    )["run"]
    assert 'test -z "${NMC_RELEASE_BOUNDARY_INJECTED:-}"' in bind_run
    assert "*:/tmp/nmc-release-boundary-injected:*) exit 1" in bind_run
    safe_env = boundary_code.split("safe_env = {", 1)[1].split("\n}", 1)[0]
    assert "GITHUB_TOKEN" not in safe_env
    assert "GITEA_TOKEN" not in safe_env
    assert "ACTIONS_RUNTIME_TOKEN" not in safe_env
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" not in safe_env
    assert "python3 -I -" in boundary_run
    assert "persist-credentials: false" in validate_source
    assert "persist-credentials: false" not in build_source


def test_release_runner_gate_is_pinned_and_precedes_candidate_execution() -> None:
    workflow = _read(GITEA_PUBLISH_WORKFLOW)
    parsed = yaml.safe_load(workflow)
    runner_gate_sha256 = hashlib.sha256(RUNNER_GATE_PATH.read_bytes()).hexdigest()
    acceptance_sha256 = hashlib.sha256(RUNNER_ACCEPTANCE_PATH.read_bytes()).hexdigest()
    acceptance = json.loads(RUNNER_ACCEPTANCE_PATH.read_bytes())

    assert runner_gate_sha256 == (
        "c643ee91c8230f9701bed65b80c206852550c8a197becacaa194db1a60910f06"
    )
    assert acceptance_sha256 == (
        "465cd4fbf16603cfb5412aa70a6ca0f14f16bfe63c3512fbaa6e65d5f86e9dcd"
    )
    assert workflow.count(runner_gate_sha256) == 2
    assert workflow.count(acceptance_sha256) == 2
    assert acceptance["runner_id"] == 0
    assert acceptance["runner_name"] == ""
    assert acceptance["validation_runner_id"] == 0
    assert acceptance["validation_runner_name"] == ""
    assert acceptance["runner_scope_sha256"] == "0" * 64
    assert acceptance["runtime_attestation_sha256"] == "0" * 64
    assert acceptance["network_attestation_sha256"] == "0" * 64
    assert acceptance["attestation_public_key_sha256"] == "0" * 64
    assert acceptance["runtime_image_digest"] == "0" * 64
    assert acceptance["supervisor_policy_sha256"] == "0" * 64
    assert acceptance["registered_labels"] == [
        "ci-release-netbox-proxbox",
    ]
    build_steps = parsed["jobs"]["build-request"]["steps"]
    gate_index = next(
        index
        for index, step in enumerate(build_steps)
        if step["name"].startswith("Prove exact accepted release runner")
    )
    boundary_index = next(
        index
        for index, step in enumerate(build_steps)
        if step["name"] == "Build artifacts across a token-free UID boundary"
    )
    assert gate_index < boundary_index


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
        "run_id": 12,
        "runner_id": 41,
        "runner_name": "ci-release-netbox-proxbox-runner",
        "runner_scope_sha256": acceptance["runner_scope_sha256"],
        "runtime_attestation_sha256": acceptance["runtime_attestation_sha256"],
        "runtime_image_digest": acceptance["runtime_image_digest"],
        "schema": 1,
        "source_sha": "a" * 40,
        "supervisor_policy_sha256": acceptance["supervisor_policy_sha256"],
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
    }
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_bytes(gate._canonical_json(acceptance))
    monkeypatch.setattr(gate, "_verify_live_attestation", lambda **_kwargs: "0" * 64)
    jobs = (
        (
            gate.VALIDATION_JOB_NAME,
            acceptance["validation_runner_id"],
            acceptance["validation_runner_name"],
        ),
        (
            gate.BUILD_JOB_NAMES["netbox-proxbox"],
            acceptance["runner_id"],
            acceptance["runner_name"],
        ),
    )
    for index, (job_name, runner_id, runner_name) in enumerate(jobs, start=1):
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


def test_candidate_process_cpu_accounting_includes_reaped_descendants() -> None:
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    boundary_run = _step(
        workflow["jobs"]["build-request"],
        "Build artifacts across a token-free UID boundary",
    )["run"]
    boundary_code = boundary_run.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    tree = ast.parse(boundary_code)
    cpu_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "process_cpu_ticks"
    )
    namespace: dict[str, object] = {}
    exec(
        compile(
            ast.Module(body=[cpu_function], type_ignores=[]),
            "publish-gitea-process-accounting",
            "exec",
        ),
        namespace,
    )
    process_cpu_ticks = namespace["process_cpu_ticks"]

    assert callable(process_cpu_ticks)
    assert (
        process_cpu_ticks("123 (candidate name) R 1 2 3 4 5 6 7 8 9 10 11 12 13 14")
        == 50
    )
    with pytest.raises(ValueError, match="Malformed process stat"):
        process_cpu_ticks("malformed")


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


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock requires Linux")
def test_candidate_write_boundary_rejects_shared_filesystem_writes(
    tmp_path: Path,
) -> None:
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    boundary_run = _step(
        workflow["jobs"]["build-request"],
        "Build artifacts across a token-free UID boundary",
    )["run"]
    boundary_code = boundary_run.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    tree = ast.parse(boundary_code)
    boundary_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "restrict_writes_to_build_root"
    )
    isolated_code = ast.unparse(
        ast.Module(
            body=[
                ast.Import(names=[ast.alias(name="ctypes")]),
                ast.Import(names=[ast.alias(name="errno")]),
                ast.Import(names=[ast.alias(name="os")]),
                ast.Import(names=[ast.alias(name="struct")]),
                ast.Import(names=[ast.alias(name="sys")]),
                ast.ImportFrom(
                    module="pathlib",
                    names=[ast.alias(name="Path")],
                    level=0,
                ),
                boundary_function,
            ],
            type_ignores=[],
        )
    )
    allowed_root = tmp_path / "allowed"
    denied_root = tmp_path / "denied"
    allowed_root.mkdir()
    denied_root.mkdir()
    probe = (
        isolated_code
        + "\nallowed = Path(sys.argv[1])\n"
        + "denied = Path(sys.argv[2])\n"
        + "restrict_writes_to_build_root(allowed)\n"
        + "(allowed / 'allowed.txt').write_text('ok', encoding='utf-8')\n"
        + "try:\n"
        + "    (denied / 'denied.txt').write_text('bad', encoding='utf-8')\n"
        + "except PermissionError:\n"
        + "    pass\n"
        + "else:\n"
        + "    raise SystemExit('Landlock allowed an out-of-bound write')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(allowed_root), str(denied_root)],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and "OSError: [Errno 95]" in result.stderr:
        pytest.skip("Landlock is disabled in this test sandbox")
    assert result.returncode == 0, result.stderr
    assert (allowed_root / "allowed.txt").read_text(encoding="utf-8") == "ok"
    assert not (denied_root / "denied.txt").exists()


def _artifact_handoff_code() -> str:
    parsed = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    bind_run = _step(
        parsed["jobs"]["build-request"],
        "Bind exact artifacts into the control request",
    )["run"]
    return bind_run.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


def test_artifact_handoff_copies_only_exact_regular_files(tmp_path: Path) -> None:
    handoff_code = _artifact_handoff_code()
    compile(handoff_code, "publish-gitea-artifact-handoff", "exec")
    dist_root = tmp_path / "dist"
    dist_root.mkdir()
    wheel = dist_root / "netbox_proxbox-0.0.24-py3-none-any.whl"
    sdist = dist_root / "netbox_proxbox-0.0.24.tar.gz"
    manifest = tmp_path / "release-manifest.json"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    manifest.write_bytes(b"{}\n")
    transfer = tmp_path / "transfer"

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(dist_root),
            str(manifest),
            str(transfer),
            "0.0.24",
        ],
        check=False,
        capture_output=True,
        input=handoff_code,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert {path.name: path.read_bytes() for path in transfer.iterdir()} == {
        wheel.name: b"wheel",
        sdist.name: b"sdist",
        manifest.name: b"{}\n",
    }


def test_artifact_handoff_rejects_noncanonical_control_filename(
    tmp_path: Path,
) -> None:
    handoff_code = _artifact_handoff_code()
    dist_root = tmp_path / "dist"
    dist_root.mkdir()
    (dist_root / "netbox_proxbox-0.0.24-py3-none-any.whl").write_bytes(b"wheel")
    control_name = "netbox_proxbox-0.0.24\n::set-env name=BAD::yes.tar.gz"
    (dist_root / control_name).write_bytes(b"sdist")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_bytes(b"{}\n")

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(dist_root),
            str(manifest),
            str(tmp_path / "transfer"),
            "0.0.24",
        ],
        check=False,
        capture_output=True,
        input=handoff_code,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "Release artifact inventory is invalid"
    assert "::set-env" not in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="FIFO rejection requires POSIX")
def test_artifact_handoff_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    handoff_code = _artifact_handoff_code()
    dist_root = tmp_path / "dist"
    dist_root.mkdir()
    (dist_root / "netbox_proxbox-0.0.24-py3-none-any.whl").write_bytes(b"wheel")
    os.mkfifo(dist_root / "netbox_proxbox-0.0.24.tar.gz")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_bytes(b"{}\n")

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(dist_root),
            str(manifest),
            str(tmp_path / "transfer"),
            "0.0.24",
        ],
        check=False,
        capture_output=True,
        input=handoff_code,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert "special file" in result.stderr


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


def test_operator_docs_match_the_locked_control_dispatch_contract() -> None:
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    release_labels = {job["runs-on"] for job in workflow["jobs"].values()}
    assert len(release_labels) == 1
    release_label = release_labels.pop()
    documentation_by_path = {path: _read(path) for path in RELEASE_CONTROL_DOC_PATHS}
    documentation = "\n".join(documentation_by_path.values())

    assert "publish=true" not in documentation
    assert "validate.yml" in documentation
    assert "publish.yml" in documentation
    assert "repository name" in documentation
    assert "target run ID" in documentation
    assert "request SHA-256" in documentation
    assert "do not merge" in documentation.lower()
    assert "existing publisher" in documentation.lower()
    assert release_label == "ci-release-netbox-proxbox"
    canary_contract = "historical canary"
    for path in CANARY_DOC_PATHS:
        text = documentation_by_path[path]
        assert canary_contract in " ".join(text.split()), path
        assert "dedicated untrusted CI VM" not in text, path

    for path, text in documentation_by_path.items():
        normalized = " ".join(text.split())
        for filename in (
            "wheel",
            "sdist",
            "release-manifest.json",
            "release-request.json",
            "runner-completion-attestation.json",
            "runner-completion-attestation.sig",
        ):
            assert filename in text, (path, filename)
        assert "signature" in normalized and "verif" in normalized, path
    agent_docs = (REPO_ROOT / "AGENTS.md", REPO_ROOT / "CLAUDE.md")
    for path in agent_docs:
        normalized = " ".join(documentation_by_path[path].split())
        assert f"job-bound ephemeral `{release_label}`" in normalized


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
    assert "deploy-netbox-plugin-package \\\n            netbox-proxbox" in workflow
    assert "deploy-netbox-plugin netbox-proxbox" in workflow
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
