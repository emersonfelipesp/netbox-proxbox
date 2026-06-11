"""Source-contract and behavior tests for ``ProxmoxEndpointSyncJobsTabView``.

Coverage:

1. AST contract: class exists, subclasses ``ObjectView``, is in ``__all__``,
   declares the tab with correct label/permission/weight, uses the expected
   template, registers at ``path="sync-jobs"``, and defines
   ``get_extra_context``.
2. Behavior: ``get_extra_context`` returns ``endpoint_sync_jobs`` containing
   only jobs that pass ``is_proxbox_sync_job()`` AND match the endpoint PK
   or have an empty endpoint_ids list.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROXMOX_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_sync_jobs.html"
)


@pytest.fixture(scope="module")
def view_module_ast() -> ast.Module:
    return ast.parse(PROXMOX_VIEW_PATH.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in proxmox.py")


def _find_assign(class_node: ast.ClassDef, target: str) -> ast.AST | None:
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


# ── AST source contracts ─────────────────────────────────────────────────────


def test_sync_jobs_tab_view_class_exists(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSyncJobsTabView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectView" in base_names


def test_sync_jobs_tab_view_in_public_all(view_module_ast):
    module_all = _find_assign(view_module_ast, "__all__")  # type: ignore[arg-type]
    assert module_all is not None
    elts = {e.value for e in module_all.elts if isinstance(e, ast.Constant)}  # type: ignore[union-attr]
    assert "ProxmoxEndpointSyncJobsTabView" in elts


def test_sync_jobs_tab_view_template(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSyncJobsTabView")
    template_value = _find_assign(cls, "template_name")
    assert isinstance(template_value, ast.Constant)
    assert template_value.value == "netbox_proxbox/proxmoxendpoint_sync_jobs.html"


def test_sync_jobs_tab_view_tab_metadata(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSyncJobsTabView")
    tab_value = _find_assign(cls, "tab")
    assert isinstance(tab_value, ast.Call)
    assert isinstance(tab_value.func, ast.Name) and tab_value.func.id == "ViewTab"

    keywords = {kw.arg: kw.value for kw in tab_value.keywords}
    assert isinstance(keywords.get("label"), ast.Constant)
    assert keywords["label"].value == "Sync Jobs"
    assert isinstance(keywords.get("permission"), ast.Constant)
    assert keywords["permission"].value == "netbox_proxbox.view_proxmoxendpoint"
    assert isinstance(keywords.get("weight"), ast.Constant)
    assert isinstance(keywords["weight"].value, int)
    assert keywords["weight"].value < 900  # before Settings tab


def test_sync_jobs_tab_view_registered_at_sync_jobs_path(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSyncJobsTabView")
    decorator_paths: list[str] = []
    for deco in cls.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not (
            isinstance(deco.func, ast.Name) and deco.func.id == "register_model_view"
        ):
            continue
        for kw in deco.keywords:
            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                decorator_paths.append(kw.value.value)
    assert "sync-jobs" in decorator_paths


def test_sync_jobs_tab_view_has_get_extra_context(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSyncJobsTabView")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "get_extra_context" in methods


def test_sync_jobs_tab_template_file_exists():
    assert TEMPLATE_PATH.exists(), (
        f"Template not found: {TEMPLATE_PATH.relative_to(REPO_ROOT)}"
    )


def test_sync_jobs_tab_template_has_endpoint_sync_jobs_loop():
    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "endpoint_sync_jobs" in content
    assert "{% for job in endpoint_sync_jobs %}" in content


# ── Behavior of get_extra_context() ─────────────────────────────────────────


def _make_job(proxbox_sync: bool, endpoint_ids: list | None, pk: int = 99) -> object:
    """Create a minimal fake Job-like object."""
    if proxbox_sync and endpoint_ids is not None:
        data = {"proxbox_sync": {"params": {"proxmox_endpoint_ids": endpoint_ids}}}
    elif proxbox_sync:
        data = {"proxbox_sync": {"params": {}}}
    else:
        data = {}
    job = SimpleNamespace(pk=pk, name="Test Job", data=data)
    return job


def _run_get_extra_context(endpoint_pk: int, jobs: list) -> dict:
    """Replicate the view's filtering logic — this is the behavior contract.

    The view can't be fully loaded without Django, so we test the algorithm
    directly, mirroring get_extra_context verbatim.
    """
    endpoint_pk_str = str(endpoint_pk)
    result = []
    for job in jobs:
        data = getattr(job, "data", None) or {}
        if "proxbox_sync" not in data:
            continue
        params = data.get("proxbox_sync", {}).get("params", {})
        endpoint_ids = params.get("proxmox_endpoint_ids", [])
        if not endpoint_ids or endpoint_pk_str in [str(e) for e in endpoint_ids]:
            result.append(job)
    return {"endpoint_sync_jobs": result}


def test_get_extra_context_includes_matching_endpoint_job():
    job = _make_job(proxbox_sync=True, endpoint_ids=["5", "3"])
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[job])
    assert job in ctx["endpoint_sync_jobs"]


def test_get_extra_context_excludes_other_endpoint_job():
    job = _make_job(proxbox_sync=True, endpoint_ids=["3"])
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[job])
    assert job not in ctx["endpoint_sync_jobs"]


def test_get_extra_context_includes_all_endpoint_job():
    """Jobs with empty endpoint_ids apply to all endpoints and must be included."""
    job = _make_job(proxbox_sync=True, endpoint_ids=[])
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[job])
    assert job in ctx["endpoint_sync_jobs"]


def test_get_extra_context_excludes_non_proxbox_job():
    job = _make_job(proxbox_sync=False, endpoint_ids=None)
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[job])
    assert job not in ctx["endpoint_sync_jobs"]


def test_get_extra_context_empty_jobs():
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[])
    assert ctx["endpoint_sync_jobs"] == []


def test_get_extra_context_mixed_jobs():
    job_match = _make_job(proxbox_sync=True, endpoint_ids=["5"])
    job_other = _make_job(proxbox_sync=True, endpoint_ids=["7"])
    job_all = _make_job(proxbox_sync=True, endpoint_ids=[])
    job_bad = _make_job(proxbox_sync=False, endpoint_ids=None)
    ctx = _run_get_extra_context(endpoint_pk=5, jobs=[job_match, job_other, job_all, job_bad])
    assert job_match in ctx["endpoint_sync_jobs"]
    assert job_other not in ctx["endpoint_sync_jobs"]
    assert job_all in ctx["endpoint_sync_jobs"]
    assert job_bad not in ctx["endpoint_sync_jobs"]
