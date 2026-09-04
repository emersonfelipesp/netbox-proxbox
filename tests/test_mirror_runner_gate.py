"""Tests for the active credential-bearing mirror runner boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import stat
import tarfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "scripts" / "gitea_mirror_runner_gate.py"
ACCEPTANCE_PATH = REPO_ROOT / ".gitea" / "mirror-runner-acceptance.json"
PUBLISH_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "publish-gitea.yml"
PROMOTE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "promote-final-tag.yml"


def _load_gate():
    spec = importlib.util.spec_from_file_location("gitea_mirror_runner_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _acceptance(gate, tmp_path: Path, binary: bytes = b"accepted uv"):
    executable = tmp_path / "accepted-tool"
    executable.write_bytes(b"trusted executable")
    executable.chmod(0o755)
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as bundle:
        member = tarfile.TarInfo("uv-x86_64-unknown-linux-gnu/uv")
        member.mode = 0o755
        member.size = len(binary)
        bundle.addfile(member, io.BytesIO(binary))
    archive = archive_buffer.getvalue()
    record = {
        "allowed_job_names": [
            "Publish exact Gitea package and reserve RC tag",
            "Verify production evidence and promote exact tag",
        ],
        "executables": {
            name: {
                "path": str(executable),
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "size": executable.stat().st_size,
            }
            for name in gate.EXPECTED_EXECUTABLES
        },
        "registered_labels": ["mirror-host"],
        "repository": "emersonfelipesp/netbox-proxbox",
        "runner_id": 46,
        "runner_label": "mirror-host",
        "runner_name": "ci-deploy-emersonfelipesp-246",
        "schema": 1,
        "uv_archive": {
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "archive_size": len(archive),
            "binary_sha256": hashlib.sha256(binary).hexdigest(),
            "binary_size": len(binary),
            "member": "uv-x86_64-unknown-linux-gnu/uv",
            "url": "https://github.com/astral-sh/uv/releases/download/0.12.5/uv-x86_64-unknown-linux-gnu.tar.gz",
            "version": "0.12.5",
        },
    }
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_bytes(gate._canonical_json(record))
    return acceptance_path, archive, binary


def test_mirror_runner_gate_binds_live_job_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _load_gate()
    acceptance_path, _, _ = _acceptance(gate, tmp_path)
    monkeypatch.setattr(
        gate,
        "_verify_executables",
        lambda _acceptance: {"python": "/usr/bin/python3.13"},
    )
    job = {
        "conclusion": None,
        "head_sha": "a" * 40,
        "id": 38950,
        "labels": ["mirror-host"],
        "name": "Publish exact Gitea package and reserve RC tag",
        "run_attempt": 1,
        "run_id": 20651,
        "runner_id": 46,
        "runner_name": "ci-deploy-emersonfelipesp-246",
        "status": "in_progress",
    }
    kwargs = {
        "acceptance_path": acceptance_path,
        "owner": "emersonfelipesp",
        "repository": "netbox-proxbox",
        "run_id": 20651,
        "run_attempt": 1,
        "job_name": job["name"],
        "source_sha": "a" * 40,
        "token": "",
    }
    evidence = gate.validate_mirror_runner(
        **kwargs, jobs_payload={"jobs": [job], "total_count": 1}
    )
    assert evidence["runner_id"] == 46
    with pytest.raises(gate.MirrorRunnerGateError, match="exact accepted"):
        gate.validate_mirror_runner(
            **kwargs,
            jobs_payload={
                "jobs": [{**job, "runner_id": 47}],
                "total_count": 1,
            },
        )
    with pytest.raises(gate.MirrorRunnerGateError, match="invocation is invalid"):
        gate.validate_mirror_runner(
            **{**kwargs, "run_attempt": 2},
            jobs_payload={"jobs": [job], "total_count": 1},
        )


def test_executable_metadata_and_digest_fail_closed(tmp_path: Path) -> None:
    gate = _load_gate()
    executable = tmp_path / "tool"
    executable.write_bytes(b"reviewed executable")
    executable.chmod(0o755)
    ownership = {
        "expected_uid": executable.stat().st_uid,
        "expected_gid": executable.stat().st_gid,
    }
    assert (
        gate._hash_open_executable(executable, executable.stat().st_size, **ownership)
        == hashlib.sha256(executable.read_bytes()).hexdigest()
    )
    executable.chmod(0o775)
    with pytest.raises(gate.MirrorRunnerGateError, match="metadata changed"):
        gate._hash_open_executable(executable, executable.stat().st_size, **ownership)


def test_checksum_pinned_uv_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _load_gate()
    acceptance_path, archive, binary = _acceptance(gate, tmp_path)
    monkeypatch.setattr(gate, "_verify_executables", lambda _acceptance: {})
    destination = tmp_path / "runtime" / "uv"
    destination.parent.mkdir(mode=0o700)
    evidence = gate.install_uv(
        acceptance_path=acceptance_path,
        output=destination,
        archive_bytes=archive,
    )
    assert destination.read_bytes() == binary
    assert stat.S_IMODE(destination.stat().st_mode) == 0o500
    assert evidence["sha256"] == hashlib.sha256(binary).hexdigest()
    descriptor = gate._open_validated_uv(
        acceptance_path=acceptance_path,
        executable=destination,
    )
    os.close(descriptor)

    runner_uid = destination.stat().st_uid
    monkeypatch.setattr(gate.os, "geteuid", lambda: runner_uid + 1)
    with pytest.raises(gate.MirrorRunnerGateError, match="metadata changed"):
        gate._open_validated_uv(
            acceptance_path=acceptance_path,
            executable=destination,
        )
    monkeypatch.setattr(gate.os, "geteuid", lambda: runner_uid)

    destination.replace(destination.with_name("reviewed-uv"))
    destination.write_bytes(b"attacker-controlled replacement")
    destination.chmod(0o500)
    with pytest.raises(
        gate.MirrorRunnerGateError, match="metadata changed|digest changed"
    ):
        gate._open_validated_uv(
            acceptance_path=acceptance_path,
            executable=destination,
        )
    with pytest.raises(gate.MirrorRunnerGateError, match="archive bytes differ"):
        gate.install_uv(
            acceptance_path=acceptance_path,
            output=tmp_path / "corrupt-uv",
            archive_bytes=archive + b"corrupt",
        )


def _locked_python_environment(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "runtime" / "venv"
    site_packages = root / "lib" / "python3.13" / "site-packages"
    site_packages.mkdir(parents=True)
    root.chmod(0o700)
    for name, version in (
        ("build", "1.5.0"),
        ("hatchling", "1.31.0"),
        ("twine", "6.2.0"),
    ):
        metadata = site_packages / f"{name}-{version}.dist-info" / "METADATA"
        metadata.parent.mkdir()
        metadata.write_text(
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
            encoding="utf-8",
        )
    package = site_packages / "trusted_module.py"
    package.write_text("VALUE = 'trusted'\n", encoding="utf-8")
    return root, root.parent / "environment-manifest.json"


def test_locked_python_environment_detects_replacement(tmp_path: Path) -> None:
    gate = _load_gate()
    root, manifest = _locked_python_environment(tmp_path)
    evidence = gate.seal_python_environment(
        root=root,
        manifest=manifest,
        requirements=["build=1.5.0", "hatchling=1.31.0", "twine=6.2.0"],
    )
    assert evidence["requirements"] == {
        "build": "1.5.0",
        "hatchling": "1.31.0",
        "twine": "6.2.0",
    }
    gate._read_python_environment_manifest(manifest)

    package = root / "lib" / "python3.13" / "site-packages" / "trusted_module.py"
    package.write_text("VALUE = 'attacker-controlled'\n", encoding="utf-8")
    with pytest.raises(gate.MirrorRunnerGateError, match="environment bytes changed"):
        gate._read_python_environment_manifest(manifest)


def test_locked_python_environment_requires_current_runner_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _load_gate()
    root, manifest = _locked_python_environment(tmp_path)
    monkeypatch.setattr(gate.os, "geteuid", lambda: root.stat().st_uid + 1)
    with pytest.raises(gate.MirrorRunnerGateError, match="root is unsafe"):
        gate.seal_python_environment(
            root=root,
            manifest=manifest,
            requirements=["build=1.5.0"],
        )


def test_locked_python_environment_rejects_links_and_version_drift(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    root, manifest = _locked_python_environment(tmp_path)
    (root / "lib" / "escape").symlink_to("/tmp")
    with pytest.raises(gate.MirrorRunnerGateError, match="symbolic link"):
        gate.seal_python_environment(
            root=root,
            manifest=manifest,
            requirements=["build=1.5.0"],
        )

    (root / "lib" / "escape").unlink()
    with pytest.raises(
        gate.MirrorRunnerGateError,
        match="distribution versions differ",
    ):
        gate.seal_python_environment(
            root=root,
            manifest=manifest,
            requirements=["build=0.0.0"],
        )


def test_active_workflows_attest_before_credentials() -> None:
    acceptance = _load_gate()._read_acceptance(ACCEPTANCE_PATH)
    assert acceptance["runner_id"] == 46
    assert acceptance["registered_labels"] == ["mirror-host"]
    assert all(
        set(record["sha256"]) != {"0"} for record in acceptance["executables"].values()
    )

    publish_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = yaml.safe_load(publish_text)
    assert publish["permissions"] == {"actions": "read", "contents": "read"}
    publish_job = publish["jobs"]["publish-gitea"]
    assert publish_job["name"] == "Publish exact Gitea package and reserve RC tag"
    publish_names = [step["name"] for step in publish_job["steps"]]
    assert publish_names.index("Attest live runner and credential consumers") < (
        publish_names.index("Checkout candidate tag as passive build input")
    )
    assert (
        "/usr/bin/python3.13 scripts/gitea_mirror_runner_gate.py validate"
        in publish_text
    )
    assert "/usr/bin/gh auth status" in publish_text
    assert "/usr/bin/git -C candidate push github" in publish_text
    assert "#!/usr/bin/dash" in publish_text
    assert "command -v gh" not in publish_text

    promote_text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
    promote = yaml.safe_load(promote_text)
    assert promote["permissions"] == {"actions": "read", "contents": "read"}
    promote_steps = promote["jobs"]["promote-final-tag"]["steps"]
    promote_names = [step["name"] for step in promote_steps]
    assert promote_names.index("Attest live runner and credential consumers") < (
        promote_names.index("Validate canonical release source and production evidence")
    )
    assert "/usr/bin/gh auth status" in promote_text
    assert "/usr/bin/git push github" in promote_text
    assert "#!/usr/bin/dash" in promote_text


def test_temporary_runner_workflows_are_not_shipped() -> None:
    workflow_root = REPO_ROOT / ".gitea" / "workflows"
    assert not (workflow_root / "mirror-runner-diagnostic.yml").exists()
    assert not (workflow_root / "mirror-runner-validation.yml").exists()
