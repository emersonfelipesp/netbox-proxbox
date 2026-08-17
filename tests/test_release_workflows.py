"""Static contracts for the staged package-first release workflow."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
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
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
RELEASE_CONTROL_DOC_PATHS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "developer" / "release-publishing.md",
)


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
    assert workflow.count("sha256sum --check --strict") == 2
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
    policy_run = parsed["jobs"]["validate-source"]["steps"][1]["run"]
    expected_digest = hashlib.sha256(CI_GATE_PATH.read_bytes()).hexdigest()
    isolated_invocation = "python3 -I scripts/gitea_ci_gate.py"

    assert expected_digest == (
        "14ef8bdb2c39fd4d239b8541a66b1b4708be6a61d7374b62f660b2673db5d8dd"
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

    assert build_job["needs"] == "validate-source"
    assert build_job["name"] == (
        "Build exact publisher-credential-free release-control request"
    )
    assert upload_step["with"] == {
        "name": "release-control-request",
        "path": "release-transfer",
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
    assert "secrets." not in build_source
    assert "github.token" not in build_source
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
    assert parsed["jobs"]["build-request"]["permissions"] == {"contents": "read"}
    assert validate_source.count("github.token") == 1
    assert "GITEA_API_TOKEN" in validate_source
    assert "github.token" not in build_source
    assert "GITEA_API_TOKEN" not in build_source
    boundary_step = parsed["jobs"]["build-request"]["steps"][2]
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
    bind_run = parsed["jobs"]["build-request"]["steps"][3]["run"]
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


def test_candidate_process_cpu_accounting_includes_reaped_descendants() -> None:
    workflow = yaml.safe_load(_read(GITEA_PUBLISH_WORKFLOW))
    boundary_run = workflow["jobs"]["build-request"]["steps"][2]["run"]
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
    boundary_run = workflow["jobs"]["build-request"]["steps"][2]["run"]
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
    bind_run = parsed["jobs"]["build-request"]["steps"][3]["run"]
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
    canary_contract = (
        f"The `{release_label}` activation canary must separately prove that the "
        "exact repository-scoped release runner/container denies management and "
        "production network access; an online runner label alone is insufficient "
        "evidence."
    )
    for path, text in documentation_by_path.items():
        assert canary_contract in " ".join(text.split()), path
        assert "dedicated untrusted CI VM" not in text, path

    agent_docs = (REPO_ROOT / "AGENTS.md", REPO_ROOT / "CLAUDE.md")
    for path in agent_docs:
        assert f"disposable `{release_label}` job" in documentation_by_path[path]


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
            "run_attempt": 0,
            "actor": {"login": "emersonfelipesp"},
        },
        "/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34": {
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
    assert evidence == {context: {"job_id": 34, "run_attempt": 1, "run_id": 12}}

    responses["/repos/emersonfelipesp/netbox-proxbox/actions/runs/12"][
        "run_attempt"
    ] = 1
    assert gate.validate_ci_gate(
        owner="emersonfelipesp",
        repository="netbox-proxbox",
        source_sha=sha,
        required_contexts=[context],
        trusted_actor="emersonfelipesp",
        token="test-token",
    ) == {context: {"job_id": 34, "run_attempt": 1, "run_id": 12}}

    responses["/repos/emersonfelipesp/netbox-proxbox/actions/runs/12"][
        "run_attempt"
    ] = 2
    with pytest.raises(gate.CIGateError, match="run attempt is invalid"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    responses["/repos/emersonfelipesp/netbox-proxbox/actions/runs/12"][
        "run_attempt"
    ] = 0

    responses["/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34"][
        "run_attempt"
    ] = 2
    with pytest.raises(gate.CIGateError, match="job does not match"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    responses["/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34"][
        "run_attempt"
    ] = 1

    responses["/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34"]["labels"] = [
        "ci-untrusted-python312",
        "prod-deploy",
    ]
    with pytest.raises(gate.CIGateError, match="trusted CI runner class"):
        gate.validate_ci_gate(
            owner="emersonfelipesp",
            repository="netbox-proxbox",
            source_sha=sha,
            required_contexts=[context],
            trusted_actor="emersonfelipesp",
            token="test-token",
        )
    responses["/repos/emersonfelipesp/netbox-proxbox/actions/jobs/34"]["labels"] = [
        "ci-untrusted-python312"
    ]

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
