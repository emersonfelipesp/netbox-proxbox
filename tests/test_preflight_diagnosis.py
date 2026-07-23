"""Regression tests for sync preflight diagnosis and stage-failure attribution.

A fresh install reported a sync dying on the first stage with only
``Error ensuring Proxbox tag`` to go on. The real cause was several minutes
earlier: proxbox-api had just started, answered the preflight too slowly, and
the NetBox endpoint push (the only thing that gives the backend credentials to
write to NetBox) never landed. The preflight recorded a warning and let the run
continue, so the operator saw a downstream symptom instead of the cause.

These tests pin the three behaviors that make that diagnosable:

* the preflight fails loudly when the backend definitively holds no NetBox
  endpoint, instead of continuing into stages that cannot succeed;
* the backend's NetBox-endpoint list is read as a **three-way** answer, so
  "could not find out" is never mistaken for "there is none";
* a stage failure names the earlier preflight problem, and a transport failure
  reported under proxbox-api's class-default HTTP 400 is still retried.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.django_stubs import install_django_stubs


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── loaders ───────────────────────────────────────────────────────────────────


def _load_by_path(name: str, relative: str, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def backend_sync_module(monkeypatch):
    """Load ``views/backend_sync.py`` with its NetBox-facing imports stubbed."""
    # `DatabaseError` / `salted_hmac` are imported at module level — see
    # `tests/django_stubs.py` for why every loader of this file needs them.
    install_django_stubs(monkeypatch)

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    views_pkg = types.ModuleType("netbox_proxbox.views")
    views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    endpoint_enabled_mod = types.ModuleType("netbox_proxbox.services.endpoint_enabled")
    endpoint_enabled_mod.disabled_endpoint_detail = lambda endpoint, **kwargs: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.endpoint_enabled", endpoint_enabled_mod
    )

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxEndpoint = object
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    utils_mod = types.ModuleType("netbox_proxbox.utils")
    utils_mod.get_ip_address_host = lambda value: (
        str(value).split("/")[0] if value else "127.0.0.1"
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_mod)

    error_utils_mod = types.ModuleType("netbox_proxbox.views.error_utils")
    error_utils_mod.extract_backend_error_detail = lambda exc: (str(exc), None)

    def _parse_json(response, log_label=None):
        try:
            return response.json(), None
        except Exception as exc:  # pragma: no cover - defensive
            return None, str(exc)

    error_utils_mod.parse_requests_response_json = _parse_json
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.error_utils", error_utils_mod
    )

    return _load_by_path(
        "netbox_proxbox.views.backend_sync",
        "netbox_proxbox/views/backend_sync.py",
        monkeypatch,
    )


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load ``sync_stages.py`` with all heavy NetBox imports stubbed."""
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants = _load_by_path(
        "netbox_proxbox.constants", "netbox_proxbox/constants.py", monkeypatch
    )

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncModeChoices = SimpleNamespace(
        ALWAYS="always", BOOTSTRAP_ONLY="bootstrap_only", DISABLED="disabled"
    )
    choices_mod.SyncTypeChoices = SimpleNamespace(
        ALL="all",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        DEVICES="devices",
        STORAGE="storage",
        TASK_HISTORY="task-history",
        NETWORK_INTERFACES="network-interfaces",
        VM_INTERFACES="vm-interfaces",
        IP_ADDRESSES="ip-addresses",
        REPLICATIONS="replications",
        BACKUP_ROUTINES="backup-routines",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    bootstrap_mod = types.ModuleType("netbox_proxbox.netbox_bootstrap")
    bootstrap_mod.BOOTSTRAP_ONLY_TAG_SLUG = "bootstrap-only"
    bootstrap_mod.ensure_proxbox_tags = lambda: {}
    monkeypatch.setitem(sys.modules, "netbox_proxbox.netbox_bootstrap", bootstrap_mod)

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                use_guest_agent_interface_name=True,
                proxbox_fetch_max_concurrency=8,
                ignore_ipv6_link_local_addresses=True,
                primary_ip_preference="ipv4",
                **{field: "always" for field in constants.SYNC_MODE_FIELDS},
            )

    class _Manager:
        def filter(self, **kwargs):
            return self

        def first(self):
            return None

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = SimpleNamespace(objects=_Manager())
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    netbox_jobs_mod = types.ModuleType("netbox.jobs")
    netbox_jobs_mod.Job = object
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    for mod_name, filename in (
        ("netbox_proxbox.sync_types", "sync_types.py"),
        ("netbox_proxbox.sync_params", "sync_params.py"),
        ("netbox_proxbox.sync_ownership", "sync_ownership.py"),
    ):
        _load_by_path(mod_name, f"netbox_proxbox/{filename}", monkeypatch)

    return _load_by_path(
        "netbox_proxbox.sync_stages", "netbox_proxbox/sync_stages.py", monkeypatch
    )


def _make_logger():
    """A ``job.logger`` double that records each level's messages."""
    records: dict[str, list[str]] = {"info": [], "warning": [], "error": []}
    logger = SimpleNamespace(
        info=lambda msg: records["info"].append(str(msg)),
        warning=lambda msg: records["warning"].append(str(msg)),
        error=lambda msg: records["error"].append(str(msg)),
    )
    return logger, records


def _make_job():
    logger, records = _make_logger()
    job = SimpleNamespace(
        logger=logger,
        job=SimpleNamespace(save=lambda **kwargs: None),
    )
    return job, records


# ── list_backend_netbox_endpoints: the three-way answer ──────────────────────


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestListBackendNetBoxEndpoints:
    """``None`` (unknown) and ``[]`` (definitively none) must stay distinct.

    Only the second is safe to escalate to a blocking error; conflating them
    would turn any transient listing failure into a hard sync failure.
    """

    def test_empty_list_is_a_definitive_answer(self, backend_sync_module, monkeypatch):
        monkeypatch.setattr(
            backend_sync_module.requests, "get", lambda *a, **kw: _FakeResponse([])
        )
        rows, err = backend_sync_module.list_backend_netbox_endpoints(
            base_url="http://backend:8000"
        )
        assert rows == []
        assert err is None

    def test_populated_list_is_returned(self, backend_sync_module, monkeypatch):
        monkeypatch.setattr(
            backend_sync_module.requests,
            "get",
            lambda *a, **kw: _FakeResponse([{"id": 1, "name": "netbox"}, "junk"]),
        )
        rows, err = backend_sync_module.list_backend_netbox_endpoints(
            base_url="http://backend:8000"
        )
        assert rows == [{"id": 1, "name": "netbox"}]
        assert err is None

    def test_request_failure_is_unknown_not_empty(
        self, backend_sync_module, monkeypatch
    ):
        def _boom(*args, **kwargs):
            raise backend_sync_module.requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(backend_sync_module.requests, "get", _boom)
        rows, err = backend_sync_module.list_backend_netbox_endpoints(
            base_url="http://backend:8000"
        )
        assert rows is None
        assert err and "Failed to list NetBox endpoints" in err

    def test_non_list_payload_is_unknown_not_empty(
        self, backend_sync_module, monkeypatch
    ):
        monkeypatch.setattr(
            backend_sync_module.requests,
            "get",
            lambda *a, **kw: _FakeResponse({"detail": "nope"}),
        )
        rows, err = backend_sync_module.list_backend_netbox_endpoints(
            base_url="http://backend:8000"
        )
        assert rows is None
        assert err and "invalid NetBox endpoint list payload" in err

    def test_endpoint_push_timeout_leaves_room_for_a_cold_backend(
        self, backend_sync_module
    ):
        # The reported failure timed out at exactly 10.02s on a backend that
        # answered the same call in 3.78s once warm.
        assert backend_sync_module.BACKEND_ENDPOINT_PUSH_TIMEOUT >= 30

    def test_both_endpoint_pushes_use_the_shared_timeout(self, backend_sync_module):
        budget = backend_sync_module.BACKEND_ENDPOINT_PUSH_TIMEOUT
        for func in (
            backend_sync_module.sync_netbox_endpoint_to_backend,
            backend_sync_module.sync_proxmox_endpoint_to_backend,
            backend_sync_module.list_backend_netbox_endpoints,
        ):
            default = inspect.signature(func).parameters["timeout"].default
            assert default == budget, f"{func.__name__} must use the shared budget"


# ── preflight HTTP budgets ────────────────────────────────────────────────────


def _module_constants(relative: str) -> dict[str, object]:
    """Read a module's top-level literal assignments without importing it.

    ``backend_auth`` imports Django/NetBox at module scope, so it cannot be
    imported here. Parsing with ``ast`` and reading only literal nodes keeps
    this a pure source contract with no code execution.
    """
    tree = ast.parse((REPO_ROOT / relative).read_text())
    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                constants[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return constants


def test_preflight_auth_timeouts_absorb_a_cold_start() -> None:
    """The old 5s/10s bounds failed on start-up latency alone."""
    path = "netbox_proxbox/services/backend_auth.py"
    source = (REPO_ROOT / path).read_text()
    constants = _module_constants(path)

    assert constants["BOOTSTRAP_STATUS_TIMEOUT"] >= 15
    assert constants["REGISTER_KEY_TIMEOUT"] >= 20
    # The preflight wait must stay far below wait_for_backend_ready's own
    # defaults (30 retries / 30s apart) — a backend that is truly down should
    # fail the job quickly, not stall it for minutes.
    assert constants["PREFLIGHT_READY_MAX_RETRIES"] <= 10
    assert constants["PREFLIGHT_READY_MAX_DELAY"] <= 15

    assert "timeout=BOOTSTRAP_STATUS_TIMEOUT" in source
    assert "timeout=REGISTER_KEY_TIMEOUT" in source


def test_key_registration_uses_named_budgets_not_literals() -> None:
    """No bare numeric timeout may creep back into the key-registration path.

    The ``/health`` probe in ``wait_for_backend_ready`` keeps its short literal
    timeout on purpose — it is a *retried* readiness poll, so a slow answer just
    costs one cheap attempt. The two calls below get one shot each, which is why
    they must stay on the named budgets.
    """
    tree = ast.parse(
        (REPO_ROOT / "netbox_proxbox/services/backend_auth.py").read_text()
    )
    register = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_try_register_key"
    )

    budgets = [
        keyword.value
        for call in ast.walk(register)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "timeout"
    ]
    assert len(budgets) == 2, "expected the bootstrap-status and register-key calls"
    assert sorted(node.id for node in budgets if isinstance(node, ast.Name)) == [
        "BOOTSTRAP_STATUS_TIMEOUT",
        "REGISTER_KEY_TIMEOUT",
    ]


# ── stage retry classification ───────────────────────────────────────────────


class TestRetryableStageFailure:
    """proxbox-api reports *every* uncaught error as HTTP 400.

    That includes timeouts and refused connections, so a 400 whose text names a
    transport failure has to stay retryable while genuine 4xx rejections do not.
    """

    def test_server_errors_are_retryable(self, sync_stages_module):
        for status in (500, 502, 503, 504):
            assert sync_stages_module._is_retryable_stage_failure(status, {}) is True

    def test_rate_limit_is_retryable(self, sync_stages_module):
        assert sync_stages_module._is_retryable_stage_failure(429, {}) is True

    @pytest.mark.parametrize(
        "detail",
        [
            "HTTPConnectionPool(host='netbox', port=80): Read timed out.",
            "Connection refused",
            "502 Bad Gateway",
            "Server disconnected",
            "Name or service not known",
        ],
    )
    def test_transport_failure_under_400_is_retryable(self, sync_stages_module, detail):
        payload = {"message": "Sync failed", "detail": detail}
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is True

    def test_genuine_client_error_under_400_is_not_retryable(self, sync_stages_module):
        # This is the exact reported payload. It is deliberately NOT rescued
        # here: with no cause in the text there is nothing to distinguish it
        # from a real rejection. Fixing that needs a non-empty ``detail`` from
        # proxbox-api; this plugin-side gate is what will then retry it.
        payload = {
            "message": "Error ensuring Proxbox tag",
            "detail": None,
            "python_exception": None,
        }
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    def test_python_exception_field_is_consulted(self, sync_stages_module):
        """proxbox-api reports the underlying exception in its own field.

        ``_extract_backend_error_text()`` never reads ``python_exception``, so
        the classifier has to look at it directly or a bare ``ReadTimeout``
        would not be recognised as transport.
        """
        payload = {
            "message": "Sync failed",
            "detail": None,
            "python_exception": "ReadTimeout",
        }
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is True

    @pytest.mark.parametrize(
        "payload",
        [
            {"detail": "vmid 101 already exists", "timeout": 30},
            {"detail": "Invalid name", "vm": {"name": "connection-reset-lab"}},
            {"detail": "Rejected", "request": {"read_timeout": 3600}},
        ],
    )
    def test_marker_outside_the_cause_does_not_trigger_a_retry(
        self, sync_stages_module, payload
    ):
        """Only the *cause* fields are searched, never the payload as a whole.

        Matching the stringified payload would retry these genuine rejections
        twice over, purely because an unrelated value spells a marker word.
        """
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    @pytest.mark.parametrize(
        "detail",
        [
            "timeout must be between 1 and 300",
            "Field 'timeout' is required",
            "connection_error is not a valid state",
        ],
    )
    def test_a_marker_word_inside_a_validation_message_is_not_transport(
        self, sync_stages_module, detail
    ):
        """The cause field itself can spell a marker and still be a rejection.

        These are client-side validation failures whose text happens to name a
        transport concept. A bare ``"timeout"`` / ``"connection error"`` marker
        matched them and bought each one two pointless retries plus 16s of
        backoff, on a request that can never succeed as sent.
        """
        payload = {"message": "Sync failed", "detail": detail}
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    @pytest.mark.parametrize(
        "detail",
        [
            # nginx, which is what the published proxbox-api image serves through.
            "<html><head><title>504 Gateway Time-out</title></head>"
            "<body><center><h1>Gateway Time-out</h1></center></body></html>",
            "HTTPConnectionPool(host='proxbox', port=8800): "
            "Read timed out. (read timeout=5)",
            "Failed to establish a new connection: [Errno 111] Connection refused",
            "Server disconnected without sending a response.",
            "[Errno -2] Name or service not known",
            "[Errno -3] Temporary failure in name resolution",
            "[Errno 8] nodename nor servname provided, or not known",
            "EOF occurred in violation of protocol (_ssl.c:1006)",
        ],
    )
    def test_real_transport_failure_texts_are_matched(self, sync_stages_module, detail):
        """The markers must match what the transport layer actually emits.

        A 502/504 is retryable by status, so these only matter when proxbox-api
        catches the upstream failure and re-reports it under its default 400 —
        which is the exact path this whole classifier exists for. nginx spells
        its own 504 ``Gateway Time-out``, with a hyphen, so ``gateway timeout``
        alone did not match it.
        """
        payload = {"message": "Sync failed", "detail": detail}
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is True

    def test_transport_failure_nested_in_a_fastapi_detail_list_is_retryable(
        self, sync_stages_module
    ):
        """FastAPI reports ``detail`` as a list, hiding the cause one level down.

        A flat ``payload["detail"]`` read sees a ``list`` and finds no marker, so
        a genuine transport failure surfaced through a dependency error was
        classified as a permanent rejection and never retried.
        """
        payload = {
            "detail": [
                {"loc": ["body"], "msg": "Connection refused", "input": {"id": 1}}
            ]
        }
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is True

    def test_nested_input_echo_is_never_scanned(self, sync_stages_module):
        """``input`` echoes the submitted body — it is data, not a cause.

        Scanning it would let a VM named ``connection-refused`` (or a pushed
        endpoint payload) turn a rejection into a retry, and is the same field
        that carries credentials.
        """
        payload = {
            "detail": [
                {
                    "loc": ["body", "name"],
                    "msg": "String too long",
                    "input": {"name": "connection refused lab", "timeout": 30},
                }
            ]
        }
        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    def test_deeply_buried_cause_stops_at_the_recursion_limit(self, sync_stages_module):
        """Descent is bounded, so a pathological body cannot stall the classifier."""
        payload: dict[str, object] = {"detail": "Connection refused"}
        for _ in range(12):
            payload = {"detail": payload}

        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    def test_self_referential_payload_does_not_recurse_forever(
        self, sync_stages_module
    ):
        payload: dict[str, object] = {"message": "Sync failed"}
        payload["detail"] = payload

        assert sync_stages_module._is_retryable_stage_failure(400, payload) is False

    def test_non_dict_payload_is_matched_whole(self, sync_stages_module):
        """A bare string body *is* the error text, so match all of it."""
        assert (
            sync_stages_module._is_retryable_stage_failure(400, "Connection refused")
            is True
        )
        assert (
            sync_stages_module._is_retryable_stage_failure(400, "Bad request") is False
        )

    def test_other_4xx_are_never_retryable(self, sync_stages_module):
        for status in (401, 403, 404, 409, 422):
            assert (
                sync_stages_module._is_retryable_stage_failure(
                    status, {"detail": "connection refused"}
                )
                is False
            ), "a transport phrase must not make a real 4xx retryable"

    def test_retry_loop_consults_the_classifier(self, sync_stages_module, monkeypatch):
        """A 400 naming a timeout must actually be retried by the stage runner."""
        module = sync_stages_module
        calls = {"count": 0}

        def _run_sync_stream(path, query_params=None, on_frame=None, endpoint_id=None):
            calls["count"] += 1
            return {"detail": "Read timed out."}, 400

        services_mod = types.ModuleType("netbox_proxbox.services")
        services_mod.run_sync_stream = _run_sync_stream
        monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
        monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

        job, _records = _make_job()
        with pytest.raises(RuntimeError):
            module._execute_stage_sync(
                job, "devices", "/devices/stream", {}, lambda e, d: None
            )

        assert calls["count"] == module._STAGE_RETRY_MAX + 1, (
            "every attempt should be spent before giving up"
        )

    def test_non_retryable_failure_is_not_retried(
        self, sync_stages_module, monkeypatch
    ):
        module = sync_stages_module
        calls = {"count": 0}

        def _run_sync_stream(path, query_params=None, on_frame=None, endpoint_id=None):
            calls["count"] += 1
            return {"message": "Error ensuring Proxbox tag"}, 400

        services_mod = types.ModuleType("netbox_proxbox.services")
        services_mod.run_sync_stream = _run_sync_stream
        monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
        monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

        job, _records = _make_job()
        with pytest.raises(RuntimeError):
            module._execute_stage_sync(
                job, "devices", "/devices/stream", {}, lambda e, d: None
            )

        assert calls["count"] == 1


# ── preflight hint attribution ────────────────────────────────────────────────


def _fail_stage(module, monkeypatch, *, preflight_hint):
    def _run_sync_stream(path, query_params=None, on_frame=None, endpoint_id=None):
        return {"message": "Error ensuring Proxbox tag"}, 400

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = _run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    job, records = _make_job()
    with pytest.raises(RuntimeError) as excinfo:
        module._execute_stage_sync(
            job,
            "devices",
            "/devices/stream",
            {},
            lambda e, d: None,
            preflight_hint=preflight_hint,
        )
    return str(excinfo.value), records


class TestPreflightHintAttribution:
    """The stage error must point at the earlier cause, not just the symptom."""

    def test_hint_is_appended_to_the_user_facing_error(
        self, sync_stages_module, monkeypatch
    ):
        hint = "Preflight reported: the NetBox endpoint was not pushed to proxbox-api."
        message, records = _fail_stage(
            sync_stages_module, monkeypatch, preflight_hint=hint
        )
        assert hint in message
        assert any(
            "likely failed because of an earlier" in entry for entry in records["error"]
        ), "the job log must carry the attribution too"

    def test_no_hint_leaves_the_error_untouched(self, sync_stages_module, monkeypatch):
        message, records = _fail_stage(
            sync_stages_module, monkeypatch, preflight_hint=None
        )
        assert "Preflight reported" not in message
        assert not any(
            "likely failed because of an earlier" in entry for entry in records["error"]
        )

    def test_stage_runner_forwards_the_hint(self, sync_stages_module):
        for func in (
            sync_stages_module._execute_stage_sync,
            sync_stages_module._run_all_stages_sync,
        ):
            params = inspect.signature(func).parameters
            assert "preflight_hint" in params, f"{func.__name__} must accept the hint"
            assert params["preflight_hint"].default is None
