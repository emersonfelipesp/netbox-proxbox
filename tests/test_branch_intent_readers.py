"""Every branch safety-gate reader must use the shared resolver."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
READERS = {
    ROOT / "netbox_proxbox" / "views" / "plan_summary.py": (
        ("_branch_intent_flags", None),
    ),
    ROOT / "netbox_proxbox" / "intent" / "merge_validator.py": (
        ("_branch_opted_in", "apply_to_proxmox"),
        ("_branch_destroy_confirmed", "apply_destroy_confirmed"),
    ),
    ROOT / "netbox_proxbox" / "intent" / "apply_job.py": (
        ("_branch_destroy_confirmed", "apply_destroy_confirmed"),
    ),
    ROOT / "netbox_proxbox" / "signal_receivers.py": (
        ("_branch_opted_in", "apply_to_proxmox"),
    ),
}


def _module(name: str, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _install_reader_stubs(monkeypatch, calls):
    class _JobRunner:
        pass

    class _PlanClientError(Exception):
        pass

    def resolve_branch_intent_flags(branch):
        calls.append(branch)
        return SimpleNamespace(
            apply_to_proxmox=True,
            apply_destroy_confirmed=True,
        )

    package_names = (
        "django",
        "netbox",
        "netbox_proxbox",
        "netbox_proxbox.intent",
        "netbox_proxbox.services",
        "netbox_proxbox.views",
        "utilities",
    )
    stubs = {}
    for name in package_names:
        package = _module(name)
        package.__path__ = []  # type: ignore[attr-defined]
        stubs[name] = package

    stubs.update(
        {
            "django.apps": _module(
                "django.apps",
                apps=SimpleNamespace(is_installed=lambda _name: False),
            ),
            "django.dispatch": _module(
                "django.dispatch",
                receiver=lambda *_args, **_kwargs: lambda function: function,
            ),
            "django.http": _module(
                "django.http",
                HttpRequest=type("HttpRequest", (), {}),
                HttpResponse=type("HttpResponse", (), {}),
            ),
            "django.shortcuts": _module(
                "django.shortcuts",
                render=lambda *_args, **_kwargs: None,
            ),
            "django.utils": _module(
                "django.utils",
                timezone=SimpleNamespace(now=lambda: None),
            ),
            "django.views": _module("django.views", View=type("View", (), {})),
            "netbox.constants": _module(
                "netbox.constants",
                RQ_QUEUE_DEFAULT="default",
            ),
            "netbox.jobs": _module(
                "netbox.jobs",
                Job=type("Job", (), {}),
                JobRunner=_JobRunner,
            ),
            "utilities.views": _module(
                "utilities.views",
                ConditionalLoginRequiredMixin=type(
                    "ConditionalLoginRequiredMixin",
                    (),
                    {},
                ),
            ),
            "netbox_proxbox.intent.diff_classify": _module(
                "netbox_proxbox.intent.diff_classify",
                classify_diff=lambda *_args: ("update", "qemu"),
            ),
            "netbox_proxbox.intent.diff_union": _module(
                "netbox_proxbox.intent.diff_union",
                virtual_machine_diff_id=lambda *_args: None,
                virtual_machine_diff_name=lambda *_args: None,
                virtual_machine_diff_union=lambda *_args: [],
            ),
            "netbox_proxbox.intent.firewall_common": _module(
                "netbox_proxbox.intent.firewall_common",
                save_status_for_firewall_object=lambda *_args, **_kwargs: None,
            ),
            "netbox_proxbox.intent.firewall_payload": _module(
                "netbox_proxbox.intent.firewall_payload",
                build_firewall_apply_diff=lambda *_args: {},
                build_firewall_plan_diffs=lambda *_args: [],
                default_proxmox_endpoint_id=lambda: None,
                firewall_changediffs=lambda *_args: [],
                firewall_result_key=lambda *_args: "key",
                first_endpoint_id_from_diffs=lambda *_args: None,
                unsupported_firewall_diff_message=lambda *_args: "unsupported",
            ),
            "netbox_proxbox.intent.intent_writes": _module(
                "netbox_proxbox.intent.intent_writes",
                stamp_intent_state=lambda *_args, **_kwargs: None,
            ),
            "netbox_proxbox.intent.payload": _module(
                "netbox_proxbox.intent.payload",
                build_lxc_payload=lambda *_args: {},
                build_update_delta=lambda *_args: {},
                build_vm_payload=lambda *_args: {},
            ),
            "netbox_proxbox.intent.plan_client": _module(
                "netbox_proxbox.intent.plan_client",
                PlanClientError=_PlanClientError,
                PlanClientResult=type("PlanClientResult", (), {}),
                call_plan_endpoint=lambda *_args: None,
            ),
            "netbox_proxbox.intent.proxmox_tags": _module(
                "netbox_proxbox.intent.proxmox_tags",
                tag_pending_deletion=lambda *_args, **_kwargs: False,
            ),
            "netbox_proxbox.intent.snapshot": _module(
                "netbox_proxbox.intent.snapshot",
                build_deleted_metadata_snapshot=lambda *_args: {},
                build_metadata_snapshot=lambda *_args: {},
            ),
            "netbox_proxbox.models": _module(
                "netbox_proxbox.models",
                DeletionRequest=type("DeletionRequest", (), {}),
                ProxmoxApplyJob=type("ProxmoxApplyJob", (), {}),
                ProxboxPluginSettings=SimpleNamespace(
                    objects=SimpleNamespace(first=lambda: None)
                ),
            ),
            "netbox_proxbox.services.backend_context": _module(
                "netbox_proxbox.services.backend_context",
                get_fastapi_request_context=lambda: None,
            ),
            "netbox_proxbox.services.branch_intent": _module(
                "netbox_proxbox.services.branch_intent",
                resolve_branch_intent_flags=resolve_branch_intent_flags,
            ),
            "netbox_proxbox.views.error_utils": _module(
                "netbox_proxbox.views.error_utils",
                extract_backend_error_detail=lambda *_args: ("error", None),
            ),
        }
    )
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.mark.parametrize(
    ("path", "function_name", "expected"),
    [
        (
            ROOT / "netbox_proxbox" / "views" / "plan_summary.py",
            "_branch_intent_flags",
            (True, True),
        ),
        (
            ROOT / "netbox_proxbox" / "intent" / "merge_validator.py",
            "_branch_opted_in",
            True,
        ),
        (
            ROOT / "netbox_proxbox" / "intent" / "merge_validator.py",
            "_branch_destroy_confirmed",
            True,
        ),
        (
            ROOT / "netbox_proxbox" / "intent" / "apply_job.py",
            "_branch_destroy_confirmed",
            True,
        ),
        (
            ROOT / "netbox_proxbox" / "signal_receivers.py",
            "_branch_opted_in",
            True,
        ),
    ],
)
def test_every_reader_is_driven_by_the_resolver_with_empty_legacy_data(
    monkeypatch,
    path,
    function_name,
    expected,
):
    calls = []
    _install_reader_stubs(monkeypatch, calls)
    module_name = f"branch_intent_reader_{path.stem}_{function_name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    branch = SimpleNamespace(custom_field_data={})

    result = getattr(module, function_name)(branch)

    if function_name == "_branch_intent_flags":
        result = (result.apply_to_proxmox, result.apply_destroy_confirmed)
    assert result == expected
    assert calls == [branch]


def _function(path: Path, function_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )


@pytest.mark.parametrize(
    ("path", "function_name", "expected_attribute"),
    [
        (path, function_name, expected_attribute)
        for path, functions in READERS.items()
        for function_name, expected_attribute in functions
    ],
)
def test_every_reader_uses_the_shared_resolver(
    path,
    function_name,
    expected_attribute,
):
    function = _function(path, function_name)
    imports = [node for node in ast.walk(function) if isinstance(node, ast.ImportFrom)]
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]

    assert any(
        node.module == "netbox_proxbox.services.branch_intent"
        and any(alias.name == "resolve_branch_intent_flags" for alias in node.names)
        for node in imports
    )
    assert any(
        isinstance(call.func, ast.Name)
        and call.func.id == "resolve_branch_intent_flags"
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "branch"
        for call in calls
    )
    returned = function.body[-1]
    assert isinstance(returned, ast.Return)
    if expected_attribute is None:
        assert isinstance(returned.value, ast.Call)
        assert isinstance(returned.value.func, ast.Name)
        assert returned.value.func.id == "resolve_branch_intent_flags"
    else:
        assert isinstance(returned.value, ast.Attribute)
        assert returned.value.attr == expected_attribute
        assert isinstance(returned.value.value, ast.Call)
        assert isinstance(returned.value.value.func, ast.Name)
        assert returned.value.value.func.id == "resolve_branch_intent_flags"


def test_no_branch_reader_consults_custom_field_data() -> None:
    for path in READERS:
        source = path.read_text(encoding="utf-8")
        assert "custom_field_data" not in source, path


def test_refusal_messages_name_the_branch_intent_setting_not_custom_fields() -> None:
    source = (ROOT / "netbox_proxbox" / "views" / "plan_summary.py").read_text(
        encoding="utf-8"
    )
    validator = (ROOT / "netbox_proxbox" / "intent" / "merge_validator.py").read_text(
        encoding="utf-8"
    )
    assert "Branch intent setting apply_to_proxmox" in source
    assert "Proxbox branch intent" in validator
    assert "branch CF" not in source
    assert "branch CF" not in validator
