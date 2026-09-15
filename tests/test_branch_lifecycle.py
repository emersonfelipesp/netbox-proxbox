"""Tests for ``netbox_proxbox.services.branch_lifecycle``.

Pins the contract that ``ProxboxSyncJob`` relies on:

* ``resolve_branching_decision()`` distinguishes disabled, enabled, and
  configured-but-unavailable states.
* ``branching_enabled_settings()`` remains a companion-plugin compatibility
  wrapper, but raises instead of silently falling open when isolation is required.
* ``create_and_provision_branch()`` calls ``Branch.save(provision=False)`` and
  then ``Branch.provision(user=...)``, polls ``refresh_from_db`` until status
  becomes ``READY``, and raises ``RuntimeError`` on ``FAILED`` or timeout.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH_LIFECYCLE_PATH = (
    REPO_ROOT / "netbox_proxbox" / "services" / "branch_lifecycle.py"
)


def _install_branching_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plugin_settings: object,
    available: bool = True,
    importable: bool = True,
):
    """Load ``branch_lifecycle.py`` directly with stubbed deps."""

    # Bare parent packages so the qualified module name resolves.
    for name in ("netbox_proxbox", "netbox_proxbox.services"):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    models_pkg = types.ModuleType("netbox_proxbox.models")

    class _SettingsClass:
        @classmethod
        def get_solo(cls):
            return plugin_settings

    models_pkg.ProxboxPluginSettings = _SettingsClass
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_pkg)

    # is_branching_available() now requires the Django *app* to be loaded, not
    # merely the package to be importable: on NetBox 4.7 the branching plugin is
    # skipped (its max_version is 4.6.99) while remaining perfectly importable.
    # See tests/test_branching_availability.py.
    django_pkg = types.ModuleType("django")
    django_pkg.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    django_apps = types.ModuleType("django.apps")

    class _AppRegistry:
        def is_installed(self, label: str) -> bool:
            return available and label == "netbox_branching"

    django_apps.apps = _AppRegistry()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "django.apps", django_apps)

    if importable:
        nb = types.ModuleType("netbox_branching")
        monkeypatch.setitem(sys.modules, "netbox_branching", nb)
    else:
        monkeypatch.setitem(sys.modules, "netbox_branching", None)

    if available and importable:
        nb_choices = types.ModuleType("netbox_branching.choices")

        class _BranchStatusChoices:
            READY = "ready"
            FAILED = "failed"
            MERGED = "merged"
            NEW = "new"
            PROVISIONING = "provisioning"

        nb_choices.BranchStatusChoices = _BranchStatusChoices
        monkeypatch.setitem(sys.modules, "netbox_branching.choices", nb_choices)
        nb_models = types.ModuleType("netbox_branching.models")
        monkeypatch.setitem(sys.modules, "netbox_branching.models", nb_models)
    else:
        sys.modules.pop("netbox_branching.choices", None)
        sys.modules.pop("netbox_branching.models", None)

    sys.modules.pop("netbox_proxbox.services.branch_lifecycle", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.branch_lifecycle",
        BRANCH_LIFECYCLE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.branch_lifecycle"] = module
    spec.loader.exec_module(module)
    return module


def test_branching_enabled_settings_returns_none_when_flag_off(monkeypatch):
    settings = SimpleNamespace(branching_enabled=False)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    decision = mod.resolve_branching_decision()
    assert decision.state is mod.BranchingDecisionState.DISABLED
    assert decision.settings is None
    assert decision.reason is None
    assert decision.configured is False
    assert mod.branching_enabled_settings() is None


def test_configured_branching_is_unavailable_when_the_app_is_not_loaded(
    monkeypatch,
):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="proxbox-sync",
        branch_on_conflict="fail",
    )
    mod = _install_branching_stubs(
        monkeypatch, plugin_settings=settings, available=False
    )

    decision = mod.resolve_branching_decision()
    assert decision.state is mod.BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE
    assert decision.settings is None
    assert "Django app is not loaded" in decision.reason
    assert decision.configured is True
    with pytest.raises(mod.BranchingUnavailableError, match="Django app is not loaded"):
        mod.branching_enabled_settings()


def test_branching_enabled_settings_returns_dict_when_enabled(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="custom-prefix",
        branch_on_conflict="acknowledge",
    )
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    expected = {
        "prefix": "custom-prefix",
        "on_conflict": "acknowledge",
    }
    decision = mod.resolve_branching_decision()
    assert decision.state is mod.BranchingDecisionState.ENABLED
    assert decision.settings == expected
    assert decision.reason is None
    assert decision.configured is True
    assert mod.branching_enabled_settings() == expected


def test_enabled_request_requires_an_active_ready_branch_schema(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    decision = mod.require_branch_isolation_or_raise()

    with pytest.raises(
        mod.ActiveBranchRequiredError,
        match="activate a branch or disable branch isolation",
    ):
        mod.require_active_branch_schema_id(decision)


def test_enabled_request_returns_the_active_ready_branch_schema(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    contextvars = types.ModuleType("netbox_branching.contextvars")
    active_branch = ContextVar("active_branch", default=None)
    branch = SimpleNamespace(
        name="request-branch",
        status="ready",
        schema_id="schema-request",
        refresh_from_db=lambda: None,
    )
    active_branch.set(branch)
    contextvars.active_branch = active_branch
    monkeypatch.setitem(sys.modules, "netbox_branching.contextvars", contextvars)

    decision = mod.require_branch_isolation_or_raise()

    assert mod.require_active_branch_schema_id(decision) == "schema-request"


def test_branching_enabled_settings_uses_defaults_for_blank_values(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="",
        branch_on_conflict="",
    )
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    assert mod.branching_enabled_settings() == {
        "prefix": "proxbox-sync",
        "on_conflict": "fail",
    }


def test_branching_settings_failure_is_configured_but_unavailable(monkeypatch):
    """If the singleton cannot be loaded, the wrapper must fail closed."""

    class _Boom:
        @classmethod
        def get_solo(cls):
            raise RuntimeError("db down")

    mod = _install_branching_stubs(monkeypatch, plugin_settings=None)
    # Replace the stubbed ProxboxPluginSettings with one that raises.
    monkeypatch.setattr(mod, "ProxboxPluginSettings", _Boom)

    decision = mod.resolve_branching_decision()
    assert decision.state is mod.BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE
    assert "settings could not be loaded" in decision.reason
    assert decision.configured is None
    with pytest.raises(
        mod.BranchingUnavailableError, match="settings could not be loaded"
    ):
        mod.branching_enabled_settings()


def test_configured_branching_is_unavailable_when_the_app_import_fails(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(
        monkeypatch,
        plugin_settings=settings,
        available=True,
        importable=False,
    )

    decision = mod.resolve_branching_decision()
    assert decision.state is mod.BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE
    assert "could not import" in decision.reason


class _FakeBranch:
    """Records save/provision/refresh calls and walks through scripted statuses."""

    def __init__(self, name: str, statuses: list[str]) -> None:
        self.name = name
        self.schema_id = "abcd1234"
        self.status = statuses[0]
        self._statuses = list(statuses)
        self.save_calls: list[dict] = []
        self.provision_calls: list[object | None] = []
        self.refresh_calls = 0

    def save(self, **kwargs):
        self.save_calls.append(kwargs)

    def provision(self, *, user):
        self.provision_calls.append(user)

    def refresh_from_db(self):
        self.refresh_calls += 1
        if len(self._statuses) > 1:
            # Advance the scripted status sequence on each refresh.
            self._statuses.pop(0)
            self.status = self._statuses[0]


def _install_branch_class(monkeypatch, branch_instance):
    """Replace ``netbox_branching.models.Branch`` with a factory yielding our stub."""

    nb_models = sys.modules["netbox_branching.models"]

    def _branch_factory(name):
        branch_instance.name = name
        return branch_instance

    nb_models.Branch = _branch_factory


def test_create_and_provision_branch_polls_until_ready(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(
        name="placeholder",
        statuses=["new", "provisioning", "ready"],
    )
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    user = SimpleNamespace(username="op")
    result = mod.create_and_provision_branch(name="b-1", user=user)

    assert result is branch
    assert branch.name == "b-1"
    assert branch.save_calls == [{"provision": False}]
    assert branch.provision_calls == [user]
    assert branch.refresh_calls >= 2


@pytest.mark.parametrize("schema_id", ["", "   ", None])
def test_ready_branch_without_usable_schema_id_fails_closed(monkeypatch, schema_id):
    """READY is unsafe until the branch has a non-empty schema identifier."""
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    branch = _FakeBranch(name="placeholder", statuses=["ready"])
    if schema_id is None:
        del branch.schema_id
    else:
        branch.schema_id = schema_id
    _install_branch_class(monkeypatch, branch)

    with pytest.raises(
        mod.BranchingUnavailableError,
        match="READY without a usable schema_id",
    ):
        mod.create_and_provision_branch(name="b-no-schema", user=None)


def test_activate_sync_branch_uses_netbox_branching_context(monkeypatch):
    """Programmatic activation must enter and restore the supplied branch."""
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    utilities = types.ModuleType("netbox_branching.utilities")
    active: list[object] = []

    @contextmanager
    def activate_branch(branch):
        active.append(branch)
        try:
            yield
        finally:
            assert active.pop() is branch

    utilities.activate_branch = activate_branch
    monkeypatch.setitem(sys.modules, "netbox_branching.utilities", utilities)
    branch = _FakeBranch(name="b-1", statuses=["ready"])

    with mod.activate_sync_branch(branch):
        assert active == [branch]

    assert active == []


def test_activate_sync_branch_rechecks_status_before_each_activation(monkeypatch):
    """A branch that changes status between local phases must stop the run."""
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    utilities = types.ModuleType("netbox_branching.utilities")

    @contextmanager
    def activate_branch(branch):
        yield

    utilities.activate_branch = activate_branch
    monkeypatch.setitem(sys.modules, "netbox_branching.utilities", utilities)
    branch = _FakeBranch(name="b-changing", statuses=["ready", "ready", "failed"])

    with mod.activate_sync_branch(branch):
        pass
    with pytest.raises(mod.BranchingUnavailableError, match="b-changing.*left open"):
        with mod.activate_sync_branch(branch):
            pytest.fail("a non-READY branch was activated")


def test_activate_sync_branch_names_activation_exception_and_disposition(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    utilities = types.ModuleType("netbox_branching.utilities")

    @contextmanager
    def activate_branch(branch):
        del branch
        raise RuntimeError("context activation failed")
        yield  # pragma: no cover

    utilities.activate_branch = activate_branch
    monkeypatch.setitem(sys.modules, "netbox_branching.utilities", utilities)
    branch = _FakeBranch(name="b-activation", statuses=["ready"])

    with pytest.raises(
        mod.BranchingUnavailableError,
        match="b-activation.*context activation failed.*left open",
    ):
        with mod.activate_sync_branch(branch):
            pytest.fail("failed activation entered its body")


def test_activate_sync_branch_restores_contextvar_after_body_exception(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)
    utilities = types.ModuleType("netbox_branching.utilities")
    active = ContextVar("test_active_branch", default="main")

    @contextmanager
    def activate_branch(branch):
        token = active.set(branch)
        try:
            yield
        finally:
            active.reset(token)

    utilities.activate_branch = activate_branch
    monkeypatch.setitem(sys.modules, "netbox_branching.utilities", utilities)
    branch = _FakeBranch(name="b-context", statuses=["ready"])

    with pytest.raises(RuntimeError, match="service failed"):
        with mod.activate_sync_branch(branch):
            assert active.get() is branch
            raise RuntimeError("service failed")

    assert active.get() == "main"


def test_create_and_provision_branch_raises_on_failed(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(name="placeholder", statuses=["new", "failed"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="FAILED"):
        mod.create_and_provision_branch(name="b-fail", user=None)


def test_create_and_provision_branch_times_out(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(name="placeholder", statuses=["new"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    times = iter([0.0, 0.1, 0.2, 99.0])
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(times))

    with pytest.raises(RuntimeError, match="did not reach READY"):
        mod.create_and_provision_branch(
            name="b-slow", user=None, ready_timeout_seconds=1
        )


def test_create_and_provision_branch_propagates_provision_failure(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    class _BoomBranch(_FakeBranch):
        def provision(self, *, user):
            raise RuntimeError("provision boom")

    branch = _BoomBranch(name="placeholder", statuses=["new"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="provision boom"):
        mod.create_and_provision_branch(name="b-prov", user=None)
