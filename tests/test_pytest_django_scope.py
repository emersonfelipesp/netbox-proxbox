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

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DJANGO_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "django-tests.yml"


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
