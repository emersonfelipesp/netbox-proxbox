"""Tests for ``branch_lifecycle.merge_branch`` and ``branch_has_conflicts``.

These two helpers encode the plugin's branch_on_conflict policy:

* ``branch_has_conflicts`` is a thin wrapper around
  ``ChangeDiff.objects.filter(branch=..., conflicts__isnull=False).exists()``.
* ``merge_branch`` reads ``on_conflict`` from ProxboxPluginSettings and decides
  whether to call ``branch.merge(user=...)``. When conflicts exist:
  - ``on_conflict='fail'`` returns ``(False, message)`` and leaves the branch
    open (no ``merge`` call).
  - ``on_conflict='acknowledge'`` proceeds to call ``merge``.
* On a successful ``branch.merge()`` it returns ``(True, message)``.
* When ``branch.merge()`` raises, it returns ``(False, error_message)`` rather
  than propagating, so the caller decides how to fail the job.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH_LIFECYCLE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "services"
    / "branch_lifecycle.py"
)


class _FakeChangeDiffManager:
    """Records ``.filter(...).exists()`` query kwargs and returns a scripted bool."""

    def __init__(self, has_conflicts: bool) -> None:
        self.has_conflicts = has_conflicts
        self.filter_calls: list[dict] = []

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        manager = self

        class _QS:
            def exists(self):
                return manager.has_conflicts

        return _QS()


def _install_branching_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    has_conflicts: bool = False,
):
    """Load ``branch_lifecycle.py`` with stubs for the netbox-branching plugin."""

    for name in ("netbox_proxbox", "netbox_proxbox.services"):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    models_pkg = types.ModuleType("netbox_proxbox.models")

    class _SettingsClass:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(branching_enabled=True)

    models_pkg.ProxboxPluginSettings = _SettingsClass
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_pkg)

    nb = types.ModuleType("netbox_branching")
    monkeypatch.setitem(sys.modules, "netbox_branching", nb)

    nb_choices = types.ModuleType("netbox_branching.choices")

    class _BranchStatusChoices:
        READY = "ready"
        FAILED = "failed"

    nb_choices.BranchStatusChoices = _BranchStatusChoices
    monkeypatch.setitem(sys.modules, "netbox_branching.choices", nb_choices)

    nb_models = types.ModuleType("netbox_branching.models")
    cdm = _FakeChangeDiffManager(has_conflicts=has_conflicts)

    class _ChangeDiff:
        objects = cdm

    nb_models.ChangeDiff = _ChangeDiff
    monkeypatch.setitem(sys.modules, "netbox_branching.models", nb_models)

    sys.modules.pop("netbox_proxbox.services.branch_lifecycle", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.branch_lifecycle",
        BRANCH_LIFECYCLE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.branch_lifecycle"] = module
    spec.loader.exec_module(module)
    return module, cdm


class _FakeBranch:
    """Records merge calls; raise_on_merge optionally simulates merge failure."""

    def __init__(self, name: str = "branch-1", raise_on_merge: bool = False) -> None:
        self.name = name
        self.merge_calls: list[object | None] = []
        self._raise_on_merge = raise_on_merge

    def merge(self, *, user):
        self.merge_calls.append(user)
        if self._raise_on_merge:
            raise RuntimeError("merge strategy refused")


# ---------------------------------------------------------------------------
# branch_has_conflicts
# ---------------------------------------------------------------------------


def test_branch_has_conflicts_filters_by_branch_and_non_null_conflicts(monkeypatch):
    mod, cdm = _install_branching_stubs(monkeypatch, has_conflicts=True)

    branch = _FakeBranch()
    assert mod.branch_has_conflicts(branch) is True
    assert cdm.filter_calls == [{"branch": branch, "conflicts__isnull": False}]


def test_branch_has_conflicts_returns_false_when_no_rows(monkeypatch):
    mod, _ = _install_branching_stubs(monkeypatch, has_conflicts=False)

    assert mod.branch_has_conflicts(_FakeBranch()) is False


# ---------------------------------------------------------------------------
# merge_branch — happy path
# ---------------------------------------------------------------------------


def test_merge_branch_no_conflicts_calls_merge_with_user(monkeypatch):
    mod, _ = _install_branching_stubs(monkeypatch, has_conflicts=False)

    branch = _FakeBranch(name="b-clean")
    user = SimpleNamespace(username="op")

    merged, message = mod.merge_branch(branch=branch, user=user, on_conflict="fail")

    assert merged is True
    assert branch.merge_calls == [user]
    assert "b-clean" in message and "merged" in message


# ---------------------------------------------------------------------------
# merge_branch — on_conflict='fail'
# ---------------------------------------------------------------------------


def test_merge_branch_fail_policy_with_conflicts_does_not_merge(monkeypatch):
    mod, _ = _install_branching_stubs(monkeypatch, has_conflicts=True)

    branch = _FakeBranch(name="b-conflicted")
    merged, message = mod.merge_branch(
        branch=branch, user=None, on_conflict="fail"
    )

    assert merged is False
    assert branch.merge_calls == [], "merge must not be invoked under 'fail' policy"
    assert "unresolved conflicts" in message
    assert "b-conflicted" in message


# ---------------------------------------------------------------------------
# merge_branch — on_conflict='acknowledge'
# ---------------------------------------------------------------------------


def test_merge_branch_acknowledge_policy_proceeds_despite_conflicts(monkeypatch):
    mod, _ = _install_branching_stubs(monkeypatch, has_conflicts=True)

    branch = _FakeBranch(name="b-ack")
    user = SimpleNamespace(username="op")

    merged, message = mod.merge_branch(
        branch=branch, user=user, on_conflict="acknowledge"
    )

    assert merged is True
    assert branch.merge_calls == [user]
    assert "merged" in message


# ---------------------------------------------------------------------------
# merge_branch — merge() raises
# ---------------------------------------------------------------------------


def test_merge_branch_returns_failure_when_merge_raises(monkeypatch):
    mod, _ = _install_branching_stubs(monkeypatch, has_conflicts=False)

    branch = _FakeBranch(name="b-boom", raise_on_merge=True)
    merged, message = mod.merge_branch(
        branch=branch, user=None, on_conflict="fail"
    )

    assert merged is False
    assert "merge failed" in message
    assert "merge strategy refused" in message
