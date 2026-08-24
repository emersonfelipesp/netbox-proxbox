"""Source contracts for the Proxbox-only Sync Jobs page.

Behavioral parity between the SQL filter and the Python predicate is proved
against a real database in ``test_proxbox_job_filter_django.py``; that is the
authoritative guard. These checks run in the mocked suite, where neither Django
nor NetBox is importable, and pin the wiring and the two translation traps that
a refactor is most likely to undo silently -- the NULL ``queue_name`` branch and
the navigation target.

They are AST/source contracts by necessity, so they are deliberately narrow:
each one names a specific regression, and none of them claims to verify
behavior the matrix test owns.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "netbox_proxbox"


def _function_source(path: Path, name: str) -> str:
    """Return the source of one top-level function, or fail if it is gone."""
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(path.read_text(), node) or ""
    pytest.fail(f"{path.name} no longer defines {name}()")


# ---------------------------------------------------------------------------
# The database filter
# ---------------------------------------------------------------------------


@pytest.fixture()
def filter_source() -> str:
    return _function_source(_PACKAGE / "jobs.py", "proxbox_sync_job_q")


def test_filter_covers_the_null_queue_name(filter_source):
    """``__in`` never matches SQL NULL; the predicate reads NULL as ``""``.

    Dropping this branch hides every job whose queue was never recorded, and
    hides it silently -- the rows just stop appearing on the page.
    """
    assert "queue_name__isnull=True" in filter_source
    assert 'queue_name=""' in filter_source


def test_filter_covers_every_predicate_branch(filter_source):
    """All four ways ``is_proxbox_sync_job`` can say yes must be represented."""
    assert 'data__has_key="proxbox_sync"' in filter_source
    assert "LEGACY_PROXBOX_RQ_QUEUE" in filter_source
    assert "PROXBOX_SYNC_QUEUE_NAME" in filter_source
    assert "name__regex" in filter_source


def test_filter_tolerates_surrounding_whitespace(filter_source):
    """The predicate compares ``name.strip()``, so the regexes must too."""
    assert filter_source.count(r"^\s*") >= 2
    assert filter_source.count(r"\s*$") >= 2


def test_filter_reuses_the_targeted_vm_pattern(filter_source):
    """Re-typing the job-name format here would let the two drift apart."""
    assert "_TARGETED_VM_JOB_NAME_RE.pattern" in filter_source


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_navigation_no_longer_points_at_the_core_job_list():
    """The entire feature: Sync Jobs must leave ``core:job_list`` behind."""
    source = (_PACKAGE / "navigation.py").read_text()
    tree = ast.parse(source)

    target = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "sync_jobs_item"
                for t in node.targets
            )
            and isinstance(node.value, ast.Call)
        ):
            for keyword in node.value.keywords:
                if keyword.arg == "link" and isinstance(keyword.value, ast.Constant):
                    target = keyword.value.value
    assert target == "plugins:netbox_proxbox:job_list", (
        f"sync_jobs_item points at {target!r}"
    )


def test_job_list_route_is_mounted():
    source = (_PACKAGE / "urls.py").read_text()
    assert 'path("jobs/", views.ProxboxJobListView.as_view(), name="job_list")' in source


def test_view_is_exported_from_the_views_package():
    source = (_PACKAGE / "views" / "__init__.py").read_text()
    assert "from .jobs import ProxboxJobListView" in source


# ---------------------------------------------------------------------------
# The view and table
# ---------------------------------------------------------------------------


@pytest.fixture()
def view_source() -> str:
    return (_PACKAGE / "views" / "jobs.py").read_text()


def test_view_filters_the_queryset(view_source):
    assert "proxbox_sync_job_q()" in view_source
    assert 'Job.objects.defer("data").filter(proxbox_sync_job_q())' in view_source


def test_view_subclasses_core_rather_than_reimplementing_it(view_source):
    """Inheriting core's list keeps its filterset/filter form/export in step."""
    tree = ast.parse(view_source)
    bases = {
        base.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for base in node.bases
        if isinstance(base, ast.Name)
    }
    assert "JobListView" in bases
    assert "JobTable" in bases


def test_bug_report_column_gates_on_reportable_status(view_source):
    """Only errored/failed/unknown rows get the affordance."""
    assert "is_reportable_status(record.status)" in view_source


def test_list_page_does_not_render_the_modal_per_row(view_source):
    """The modal needs ``data``/``log_entries``; the list defers ``data``.

    Rendering it per row would defeat the deferral and emit one modal plus one
    inline script per job, so the column must link to the detail page instead.
    """
    assert "build_bug_report_context" not in view_source
    assert "record.get_absolute_url()" in view_source
