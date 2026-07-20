"""Behavior tests for the per-endpoint "Create Sync Job" modal handler.

``handle_endpoint_sync_routine_post`` is the NetBox-independent core of the
Sync Jobs tab's create-routine modal (issue #208). It is loadable via the
stubbed ``load_plugin_module`` harness so its gating, hard endpoint scoping
(both Proxmox and NetBox sides), fail-closed enqueue, and immediate-vs-recurring
behavior can be verified without a live NetBox.
"""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


def _load(monkeypatch):
    return load_plugin_module(
        "netbox_proxbox.views.schedule_sync", monkeypatch=monkeypatch
    )


def _make_form_class(*, valid: bool, cleaned: dict | None = None):
    """Return a fake ``ScheduleSyncForm`` capturing constructor + cleaned_data."""

    class _FakeForm:
        instances: list = []

        def __init__(self, post_data, use_bootstrap_sync_checkboxes=False):
            self.post_data = post_data
            self.use_bootstrap_sync_checkboxes = use_bootstrap_sync_checkboxes
            self.cleaned_data = dict(cleaned or {})
            _FakeForm.instances.append(self)

        def is_valid(self):
            return valid

    return _FakeForm


def _request(*, allowed: bool = True):
    return SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm: allowed))


def _patch_common(monkeypatch, module, form_cls, captured):
    monkeypatch.setattr(module, "ScheduleSyncForm", form_cls)
    monkeypatch.setattr(
        module, "permission_enqueue_proxbox_sync", lambda: "core.add_job"
    )
    monkeypatch.setattr(
        module.ProxboxSyncJob,
        "enqueue",
        classmethod(lambda cls, **kw: captured.append(kw)),
    )
    monkeypatch.setattr(module, "schedule_sync_success_message", lambda form: "queued")


def _valid_cleaned(**overrides):
    base = {
        "sync_types": ["all"],
        "schedule_at": None,
        "interval": None,
        "job_name": "",
        "proxmox_endpoint_ids": [],
        "netbox_endpoint_ids": [],
    }
    base.update(overrides)
    return base


def test_created_hard_scopes_proxmox_to_viewed_endpoint(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    # POST body deliberately targets *other* endpoints; scoping must override it.
    form_cls = _make_form_class(
        valid=True,
        cleaned=_valid_cleaned(proxmox_endpoint_ids=["3", "9"]),
    )
    _patch_common(monkeypatch, module, form_cls, captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    req = _request()
    outcome, form = module.handle_endpoint_sync_routine_post(
        req, endpoint, {"proxmox_endpoints": ["3", "9"]}
    )

    assert outcome == "created"
    assert len(captured) == 1
    # Fail-closed hard scoping: always exactly the viewed endpoint, never [].
    assert captured[0]["proxmox_endpoint_ids"] == ["5"]
    assert form.cleaned_data["proxmox_endpoint_ids"] == ["5"]
    # Direct-enqueue contract: the other kwargs ProxboxSyncJob.enqueue consumes.
    assert captured[0]["instance"] is None
    assert captured[0]["user"] is req.user
    assert captured[0]["queue_name"] == module.PROXBOX_SYNC_QUEUE_NAME
    assert captured[0]["sync_types"] == ["all"]
    assert ("success", "queued") in module.messages.calls


def test_created_ignores_crafted_netbox_endpoints(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    # A crafted POST supplies a NetBox endpoint the modal never exposes.
    form_cls = _make_form_class(
        valid=True,
        cleaned=_valid_cleaned(netbox_endpoint_ids=["9"]),
    )
    _patch_common(monkeypatch, module, form_cls, captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "created"
    assert captured[0]["netbox_endpoint_ids"] == []
    assert form.cleaned_data["netbox_endpoint_ids"] == []


def test_created_immediate_one_time_has_no_interval(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    form_cls = _make_form_class(
        valid=True, cleaned=_valid_cleaned(schedule_at=None, interval=None)
    )
    _patch_common(monkeypatch, module, form_cls, captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, _form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "created"
    assert captured[0]["interval"] is None
    assert captured[0]["schedule_at"] is None


def test_created_recurring_forwards_interval_and_schedule(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    marker = object()
    form_cls = _make_form_class(
        valid=True,
        cleaned=_valid_cleaned(schedule_at=marker, interval=240, job_name="Nightly"),
    )
    _patch_common(monkeypatch, module, form_cls, captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, _form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "created"
    assert captured[0]["interval"] == 240
    assert captured[0]["schedule_at"] is marker
    assert captured[0]["name"] == "Nightly"


def test_missing_add_job_permission_is_forbidden(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    _patch_common(monkeypatch, module, _make_form_class(valid=True), captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, form = module.handle_endpoint_sync_routine_post(
        _request(allowed=False), endpoint, {}
    )

    assert outcome == "forbidden"
    assert form is None
    assert captured == []


def test_disabled_endpoint_is_refused(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    _patch_common(monkeypatch, module, _make_form_class(valid=True), captured)
    endpoint = SimpleNamespace(pk=5, enabled=False)

    outcome, form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "disabled"
    assert captured == []
    assert (
        "warning",
        "Disabled Proxmox endpoints cannot run sync jobs.",
    ) in module.messages.calls


def test_invalid_form_returns_bound_form_and_does_not_enqueue(monkeypatch):
    module = _load(monkeypatch)
    captured: list = []
    form_cls = _make_form_class(valid=False)
    _patch_common(monkeypatch, module, form_cls, captured)
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "invalid"
    assert form is form_cls.instances[-1]
    assert captured == []


def test_enqueue_failure_reports_error(monkeypatch):
    module = _load(monkeypatch)
    form_cls = _make_form_class(valid=True, cleaned=_valid_cleaned())
    monkeypatch.setattr(module, "ScheduleSyncForm", form_cls)
    monkeypatch.setattr(
        module, "permission_enqueue_proxbox_sync", lambda: "core.add_job"
    )

    def boom(cls, **kwargs):
        raise RuntimeError("queue offline")

    monkeypatch.setattr(module.ProxboxSyncJob, "enqueue", classmethod(boom))
    endpoint = SimpleNamespace(pk=5, enabled=True)

    outcome, form = module.handle_endpoint_sync_routine_post(_request(), endpoint, {})

    assert outcome == "error"
    assert any(level == "error" for level, _msg in module.messages.calls)
