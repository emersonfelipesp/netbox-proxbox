"""Contract: pytest-django is disabled for the mocked suite ONLY.

Two pytest jobs run in CI and they need opposite things from pytest-django:

* ``.github/workflows/ci.yml`` runs the **mocked** suite against the
  Django/NetBox stubs in ``tests/conftest.py``. Those stubs register ``django``
  as a plain **module**, not a package, so pytest-django's
  ``pytest_collection_modifyitems`` hook — which unconditionally runs
  ``from django.test import TestCase, TransactionTestCase`` — raises
  ``ModuleNotFoundError: No module named 'django.test'; 'django' is not a
  package`` and aborts the whole run with an INTERNALERROR. That job therefore
  passes ``-p no:django``.

* ``.github/workflows/django-tests.yml`` runs the NetBox-backed subset against a
  **real** Django and genuinely needs pytest-django — it passes ``--ds``,
  ``--reuse-db`` and ``--create-db``.

So the disable must stay **per-invocation**. Putting ``-p no:django`` in
``[tool.pytest.ini_options] addopts`` disables the plugin for *both* jobs and
makes those flags "unrecognized arguments" in the NetBox-backed job. This module
pins that split so the fix cannot be "simplified" back into a global option.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DJANGO_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "django-tests.yml"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-testpypi.yml"
GITEA_PUBLISH_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "publish-gitea.yml"
TRACEABILITY_DOC = REPO_ROOT / "docs" / "developer" / "endpoint-autoconfiguration.md"
CI_WORKFLOW_DOC = REPO_ROOT / "docs" / "developer" / "ci-e2e-workflows.md"
MKDOCS = REPO_ROOT / "mkdocs.yml"
README = REPO_ROOT / "README.md"
NETBOX_TEST_CONFIG = REPO_ROOT / "tests" / "netbox_test_configuration.py"


def test_mocked_suite_disables_pytest_django():
    """ci.yml's mocked run must pass -p no:django, or collection aborts."""
    workflow = CI_WORKFLOW.read_text()
    run_lines = [
        line for line in workflow.splitlines() if re.search(r"\bpytest\b", line)
    ]

    assert run_lines, "expected a pytest invocation in ci.yml"
    assert any("-p no:django" in line for line in run_lines), (
        "ci.yml must run the mocked suite with `-p no:django`; without it "
        "pytest-django's collection hook imports django.test against the "
        "conftest stub and aborts with an INTERNALERROR before any test runs"
    )


def test_ci_static_toolchain_is_pinned_and_markdown_is_not_python_formatted():
    """Hosted lint results must not change under an unreviewed tool release."""

    workflow = CI_WORKFLOW.read_text()
    configuration = tomllib.loads(PYPROJECT.read_text())

    assert 'pip install "ruff==0.15.10" "bandit==1.9.4"' in workflow
    assert configuration["tool"]["ruff"]["format"]["exclude"] == ["*.md"]


def test_pre_commit_mocked_suite_disables_pytest_django():
    """The local all-files gate must follow the mocked-suite invocation contract."""
    configuration = PRE_COMMIT_CONFIG.read_text()
    pytest_hook = configuration.split("- id: pytest", 1)[1]

    assert 'args: ["-p", "no:django", "tests/"]' in pytest_hook, (
        "the pre-commit pytest hook must disable pytest-django per invocation; "
        "otherwise collection imports django.test against the conftest stub"
    )


def test_release_mocked_suites_disable_pytest_django():
    """Every release-time full mocked run needs the same collection guard."""
    workflow = RELEASE_WORKFLOW.read_text()
    run_lines = [line for line in workflow.splitlines() if "uv run pytest" in line]

    assert len(run_lines) == 2, (
        "expected TestPyPI and PyPI candidate full-suite pytest invocations"
    )
    assert all("-p no:django" in line for line in run_lines), (
        "publish-testpypi.yml must disable pytest-django for every mocked "
        "full-suite run, or its release validation aborts during collection"
    )


def test_gitea_package_publish_has_one_automatic_tag_trigger():
    """A tag must create one immutable package upload, never push+create twins."""
    workflow = GITEA_PUBLISH_WORKFLOW.read_text()
    trigger_block = workflow.split("jobs:", 1)[0]

    assert "push:" in trigger_block
    assert "tags:" in trigger_block
    assert "create:" not in trigger_block, (
        "Gitea emits both create and push for a tag; subscribing to both starts "
        "duplicate immutable package uploads for the same version"
    )


def test_real_django_workflow_enforces_autoconfiguration_branch_coverage():
    """Each real-Django production module must pass its own coverage gate."""
    workflow = DJANGO_WORKFLOW.read_text()

    assert "--cov=netbox_proxbox.services.endpoint_autoconfiguration" in workflow
    assert "--cov=netbox_proxbox.api.serializers.resource_views" in workflow
    assert "--cov-branch" in workflow
    assert "--cov-fail-under=0" in workflow
    assert workflow.count("--fail-under=85") == 2
    assert (
        "--include='netbox_proxbox/services/endpoint_autoconfiguration.py'" in workflow
    )
    assert "--include='netbox_proxbox/api/serializers/resource_views.py'" in workflow


def test_candidate_workflow_cannot_self_authorize_the_waiter_pin():
    """A workflow edit remains untrusted until a later base-artifact pin update."""
    waiter = (REPO_ROOT / "scripts" / "wait_for_github_django_matrix.py").read_text()
    base_workflow_blob = "7d07b0c189101f2d2852ed98d057a22b0b4141f5"

    assert f'PINNED_WORKFLOW_BLOB_SHA = "{base_workflow_blob}"' in waiter
    payload = DJANGO_WORKFLOW.read_bytes()
    candidate_blob = hashlib.sha1(
        f"blob {len(payload)}\0".encode() + payload,
        usedforsecurity=False,
    ).hexdigest()
    assert candidate_blob != base_workflow_blob
    workflow_docs = CI_WORKFLOW_DOC.read_text()
    assert "workflow change cannot self-authorize" in workflow_docs
    assert "In a separate change" in workflow_docs


def test_real_django_workflow_runs_pdm_object_permission_regression():
    """The PDM queryset restriction needs a PDM-enabled real-Django gate."""
    workflow = DJANGO_WORKFLOW.read_text()

    assert "tests/test_pdm_endpoint_permissions_django.py" in workflow
    assert "pdm: true" in workflow


def test_endpoint_autoconfiguration_traceability_is_published():
    """The security state machine and evidence must stay in the docs surface."""
    document = TRACEABILITY_DOC.read_text()

    for heading in (
        "## Trust Boundary",
        "## Credential State Machine",
        "## Operator Outcomes",
        "## Requirements-to-Tests Matrix",
        "## Coverage Gates",
    ):
        assert heading in document
    assert "test_ui_endpoint_is_the_exact_discovery_allowlist" in document
    assert "test_websocket_redirect_never_receives_the_backend_key" in document
    assert "developer/endpoint-autoconfiguration.md" in MKDOCS.read_text()
    assert "/developer/endpoint-autoconfiguration/" in README.read_text()


def test_local_django_harness_accepts_isolated_service_hosts():
    """Parallel/local runs must not be forced through localhost's IPv6 result."""
    configuration = NETBOX_TEST_CONFIG.read_text()

    assert 'os.environ.get("NETBOX_TEST_DB_HOST")' in configuration
    assert 'os.environ.get("NETBOX_TEST_REDIS_HOST")' in configuration


def test_disable_is_not_global():
    """The flag must not live in addopts — it would break the NetBox-backed job."""
    pyproject = PYPROJECT.read_text()
    ini_options = re.search(
        r"\[tool\.pytest\.ini_options\](.*?)(?=\n\[|\Z)", pyproject, re.S
    )

    assert ini_options, "expected [tool.pytest.ini_options] in pyproject.toml"
    # Strip comments — the section documents *why* the flag is not set here.
    settings = "\n".join(
        line
        for line in ini_options.group(1).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "no:django" not in settings, (
        "`-p no:django` must not be a global addopts entry: django-tests.yml "
        "runs against a real Django and passes --ds/--reuse-db/--create-db, "
        "which become unrecognized arguments once the plugin is disabled"
    )


@pytest.mark.parametrize("flag", ["--ds=netbox.settings", "--reuse-db", "--create-db"])
def test_netbox_backed_job_still_relies_on_pytest_django(flag):
    """Pin the flags that prove django-tests.yml needs the plugin enabled."""
    if not DJANGO_WORKFLOW.exists():  # pragma: no cover - workflow always present
        pytest.skip("django-tests.yml not present")

    workflow = DJANGO_WORKFLOW.read_text()
    assert flag in workflow, (
        f"django-tests.yml is expected to pass {flag}; if that changed, revisit "
        "whether pytest-django must stay enabled for that job"
    )
    assert "-p no:django" not in workflow, (
        "django-tests.yml must NOT disable pytest-django — it runs against a "
        "real Django and depends on the plugin's flags and fixtures"
    )
