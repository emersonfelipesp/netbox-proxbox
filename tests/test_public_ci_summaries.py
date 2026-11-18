"""Exercise the actual public summary shell programs with terminal outcomes."""

from pathlib import Path
import os
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def summary_script(filename: str) -> str:
    """Read the shipped summary body rather than reimplement its decision."""
    document = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
    job = document["jobs"]["complete"]
    assert job["if"] == "${{ always() }}"
    return job["steps"][0]["run"]


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("field", ["LINT", "TYPES", "COMPILE", "PACKAGE", "TESTS"])
def test_core_summary_requires_every_producer(field: str, outcome: str) -> None:
    environment = {
        **os.environ,
        **dict.fromkeys(["LINT", "TYPES", "COMPILE", "PACKAGE", "TESTS"], "success"),
        field: outcome,
    }
    result = subprocess.run(
        ["/bin/bash", "-c", summary_script("ci.yml")],
        env=environment,
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == (outcome == "success")


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled", "skipped", ""])
def test_django_summary_requires_complete_matrix(outcome: str) -> None:
    result = subprocess.run(
        ["/bin/bash", "-c", summary_script("django-tests.yml")],
        env={**os.environ, "MATRIX_RESULT": outcome},
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == (outcome == "success")


@pytest.mark.parametrize(
    "selector,selected,prerequisites,matrix,accepted",
    [
        ("success", "true", "success", "success", True),
        ("success", "false", "skipped", "skipped", True),
        ("failure", "false", "skipped", "skipped", False),
        ("cancelled", "true", "success", "success", False),
        ("success", "", "skipped", "skipped", False),
        ("success", "true", "failure", "skipped", False),
        ("success", "true", "success", "failure", False),
        ("success", "true", "success", "cancelled", False),
        ("success", "true", "success", "skipped", False),
        ("success", "false", "success", "success", False),
    ],
)
def test_e2e_summary_requires_selected_producers(
    selector: str,
    selected: str,
    prerequisites: str,
    matrix: str,
    accepted: bool,
) -> None:
    result = subprocess.run(
        ["/bin/bash", "-c", summary_script("e2e-docker.yml")],
        env={
            **os.environ,
            "SELECTOR": selector,
            "SELECTED": selected,
            "PREREQUISITES": prerequisites,
            "MATRIX": matrix,
        },
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == accepted


def git_fixture_command(repository: Path, *arguments: str) -> str:
    """Run Git only against the task-owned fixture repository."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    "filename,selected",
    [
        ("netbox_proxbox/nested/module.py", True),
        ("tests/e2e/nested/test_case.py", True),
        ("tests/test_backend_key_adoption_variant.py", True),
        (".github/workflows/e2e-docker.yml", True),
        ("scripts/e2e_example.py", True),
        ("tests/test_e2e_example.py", True),
        ("docs/guide.md", False),
        ("tests/test_e2e_example.txt", False),
        ("docs/netbox_proxbox/example.py", False),
        ("netbox_proxbox/space and\nnewline.py", True),
    ],
)
@pytest.mark.parametrize("operation", ["add", "delete", "rename-away"])
def test_e2e_selector_uses_real_git_changes(
    tmp_path: Path, filename: str, selected: bool, operation: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    git_fixture_command(repository, "init", "--quiet")
    git_fixture_command(repository, "config", "user.name", "CI fixture")
    git_fixture_command(repository, "config", "user.email", "ci@example.invalid")
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    (repository / "baseline.txt").write_text("fixture baseline\n")
    if operation != "add":
        path.write_text("unchanged fixture content\n" * 10)
    git_fixture_command(repository, "add", ".")
    git_fixture_command(repository, "commit", "--quiet", "-m", "Create fixture base")
    base = git_fixture_command(repository, "rev-parse", "HEAD")
    if operation == "add":
        path.write_text("changed fixture content\n")
    elif operation == "delete":
        path.unlink()
    else:
        path.rename(repository / "unrelated-renamed.txt")
    git_fixture_command(repository, "add", "--all")
    git_fixture_command(repository, "commit", "--quiet", "-m", "Change fixture path")
    head = git_fixture_command(repository, "rev-parse", "HEAD")
    document = yaml.safe_load((ROOT / ".github/workflows/e2e-docker.yml").read_text())
    script = document["jobs"]["selection"]["steps"][1]["run"]
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        cwd=repository,
        env={
            **os.environ,
            "EVENT": "pull_request",
            "BASE": base,
            "HEAD": head,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert output.read_text() == f"selected={str(selected).lower()}\n"
