"""Source + template contracts for the Sync Jobs tab "Create Sync Job" modal.

Issue #208 adds a create-routine modal to the Proxmox endpoint Sync Jobs tab.
The heavy ``views/endpoints/proxmox.py`` module is not loadable without a live
NetBox, so structural guarantees are pinned here via AST + template-string
contracts (mirroring ``test_endpoint_sync_jobs_tab.py``). Runtime behavior of the
handler is covered in ``test_endpoint_sync_job_create.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROXMOX_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
SCHEDULE_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "schedule_sync.py"
TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_sync_jobs.html"
)


@pytest.fixture(scope="module")
def proxmox_ast() -> ast.Module:
    return ast.parse(PROXMOX_VIEW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def proxmox_src() -> str:
    return PROXMOX_VIEW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def schedule_ast() -> ast.Module:
    return ast.parse(SCHEDULE_VIEW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schedule_src() -> str:
    return SCHEDULE_VIEW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template_src() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _module_all(module: ast.Module) -> set[str]:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__all__":
                    return {
                        e.value for e in node.value.elts if isinstance(e, ast.Constant)
                    }
    raise AssertionError("__all__ not found")


def _method_source(cls: ast.ClassDef, name: str, src: str) -> str:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(src, node)
            assert segment is not None
            return segment
    raise AssertionError(f"method {name} not found on {cls.name}")


# ── views/endpoints/proxmox.py contracts ────────────────────────────────────


def test_endpoint_sync_jobs_for_is_module_level_and_exported(proxmox_ast):
    top_level_funcs = {
        n.name for n in proxmox_ast.body if isinstance(n, ast.FunctionDef)
    }
    assert "endpoint_sync_jobs_for" in top_level_funcs
    assert "endpoint_sync_jobs_for" in _module_all(proxmox_ast)


def test_sync_jobs_tab_view_handles_post(proxmox_ast):
    cls = _find_class(proxmox_ast, "ProxmoxEndpointSyncJobsTabView")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "post" in methods
    assert "get_extra_context" in methods


def test_get_extra_context_exposes_modal_form_and_flag(proxmox_ast, proxmox_src):
    cls = _find_class(proxmox_ast, "ProxmoxEndpointSyncJobsTabView")
    body = _method_source(cls, "get_extra_context", proxmox_src)
    assert "schedule_form" in body
    assert "ScheduleSyncForm" in body
    assert "show_create_modal" in body
    # Modal defaults to one-time (blank interval) so "blank schedule = immediate"
    # is truthful and an untouched submit is not silently recurring.
    assert '"interval_value"].initial = None' in body


def test_post_delegates_to_handler_and_reopens_modal_on_invalid(
    proxmox_ast, proxmox_src
):
    cls = _find_class(proxmox_ast, "ProxmoxEndpointSyncJobsTabView")
    body = _method_source(cls, "post", proxmox_src)
    assert "handle_endpoint_sync_routine_post" in body
    # 403 on forbidden, redirect back to the same tab, re-render with modal open.
    assert "status=403" in body
    assert "proxmoxendpoint_sync_jobs" in body
    assert '"show_create_modal": True' in body


# ── views/schedule_sync.py contracts ────────────────────────────────────────


def test_handler_defined_and_exported(schedule_ast):
    top_level_funcs = {
        n.name for n in schedule_ast.body if isinstance(n, ast.FunctionDef)
    }
    assert "handle_endpoint_sync_routine_post" in top_level_funcs
    assert "handle_endpoint_sync_routine_post" in _module_all(schedule_ast)


def test_handler_hard_scopes_both_endpoint_sides(schedule_src):
    # Proxmox side scoped to the viewed endpoint...
    assert "scoped_proxmox_ids = [str(endpoint.pk)]" in schedule_src
    assert 'cleaned_data["proxmox_endpoint_ids"] = scoped_proxmox_ids' in schedule_src
    # ...and the NetBox-endpoint picker (not exposed by the modal) hard-scoped too.
    assert 'cleaned_data["netbox_endpoint_ids"] = []' in schedule_src


def test_handler_enqueues_directly_to_fail_closed(schedule_src):
    # Must NOT route through enqueue_proxbox_sync_from_valid_form (which re-filters
    # by enabled=True and can fall through to an all-endpoints sync on empty). The
    # explicit id list passed to ProxboxSyncJob.enqueue fails closed.
    assert "ProxboxSyncJob.enqueue(**enqueue_kwargs)" in schedule_src
    assert '"proxmox_endpoint_ids": scoped_proxmox_ids' in schedule_src


# ── template contracts ──────────────────────────────────────────────────────


def test_template_has_gated_create_button(template_src):
    assert "Create Sync Job" in template_src
    assert "perms.core.add_job" in template_src
    # Disabled endpoints get a disabled button with an explanatory tooltip.
    assert "Disabled endpoints cannot run sync jobs." in template_src


def test_template_modal_posts_to_the_tab(template_src):
    assert 'id="proxbox-create-sync-job-modal"' in template_src
    assert (
        "{% url 'plugins:netbox_proxbox:proxmoxendpoint_sync_jobs' pk=object.pk %}"
        in template_src
    )
    assert "{% csrf_token %}" in template_src


def test_template_renders_scoped_field_subset_only(template_src):
    # The scheduling fields we surface in the modal.
    for field in (
        "schedule_form.job_name",
        "schedule_form.sync_types",
        "schedule_form.schedule_at",
        "schedule_form.interval_value",
        "schedule_form.interval_unit",
    ):
        assert field in template_src, field
    # The endpoint pickers must NOT appear — the endpoint is fixed to this one.
    assert "schedule_form.proxmox_endpoints" not in template_src
    assert "schedule_form.netbox_endpoints" not in template_src
    assert "Target endpoint" in template_src


def test_template_autoopens_modal_on_validation_error(template_src):
    assert "show_create_modal" in template_src
    assert "proxbox-create-sync-job-modal" in template_src
    assert "bootstrap.Modal" in template_src
