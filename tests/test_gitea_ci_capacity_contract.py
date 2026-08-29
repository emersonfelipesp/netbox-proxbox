from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".gitea" / "workflows" / "ci.yml"
CLEANER = ROOT / "ci" / "clean-generated-workspace.sh"


def load_workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def step_script(job: dict[str, Any], name: str) -> str:
    steps = job["steps"]
    return next(step["run"] for step in steps if step.get("name") == name)


def test_capacity_bound_gitea_jobs_are_serialized_without_cache() -> None:
    workflow = load_workflow()
    jobs = workflow["jobs"]
    quality = jobs["quality"]
    docs = jobs["docs-and-package"]

    assert workflow["concurrency"] == {
        "group": "netbox-proxbox-ci",
        "cancel-in-progress": False,
    }
    assert docs["needs"] == "quality"
    assert quality["env"]["UV_NO_CACHE"] == "1"
    assert docs["env"]["UV_NO_CACHE"] == "1"
    assert "UV_CACHE_DIR" not in quality["env"]
    assert "UV_CACHE_DIR" not in docs["env"]


def test_quality_and_docs_install_only_their_locked_dependency_scope() -> None:
    jobs = load_workflow()["jobs"]
    quality_install = step_script(
        jobs["quality"], "Install locked quality and test environment"
    )
    docs_install = step_script(
        jobs["docs-and-package"], "Install documentation and packaging environment"
    )
    package_build = step_script(
        jobs["docs-and-package"], "Build and check distribution"
    )

    assert (
        "uv sync --no-dev --extra test --extra dev --extra cli --locked"
        in quality_install
    )
    assert "--group dev" not in quality_install
    assert "uv sync --group dev --group publish --locked" in docs_install
    assert "uv pip install" not in docs_install
    assert ".venv/bin/python -m build --no-isolation" in package_build


def test_jobs_preflight_capacity_and_always_clean_workspace_artifacts() -> None:
    jobs = load_workflow()["jobs"]
    quality = jobs["quality"]
    docs = jobs["docs-and-package"]
    quality_install = step_script(
        quality, "Install locked quality and test environment"
    )
    docs_install = step_script(docs, "Install documentation and packaging environment")

    for install in (quality_install, docs_install):
        assert "required_kib=393216" in install
        assert 'test "$available_kib" -ge "$required_kib"' in install
        assert "runner_capacity available_kib=%s required_kib=%s" in install
    quality_cleanup = next(
        step for step in quality["steps"] if step["name"] == "Clean quality environment"
    )
    docs_cleanup = next(
        step
        for step in docs["steps"]
        if step["name"] == "Clean docs and package environment"
    )
    assert quality_cleanup["if"] == "always()"
    assert docs_cleanup["if"] == "always()"
    assert quality_cleanup["run"] == "bash ci/clean-generated-workspace.sh cleanup"
    assert docs_cleanup["run"] == "bash ci/clean-generated-workspace.sh cleanup"
    for job in (quality, docs):
        startup = step_script(job, "Reset generated workspace state")
        assert startup == "bash ci/clean-generated-workspace.sh startup"


@pytest.mark.parametrize(
    ("job_name", "step_name", "job_outputs"),
    (
        ("quality", "Clean quality environment", ()),
        (
            "docs-and-package",
            "Clean docs and package environment",
            (".ci-site", "dist"),
        ),
    ),
)
def test_cleanup_steps_remove_generated_workspace_artifacts(
    tmp_path: Path,
    job_name: str,
    step_name: str,
    job_outputs: tuple[str, ...],
) -> None:
    jobs = load_workflow()["jobs"]
    assert step_script(jobs[job_name], step_name) == (
        "bash ci/clean-generated-workspace.sh cleanup"
    )
    generated_paths = (".venv", ".ruff_cache", ".pytest_cache", "htmlcov", *job_outputs)
    for generated_path in generated_paths:
        (tmp_path / generated_path).mkdir()
    (tmp_path / ".coverage").write_text("coverage")
    for source_root in ("netbox_proxbox", "proxbox_cli", "tests"):
        bytecode = tmp_path / source_root / "nested" / "__pycache__" / "module.pyc"
        bytecode.parent.mkdir(parents=True)
        bytecode.write_bytes(b"bytecode")

    result = subprocess.run(
        ["bash", str(CLEANER), "cleanup"], cwd=tmp_path, text=True, capture_output=True
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".coverage").exists()
    assert all(
        not (tmp_path / generated_path).exists() for generated_path in generated_paths
    )
    assert not list(tmp_path.rglob("*.py[co]"))
    assert not list(tmp_path.rglob("__pycache__"))


def test_startup_scrub_removes_stale_outputs_before_use(tmp_path: Path) -> None:
    for source_root in ("netbox_proxbox", "proxbox_cli", "tests"):
        (tmp_path / source_root).mkdir()
    stale_artifact = tmp_path / "dist" / "stale.whl"
    stale_artifact.parent.mkdir()
    stale_artifact.write_bytes(b"stale")

    result = subprocess.run(
        ["bash", str(CLEANER), "startup"], cwd=tmp_path, text=True, capture_output=True
    )

    assert result.returncode == 0, result.stderr
    assert not stale_artifact.exists()
    assert not (tmp_path / "dist").exists()


def test_startup_scrub_removes_symlink_without_following_and_fails_closed(
    tmp_path: Path,
) -> None:
    for source_root in ("netbox_proxbox", "proxbox_cli", "tests"):
        (tmp_path / source_root).mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "must-remain"
    marker.write_text("external")
    (tmp_path / ".venv").symlink_to(external, target_is_directory=True)

    result = subprocess.run(
        ["bash", str(CLEANER), "startup"], cwd=tmp_path, text=True, capture_output=True
    )

    assert result.returncode == 65
    assert not (tmp_path / ".venv").exists()
    assert marker.read_text() == "external"
