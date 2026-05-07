"""Tests for the per-endpoint overwrite resolution and global fallback.

Exercises both:

- ``ProxmoxEndpoint.effective_overwrites()`` tri-state semantics (per-field
  ``None`` falls back to the global ``ProxboxPluginSettings`` value, ``True``/
  ``False`` overrides it).
- ``effective_overwrites_for_endpoint()`` in ``sync_params.py``: routes to the
  global singleton when the endpoint id is empty/zero/missing/invalid, or to a
  specific endpoint's resolved values when it loads.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_constants():
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_for_overwrites",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_overwrites_like_model(endpoint, settings, fields):
    """Mirror of ``ProxmoxEndpoint.effective_overwrites()`` body.

    Same dict-comprehension semantics: per-field ``None`` on the endpoint
    falls back to the matching attribute on the plugin settings singleton.
    """
    return {
        name: getattr(endpoint, name)
        if getattr(endpoint, name) is not None
        else getattr(settings, name)
        for name in fields
    }


@pytest.fixture
def overwrite_fields() -> tuple[str, ...]:
    return _load_constants().OVERWRITE_FIELDS


def test_effective_overwrites_all_inherited_when_endpoint_fields_are_none(
    overwrite_fields,
):
    settings = SimpleNamespace(**{name: True for name in overwrite_fields})
    endpoint = SimpleNamespace(**{name: None for name in overwrite_fields})

    resolved = _resolve_overwrites_like_model(endpoint, settings, overwrite_fields)

    assert resolved == {name: True for name in overwrite_fields}


def test_effective_overwrites_endpoint_overrides_win(overwrite_fields):
    settings = SimpleNamespace(**{name: True for name in overwrite_fields})
    overrides = {name: None for name in overwrite_fields}
    overrides["overwrite_vm_tags"] = False
    overrides["overwrite_device_role"] = False
    endpoint = SimpleNamespace(**overrides)

    resolved = _resolve_overwrites_like_model(endpoint, settings, overwrite_fields)

    assert resolved["overwrite_vm_tags"] is False
    assert resolved["overwrite_device_role"] is False
    for name in overwrite_fields:
        if name in {"overwrite_vm_tags", "overwrite_device_role"}:
            continue
        assert resolved[name] is True


def test_effective_overwrites_endpoint_true_overrides_global_false(overwrite_fields):
    settings = SimpleNamespace(**{name: False for name in overwrite_fields})
    overrides = {name: None for name in overwrite_fields}
    overrides["overwrite_ip_tags"] = True
    endpoint = SimpleNamespace(**overrides)

    resolved = _resolve_overwrites_like_model(endpoint, settings, overwrite_fields)

    assert resolved["overwrite_ip_tags"] is True
    for name in overwrite_fields:
        if name == "overwrite_ip_tags":
            continue
        assert resolved[name] is False


# ---------------------------------------------------------------------------
# effective_overwrites_for_endpoint(): global-fallback wrapper
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_params_module(monkeypatch):
    """Load ``sync_params.py`` with stubbed model imports.

    ``netbox_proxbox.models`` is replaced with a fake module exposing
    ``ProxboxPluginSettings`` and ``ProxmoxEndpoint``; both default to global=
    True for every flag and an empty endpoint queryset, but tests can override
    them via ``module._stubs``.
    """
    constants = _load_constants()
    fields = constants.OVERWRITE_FIELDS

    state: dict[str, object] = {
        "global": {name: True for name in fields},
        "endpoints_by_pk": {},
        "raise_on_get_solo": None,
    }

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            if state["raise_on_get_solo"] is not None:
                raise state["raise_on_get_solo"]
            return SimpleNamespace(**state["global"])

    class _Manager:
        def filter(self, **kwargs):
            self._pk = kwargs.get("pk")
            return self

        def first(self):
            return state["endpoints_by_pk"].get(self._pk)

    class _ProxmoxEndpoint:
        objects = _Manager()

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = fields
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        ALL="all",
        VIRTUAL_MACHINES="virtual-machines",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    sync_types_mod = types.ModuleType("netbox_proxbox.sync_types")
    import re

    sync_types_mod._TARGETED_VM_JOB_NAME_RE = re.compile(r"^Sync VM (\d+)")
    sync_types_mod._TARGETED_VM_SYNC_TYPES = ("virtual-machines",)
    sync_types_mod.normalize_sync_types = lambda x: list(x or [])
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sync_types", sync_types_mod)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    sys.modules.pop("netbox_proxbox.sync_params", None)
    path = REPO_ROOT / "netbox_proxbox" / "sync_params.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.sync_params", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.sync_params"] = module
    spec.loader.exec_module(module)
    module._stubs = state  # type: ignore[attr-defined]
    return module


def _make_endpoint(fields, **overrides):
    values = {name: None for name in fields}
    values.update(overrides)
    obj = SimpleNamespace(**values)

    def effective_overwrites(_self=obj, _fields=fields):
        return {
            name: getattr(_self, name) if getattr(_self, name) is not None else True
            for name in _fields
        }

    obj.effective_overwrites = effective_overwrites
    return obj


@pytest.mark.parametrize("missing_id", [None, "", 0, "0"])
def test_effective_overwrites_returns_global_for_empty_id(
    sync_params_module, overwrite_fields, missing_id
):
    sync_params_module._stubs["global"] = {
        name: (name != "overwrite_vm_tags") for name in overwrite_fields
    }

    result = sync_params_module.effective_overwrites_for_endpoint(missing_id)

    assert result["overwrite_vm_tags"] is False
    for name in overwrite_fields:
        if name == "overwrite_vm_tags":
            continue
        assert result[name] is True


def test_effective_overwrites_returns_global_when_endpoint_missing(
    sync_params_module, overwrite_fields
):
    sync_params_module._stubs["endpoints_by_pk"] = {}
    sync_params_module._stubs["global"] = {name: True for name in overwrite_fields}

    result = sync_params_module.effective_overwrites_for_endpoint(42)

    assert result == {name: True for name in overwrite_fields}


def test_effective_overwrites_returns_global_for_invalid_string_id(
    sync_params_module, overwrite_fields
):
    sync_params_module._stubs["global"] = {name: True for name in overwrite_fields}

    result = sync_params_module.effective_overwrites_for_endpoint("not-an-int")

    assert result == {name: True for name in overwrite_fields}


def test_effective_overwrites_uses_endpoint_when_loaded(
    sync_params_module, overwrite_fields
):
    endpoint = _make_endpoint(
        overwrite_fields,
        overwrite_vm_tags=False,
        overwrite_ip_status=False,
    )
    sync_params_module._stubs["endpoints_by_pk"] = {7: endpoint}
    sync_params_module._stubs["global"] = {name: True for name in overwrite_fields}

    result = sync_params_module.effective_overwrites_for_endpoint(7)

    assert result["overwrite_vm_tags"] is False
    assert result["overwrite_ip_status"] is False
    for name in overwrite_fields:
        if name in {"overwrite_vm_tags", "overwrite_ip_status"}:
            continue
        assert result[name] is True


def test_effective_overwrites_falls_back_when_get_solo_raises(
    sync_params_module, overwrite_fields
):
    sync_params_module._stubs["raise_on_get_solo"] = RuntimeError("no settings")

    result = sync_params_module.effective_overwrites_for_endpoint(None)

    assert result == {name: True for name in overwrite_fields}


def test_effective_overwrites_keys_match_canonical_field_set(
    sync_params_module, overwrite_fields
):
    result = sync_params_module.effective_overwrites_for_endpoint(None)
    assert tuple(result.keys()) == tuple(overwrite_fields)
    assert len(result) == 23
