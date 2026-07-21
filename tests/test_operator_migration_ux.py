"""Contracts for issue #217 operator sync-state repair UX."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from tests.conftest import load_plugin_module

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "sync_state_repair.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "urls.py"
VIEWS_INIT_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "__init__.py"
BACKEND_PROXY_PATH = REPO_ROOT / "netbox_proxbox" / "services" / "backend_proxy.py"
SETTINGS_TEMPLATE = (
    REPO_ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox" / "settings.html"
)
HOME_TEMPLATE = (
    REPO_ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox" / "home.html"
)
BOOTSTRAP_PARTIAL = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "partials"
    / "bootstrap_status_card.html"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _backend_proxy_functions() -> dict[str, ast.FunctionDef]:
    module = ast.parse(_read(BACKEND_PROXY_PATH))
    return {
        node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
    }


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_repair_sync_state_route_is_registered():
    urls = _read(URLS_PATH)

    assert '"sync-state/repair/"' in urls
    assert "views.RepairSyncStateView.as_view()" in urls
    assert 'name="repair_sync_state"' in urls
    assert '"sync-state/bootstrap-status/"' in urls
    assert "views.BootstrapStatusView.as_view()" in urls
    assert 'name="bootstrap_status"' in urls


def test_repair_view_is_exported_from_views_package():
    init_source = _read(VIEWS_INIT_PATH)

    assert (
        "from .sync_state_repair import BootstrapStatusView, RepairSyncStateView"
        in init_source
    )
    assert "BootstrapStatusView" in init_source


def test_repair_view_uses_session_gate_and_sync_enqueue_permission():
    view_source = _read(VIEW_PATH)

    # The session gate is ContentTypePermissionRequiredMixin alone. An earlier
    # revision also listed ConditionalLoginRequiredMixin, but commit 39f8f9d9
    # ("Fix invalid MRO on the sync-state repair view base classes") removed it
    # deliberately -- combining the two produced an invalid MRO. This assertion
    # was left behind and has been failing on develop ever since; it now pins
    # the gate the view actually uses, and that the removed mixin stays out.
    assert "ContentTypePermissionRequiredMixin" in view_source
    assert "ConditionalLoginRequiredMixin" not in view_source
    assert "permission_enqueue_proxbox_sync" in view_source
    assert "def get_required_permission" in view_source
    assert "ProxboxSyncJob.enqueue" in view_source
    assert "PROXBOX_SYNC_QUEUE_NAME" in view_source
    assert "SyncTypeChoices.ALL" in view_source


def test_bootstrap_status_uses_fastapi_view_permission():
    view_source = _read(VIEW_PATH)

    assert "permission_view_fastapi_endpoint" in view_source
    assert "build_bootstrap_status_context" in view_source
    assert "build_bootstrap_status_payload" in view_source
    assert "has_perm(permission_view_fastapi_endpoint())" in view_source
    assert 'FastAPIEndpoint.objects.restrict(request.user, "view")' in view_source


def test_backend_proxy_wires_extras_reconcile_and_bootstrap_status():
    source = _read(BACKEND_PROXY_PATH)

    assert '"extras/custom-fields/reconcile"' in source
    assert '"extras/bootstrap-status"' in source
    assert 'method="POST"' in source
    assert 'method="GET"' in source
    assert "request_backend_json" in source
    assert "endpoint_id: int | None = None" in source
    assert "get_fastapi_request_context(endpoint_id=endpoint_id)" in source


def test_backend_json_auth_retry_preserves_scoped_endpoint_id():
    funcs = _backend_proxy_functions()
    request_json = funcs["request_backend_json"]

    kwonly_args = [arg.arg for arg in request_json.args.kwonlyargs]
    assert "endpoint_id" in kwonly_args
    endpoint_index = kwonly_args.index("endpoint_id")
    assert isinstance(request_json.args.kw_defaults[endpoint_index], ast.Constant)
    assert request_json.args.kw_defaults[endpoint_index].value is None

    retry_calls = [
        node
        for node in ast.walk(request_json)
        if isinstance(node, ast.Call)
        and _call_name(node) == "_handle_auth_registration_and_retry"
    ]
    assert retry_calls, "request_backend_json must retain the auth retry hook"
    assert any(
        keyword.arg == "endpoint_id"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "endpoint_id"
        for call in retry_calls
        for keyword in call.keywords
    )

    for func_name in (
        "get_backend_bootstrap_status",
        "reconcile_backend_custom_fields",
    ):
        wrapper = funcs[func_name]
        request_calls = [
            node
            for node in ast.walk(wrapper)
            if isinstance(node, ast.Call) and _call_name(node) == "request_backend_json"
        ]
        assert request_calls, f"{func_name} must call request_backend_json"
        assert any(
            keyword.arg == "endpoint_id"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "endpoint_id"
            for call in request_calls
            for keyword in call.keywords
        ), f"{func_name} must pass the scoped endpoint_id into request_backend_json"


def test_settings_and_home_templates_expose_bootstrap_status_card():
    partial = _read(BOOTSTRAP_PARTIAL)

    assert "bootstrap_status.can_view" in partial
    assert "data-proxbox-bootstrap-status-card" in partial
    assert "data-proxbox-bootstrap-refresh" in partial
    assert "plugins:netbox_proxbox:bootstrap_status" in partial
    assert "plugins:netbox_proxbox:repair_sync_state" in partial
    assert "Repair / Rebuild Proxbox sync-state" in partial
    assert "innerHTML" not in partial
    assert "bootstrap_status_card.html" in _read(SETTINGS_TEMPLATE)
    assert "bootstrap_status_card.html" in _read(HOME_TEMPLATE)


def test_repair_outcome_success_reconciles_then_queues_full_sync(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    enqueue_calls: list[dict[str, object]] = []

    class _Job:
        def get_absolute_url(self):
            return "/core/jobs/17/"

    def enqueue_sync(**kwargs):
        enqueue_calls.append(kwargs)
        return _Job()

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=lambda: ({"ok": True, "response": {"created": 3}}, 200),
        enqueue_sync=enqueue_sync,
        endpoint_ids=[10, 20],
    )

    assert outcome.ok is True
    assert outcome.status == "success"
    assert enqueue_calls == [
        {
            "instance": None,
            "user": SimpleNamespace(username="operator"),
            "queue_name": "default",
            "name": enqueue_calls[0]["name"],
            "sync_types": ["all"],
            "proxmox_endpoint_ids": [10, 20],
        }
    ]


def test_repair_outcome_permission_denied_skips_backend_and_enqueue(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )

    def fail_reconcile():
        raise AssertionError("reconcile must not run without permission")

    def fail_enqueue(**kwargs):
        raise AssertionError("enqueue must not run without permission")

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(),
        can_enqueue=False,
        reconcile_backend=fail_reconcile,
        enqueue_sync=fail_enqueue,
        endpoint_ids=[],
    )

    assert outcome.ok is False
    assert outcome.status == "permission_denied"
    assert "permission" in outcome.message


def test_repair_outcome_backend_error_skips_sync_enqueue(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    enqueue_calls: list[dict[str, object]] = []

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(),
        can_enqueue=True,
        reconcile_backend=lambda: (
            {"ok": True, "response": {"ok": False, "detail": "reconcile failed"}},
            200,
        ),
        enqueue_sync=lambda **kwargs: enqueue_calls.append(kwargs),
        endpoint_ids=[1],
    )

    assert outcome.ok is False
    assert outcome.status == "backend_error"
    assert outcome.backend_status == 200
    assert "reconcile failed" in outcome.message
    assert enqueue_calls == []


def test_repair_outcome_active_full_sync_skips_reconcile_and_enqueue(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    active_job = SimpleNamespace(get_absolute_url=lambda: "/core/jobs/19/")

    def fail_reconcile():
        raise AssertionError("reconcile must not run when an active job exists")

    def fail_enqueue(**kwargs):
        raise AssertionError("enqueue must not run when an active job exists")

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=fail_reconcile,
        enqueue_sync=fail_enqueue,
        endpoint_ids=[1],
        active_job_check=lambda user, endpoint_ids: active_job,
    )

    assert outcome.ok is False
    assert outcome.status == "already_running"
    assert outcome.job is active_job
    assert "No duplicate repair sync was queued" in outcome.message


def test_bootstrap_status_payload_inner_backend_failure_surfaces_detail(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm: True))

    payload, status = module.build_bootstrap_status_payload(
        request,
        fetch_status=lambda: (
            {"ok": True, "response": {"ok": False, "detail": "bootstrap failed"}},
            200,
        ),
    )

    assert status == 200
    assert payload["ok"] is False
    assert payload["http_status"] == 200
    assert payload["detail"] == "bootstrap failed"
    assert payload["payload"] == {"ok": False, "detail": "bootstrap failed"}


def test_bootstrap_status_context_defers_backend_fetch(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm: True))

    context = module.build_bootstrap_status_context(request, surface="home")

    assert context["bootstrap_status"]["can_view"] is True
    assert context["bootstrap_status"]["deferred"] is True
    assert context["bootstrap_status_json"] == ""
