"""Behavioral guards for the lifetime VM ownership of an intent row."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"
ERROR = "The virtual machine for an existing Proxmox VM intent cannot be changed."


class _ValidationError(Exception):
    pass


def _module(name: str, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _load(monkeypatch, dotted_name: str, path: Path, stubs: dict[str, object]):
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(dotted_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, dotted_name, module)
    spec.loader.exec_module(module)
    return module


def _form_module(monkeypatch):
    class _BaseForm:
        pass

    class _VirtualMachine:
        objects = SimpleNamespace(all=lambda: ())

    forms = _module(
        "django.forms",
        ValidationError=_ValidationError,
        Textarea=lambda **kwargs: kwargs,
        ModelMultipleChoiceField=lambda **kwargs: kwargs,
        CharField=lambda **kwargs: kwargs,
    )
    django = _module("django", forms=forms)
    return _load(
        monkeypatch,
        "netbox_proxbox.forms.vm_intent",
        ROOT / "forms" / "vm_intent.py",
        {
            "django": django,
            "django.forms": forms,
            "netbox": _module("netbox"),
            "netbox.forms": _module(
                "netbox.forms",
                NetBoxModelFilterSetForm=_BaseForm,
                NetBoxModelForm=_BaseForm,
            ),
            "utilities": _module("utilities"),
            "utilities.forms": _module("utilities.forms"),
            "utilities.forms.fields": _module(
                "utilities.forms.fields",
                DynamicModelChoiceField=lambda **kwargs: kwargs,
            ),
            "virtualization": _module("virtualization"),
            "virtualization.models": _module(
                "virtualization.models", VirtualMachine=_VirtualMachine
            ),
            "netbox_proxbox.models": _module(
                "netbox_proxbox.models", ProxmoxVMIntent=type("Intent", (), {})
            ),
        },
    )


def _serializer_module(monkeypatch):
    class _BaseSerializer:
        pass

    serializers = _module(
        "rest_framework.serializers",
        ValidationError=_ValidationError,
        HyperlinkedIdentityField=lambda **kwargs: kwargs,
    )
    rest_framework = _module("rest_framework", serializers=serializers)
    return _load(
        monkeypatch,
        "netbox_proxbox.api.serializers.vm_intent",
        ROOT / "api" / "serializers" / "vm_intent.py",
        {
            "netbox": _module("netbox"),
            "netbox.api": _module("netbox.api"),
            "netbox.api.serializers": _module(
                "netbox.api.serializers", NetBoxModelSerializer=_BaseSerializer
            ),
            "rest_framework": rest_framework,
            "rest_framework.serializers": serializers,
            "netbox_proxbox.api": _module("netbox_proxbox.api"),
            "netbox_proxbox.api.serializers": _module("netbox_proxbox.api.serializers"),
            "netbox_proxbox.api.serializers.sync_state": _module(
                "netbox_proxbox.api.serializers.sync_state",
                NestedVirtualMachineSerializer=lambda: object(),
            ),
            "netbox_proxbox.models": _module(
                "netbox_proxbox.models", ProxmoxVMIntent=type("Intent", (), {})
            ),
        },
    )


def test_form_rejects_reassigning_an_existing_intent(monkeypatch):
    module = _form_module(monkeypatch)
    form = object.__new__(module.ProxmoxVMIntentForm)
    form.instance = SimpleNamespace(pk=11, virtual_machine_id=101)
    form.cleaned_data = {"virtual_machine": SimpleNamespace(pk=202)}

    with pytest.raises(_ValidationError, match=ERROR):
        form.clean_virtual_machine()


def test_form_allows_the_existing_parent_and_new_rows(monkeypatch):
    module = _form_module(monkeypatch)
    selected = SimpleNamespace(pk=101)
    form = object.__new__(module.ProxmoxVMIntentForm)
    form.cleaned_data = {"virtual_machine": selected}

    form.instance = SimpleNamespace(pk=11, virtual_machine_id=101)
    assert form.clean_virtual_machine() is selected

    form.instance = SimpleNamespace(pk=None, virtual_machine_id=None)
    assert form.clean_virtual_machine() is selected


def test_api_rejects_reassigning_an_existing_intent(monkeypatch):
    module = _serializer_module(monkeypatch)
    serializer = object.__new__(module.ProxmoxVMIntentSerializer)
    serializer.instance = SimpleNamespace(pk=12, virtual_machine_id=303)

    with pytest.raises(_ValidationError, match=ERROR):
        serializer.validate_virtual_machine(SimpleNamespace(pk=404))


def test_api_allows_the_existing_parent_and_new_rows(monkeypatch):
    module = _serializer_module(monkeypatch)
    selected = SimpleNamespace(pk=303)
    serializer = object.__new__(module.ProxmoxVMIntentSerializer)

    serializer.instance = SimpleNamespace(pk=12, virtual_machine_id=303)
    assert serializer.validate_virtual_machine(selected) is selected

    serializer.instance = None
    assert serializer.validate_virtual_machine(selected) is selected
