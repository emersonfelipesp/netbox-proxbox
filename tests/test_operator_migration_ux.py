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


def test_bootstrap_status_card_is_hidden_until_it_needs_attention():
    partial = _read(BOOTSTRAP_PARTIAL)

    # The card is hidden when the user can view status (JS reveals on a problem)
    # OR cannot repair; it is server-visible only for a repair-only user
    # (can repair but not view status), so it never shows permanently for the
    # common both-permissions case yet an authorized repairer keeps the action.
    assert (
        'class="card mb-3{% if bootstrap_status.can_view or '
        'not can_repair_sync_state %} d-none{% endif %}"' in partial
    )
    assert "data-can-view=" in partial
    assert "bootstrap_status.can_view|yesno" in partial

    # It only reveals for a genuine backend-reported problem (HTTP 200 + ok:false)
    # and never auto-hides once revealed.
    assert "function needsAttention(data)" in partial
    assert "data.ok === false" in partial
    assert "Number(data.http_status) === 200" in partial
    assert "function revealCard(card)" in partial
    assert "revealCard(card)" in partial
    # revealCard only ever un-hides (setHidden(card, false)); there is no
    # setHidden(card, true) that would auto-hide a revealed card.
    assert "setHidden(card, false)" in partial
    assert "setHidden(card, true)" not in partial

    # It auto-checks on load only when the user can view status.
    assert 'card.getAttribute("data-can-view") === "true"' in partial
    # Still no innerHTML anywhere in the (now larger) inline JS.
    assert "innerHTML" not in partial


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


def test_repair_outcome_reconcile_failure_still_queues_rebuild_sync(monkeypatch):
    # A custom-field reconcile failure is non-fatal: proxbox-api may be holding a
    # stale/invalid NetBox credential (the "Invalid v1 token" bootstrap failure),
    # and the very reconcile POST authenticates with that broken credential. The
    # rebuild sync's preflight re-pushes fresh credentials and rebuilds the
    # sidecars, so the repair MUST still enqueue it and surface the reconcile
    # detail as a warning rather than dead-ending.
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    enqueue_calls: list[dict[str, object]] = []

    class _Job:
        def get_absolute_url(self):
            return "/core/jobs/21/"

    def enqueue_sync(**kwargs):
        enqueue_calls.append(kwargs)
        return _Job()

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=lambda: (
            {"ok": True, "response": {"ok": False, "detail": "Invalid v1 token"}},
            200,
        ),
        enqueue_sync=enqueue_sync,
        endpoint_ids=[1],
    )

    assert outcome.ok is True
    assert outcome.status == "success"
    assert outcome.backend_status == 200
    assert outcome.reconcile_warning == "Invalid v1 token"
    assert "Invalid v1 token" in outcome.message
    assert "rebuild sync job has been queued" in outcome.message
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["sync_types"] == ["all"]
    assert enqueue_calls[0]["proxmox_endpoint_ids"] == [1]


def test_repair_outcome_reconcile_exception_still_queues_rebuild_sync(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    enqueue_calls: list[dict[str, object]] = []

    class _Job:
        def get_absolute_url(self):
            return "/core/jobs/22/"

    def raise_reconcile():
        raise RuntimeError("backend unreachable")

    def enqueue_sync(**kwargs):
        enqueue_calls.append(kwargs)
        return _Job()

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=raise_reconcile,
        enqueue_sync=enqueue_sync,
        endpoint_ids=[1],
    )

    assert outcome.ok is True
    assert outcome.status == "success"
    assert outcome.backend_status == 503
    assert outcome.reconcile_warning == "backend unreachable"
    assert len(enqueue_calls) == 1


def test_repair_outcome_enqueue_failure_after_reconcile_warning_is_fatal(monkeypatch):
    # Reconcile is non-fatal, but a failure to actually QUEUE the rebuild sync is
    # a hard error: nothing recovers the state, so the operator must be told.
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )

    def enqueue_sync(**kwargs):
        raise RuntimeError("queue down")

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=lambda: (
            {"ok": True, "response": {"ok": False, "detail": "Invalid v1 token"}},
            200,
        ),
        enqueue_sync=enqueue_sync,
        endpoint_ids=[1],
    )

    assert outcome.ok is False
    assert outcome.status == "enqueue_error"
    assert outcome.reconcile_warning == "Invalid v1 token"
    assert "could not be queued" in outcome.message
    assert "queue down" in outcome.message


def test_repair_outcome_transport_error_reconcile_still_queues_rebuild_sync(
    monkeypatch,
):
    # A transport-level reconcile failure (outer proxy envelope non-ok, non-2xx
    # status) is classified as not-ok by backend_payload_result and must be
    # treated exactly like an inner ok:false: warn and still queue the rebuild.
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    enqueue_calls: list[dict[str, object]] = []

    class _Job:
        def get_absolute_url(self):
            return "/core/jobs/23/"

    def enqueue_sync(**kwargs):
        enqueue_calls.append(kwargs)
        return _Job()

    outcome = module.build_sync_state_repair_outcome(
        user=SimpleNamespace(username="operator"),
        can_enqueue=True,
        reconcile_backend=lambda: (
            {"ok": False, "detail": "Unable to reach the ProxBox backend."},
            503,
        ),
        enqueue_sync=enqueue_sync,
        endpoint_ids=[1],
    )

    assert outcome.ok is True
    assert outcome.status == "success"
    assert outcome.backend_status == 503
    assert outcome.reconcile_warning == "Unable to reach the ProxBox backend."
    assert len(enqueue_calls) == 1


def _run_repair_post(module, monkeypatch, outcome):
    """Drive RepairSyncStateView.post() with a crafted outcome, capturing the
    flash-message level and the redirect target."""
    calls: list[str] = []

    fake_messages = SimpleNamespace(
        success=lambda request, msg: calls.append("success"),
        warning=lambda request, msg: calls.append("warning"),
        error=lambda request, msg: calls.append("error"),
    )
    monkeypatch.setattr(module, "messages", fake_messages)
    monkeypatch.setattr(module, "format_html", lambda *a, **k: "msg")
    monkeypatch.setattr(module, "redirect", lambda name: SimpleNamespace(target=name))
    monkeypatch.setattr(
        module, "build_sync_state_repair_outcome", lambda **kwargs: outcome
    )

    request = SimpleNamespace(
        user=SimpleNamespace(has_perm=lambda perm: True),
        POST={"next": "home"},
    )
    response = module.RepairSyncStateView().post(request)
    return calls, response


def test_repair_view_uses_warning_flash_when_reconcile_warned(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    job = SimpleNamespace(get_absolute_url=lambda: "/core/jobs/24/")
    outcome = module.SyncStateRepairOutcome(
        status="success",
        message="queued with warning",
        job=job,
        backend_status=200,
        reconcile_warning="Invalid v1 token",
    )

    calls, response = _run_repair_post(module, monkeypatch, outcome)

    assert calls == ["warning"]
    assert response.target == "plugins:netbox_proxbox:home"


def test_repair_view_uses_success_flash_when_reconcile_clean(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.sync_state_repair", monkeypatch=monkeypatch
    )
    job = SimpleNamespace(get_absolute_url=lambda: "/core/jobs/25/")
    outcome = module.SyncStateRepairOutcome(
        status="success",
        message="queued clean",
        job=job,
        backend_status=200,
        reconcile_warning=None,
    )

    calls, _ = _run_repair_post(module, monkeypatch, outcome)

    assert calls == ["success"]


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
