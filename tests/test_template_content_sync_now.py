"""Behavioral coverage for registered Sync Now action URL resolution."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "template_content.py"
)
CARD_TEMPLATE_PATH = (
    MODULE_PATH.parent / "templates" / "netbox_proxbox" / "inc" / "vm_proxmox_card.html"
)
SYNC_PERMISSION = "core.add_job"
OPERATION_PERMISSION = "core.run_proxmox_action"


class _User:
    def __init__(self, *permissions: str):
        self.permissions = frozenset(permissions)

    def has_perm(self, permission: str) -> bool:
        return permission in self.permissions


class _Relation:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _ObjectQuery:
    def __init__(self):
        self.value = None
        self.select_related_fields = ()

    def select_related(self, *fields):
        self.select_related_fields = fields
        return self

    def filter(self, **kwargs):
        return self

    def first(self):
        return self.value


def _model_class(name: str, *, app_label: str, model_name: str | None = None):
    model = type(name, (), {})
    model._meta = SimpleNamespace(
        app_label=app_label,
        model_name=model_name or name.lower(),
    )
    return model


def _module(name: str, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


@pytest.fixture
def template_content_module(monkeypatch):
    """Load ``template_content`` against small, route-recording NetBox stubs."""
    calls = {"get_viewname": [], "reverse": []}

    class NoReverseMatch(Exception):
        pass

    def get_viewname(target, action=None, rest_api=False):
        calls["get_viewname"].append((target, action, rest_api))
        prefix = f"{target._meta.app_label}:{target._meta.model_name}"
        if target._meta.app_label == "netbox_proxbox":
            prefix = f"plugins:{prefix}"
        return f"{prefix}_{action}" if action else prefix

    def reverse(viewname, kwargs=None):
        calls["reverse"].append((viewname, kwargs))
        return f"/route/{viewname}/{kwargs['pk']}/"

    class PluginTemplateExtension:
        def __init__(self, context):
            self.context = context
            self.render_calls = []

        def render(self, template_name, context=None):
            context = context or {}
            self.render_calls.append((template_name, context))
            if template_name == "netbox_proxbox/inc/vm_proxmox_card.html":
                return "rendered-proxmox-card"
            return str(context.get("action_url", ""))

    model_classes = {
        name: _model_class(name, app_label="netbox_proxbox")
        for name in (
            "ProxmoxCluster",
            "ProxmoxFirewallAlias",
            "ProxmoxFirewallIPSet",
            "ProxmoxFirewallIPSetEntry",
            "ProxmoxFirewallOptions",
            "ProxmoxFirewallRule",
            "ProxmoxFirewallSecurityGroup",
            "ProxmoxNode",
            "ProxmoxStorage",
            "VMBackup",
            "VMSnapshot",
            "VMTaskHistory",
        )
    }
    model_classes["ProxmoxEndpoint"] = _model_class(
        "ProxmoxEndpoint", app_label="netbox_proxbox"
    )
    virtual_machine = _model_class(
        "VirtualMachine",
        app_label="virtualization",
        model_name="virtualmachine",
    )
    virtual_machine.objects = _ObjectQuery()
    job = _model_class("Job", app_label="core", model_name="job")

    model_module = _module("netbox_proxbox.models", **model_classes)
    model_module.ProxmoxEndpoint.objects = SimpleNamespace(
        filter=lambda **kwargs: SimpleNamespace(first=lambda: None)
    )
    model_module.ProxboxPluginSettings = SimpleNamespace(
        get_solo=lambda: SimpleNamespace(console_url="")
    )

    root = _module("netbox_proxbox")
    root.__path__ = [str(MODULE_PATH.parent)]
    intent = _module("netbox_proxbox.intent")
    intent.__path__ = [str(MODULE_PATH.parent / "intent")]
    views = _module("netbox_proxbox.views")
    views.__path__ = [str(MODULE_PATH.parent / "views")]

    stub_modules = {
        "core": _module("core"),
        "core.choices": _module(
            "core.choices",
            JobStatusChoices=SimpleNamespace(
                ENQUEUED_STATE_CHOICES=(),
                TERMINAL_STATE_CHOICES=(),
                STATUS_SCHEDULED="scheduled",
            ),
        ),
        "core.models": _module("core.models", Job=job),
        "django": _module("django"),
        "django.urls": _module(
            "django.urls", NoReverseMatch=NoReverseMatch, reverse=reverse
        ),
        "django.utils": _module("django.utils"),
        "django.utils.safestring": _module(
            "django.utils.safestring", mark_safe=lambda value: value
        ),
        "netbox": _module("netbox"),
        "netbox.plugins": _module(
            "netbox.plugins", PluginTemplateExtension=PluginTemplateExtension
        ),
        "utilities": _module("utilities"),
        "utilities.permissions": _module(
            "utilities.permissions",
            get_permission_for_model=lambda model, action: (
                f"{model._meta.app_label}.{action}_{model._meta.model_name}"
            ),
        ),
        "utilities.views": _module("utilities.views", get_viewname=get_viewname),
        "virtualization": _module("virtualization"),
        "virtualization.models": _module(
            "virtualization.models", VirtualMachine=virtual_machine
        ),
        "netbox_proxbox": root,
        "netbox_proxbox.bug_report": _module(
            "netbox_proxbox.bug_report",
            build_bug_report_context=lambda job: {},
            is_reportable_status=lambda status: False,
        ),
        "netbox_proxbox.intent": intent,
        "netbox_proxbox.intent.firewall_common": _module(
            "netbox_proxbox.intent.firewall_common",
            resolve_firewall_endpoint=lambda obj: None,
        ),
        "netbox_proxbox.jobs": _module(
            "netbox_proxbox.jobs", is_proxbox_sync_job=lambda job: False
        ),
        "netbox_proxbox.models": model_module,
        "netbox_proxbox.utils": _module(
            "netbox_proxbox.utils", resolve_vm_type=lambda vm: "qemu"
        ),
        "netbox_proxbox.views": views,
        "netbox_proxbox.views.operational": _module(
            "netbox_proxbox.views.operational",
            resolve_vm_endpoint_context=lambda vm: None,
        ),
        "netbox_proxbox.views.proxbox_access": _module(
            "netbox_proxbox.views.proxbox_access",
            permission_enqueue_proxbox_sync=lambda: SYNC_PERMISSION,
            permission_run_proxmox_action=lambda: OPERATION_PERMISSION,
        ),
    }
    for name, module in stub_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "netbox_proxbox.template_content"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)

    return SimpleNamespace(
        calls=calls,
        classes=model_classes,
        module=module,
        virtual_machine=virtual_machine,
        vm_objects=virtual_machine.objects,
    )


def _context(obj, *permissions: str):
    return {
        "object": obj,
        "request": SimpleNamespace(user=_User(*permissions)),
    }


def _set_console_url(harness, value: str) -> None:
    harness.module.ProxboxPluginSettings.get_solo = lambda: SimpleNamespace(
        console_url=value
    )


@pytest.mark.parametrize(
    ("vm_type", "resource"),
    [("qemu", "virtual-machines"), ("lxc", "lxc-containers")],
)
def test_console_button_hands_off_to_management_console(
    template_content_module,
    vm_type,
    resource,
):
    """Console entry points never expose an endpoint URL to the browser."""
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 73
    host = ".".join(("console", "example", "invalid"))
    _set_console_url(harness, f"https://{host}")
    vm.proxbox_sync_state = SimpleNamespace(
        endpoint=SimpleNamespace(pk=1, enabled=True),
        proxmox_vm_id=100,
        proxmox_vm_type=vm_type,
    )

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    _template, context = extension.render_calls[-1]
    assert context["console_url"] == f"https://{host}/virtualization/{resource}/73"


def test_console_button_hides_when_management_console_url_is_unsafe(
    template_content_module,
):
    harness = template_content_module
    _set_console_url(harness, "http://console.example.invalid")
    vm = harness.virtual_machine()
    vm.pk = 74
    vm.proxbox_sync_state = SimpleNamespace(
        endpoint=SimpleNamespace(pk=1, enabled=True),
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
    )

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1",
        "https://console.example.invalid:bad",
        "https://console.example.invalid:65536",
    ],
)
def test_console_button_hides_when_management_console_url_is_malformed(
    template_content_module, url
):
    harness = template_content_module
    _set_console_url(harness, url)
    vm = harness.virtual_machine()
    vm.pk = 75
    vm.proxbox_sync_state = SimpleNamespace(
        endpoint=SimpleNamespace(pk=1, enabled=True),
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
    )

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


def test_console_button_hides_without_synchronized_guest(
    template_content_module,
):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 76

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


def test_console_button_hides_when_sidecar_endpoint_is_disabled(
    template_content_module,
):
    harness = template_content_module
    _set_console_url(harness, "https://console.example.invalid")
    vm = harness.virtual_machine()
    vm.pk = 76
    vm.proxbox_sync_state = SimpleNamespace(
        endpoint=SimpleNamespace(pk=1, enabled=False),
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
    )

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


@pytest.mark.parametrize(
    "sync_state",
    [
        SimpleNamespace(
            endpoint=SimpleNamespace(pk=1), proxmox_vm_id=None, proxmox_vm_type="qemu"
        ),
        SimpleNamespace(
            endpoint=SimpleNamespace(pk=1),
            proxmox_vm_id=100,
            proxmox_vm_type="template",
        ),
        SimpleNamespace(endpoint=None, proxmox_vm_id=100, proxmox_vm_type="lxc"),
    ],
)
def test_console_button_hides_when_authoritative_sync_state_is_ineligible(
    template_content_module, sync_state
):
    """Legacy or incomplete state cannot create a browser console handoff."""
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 77
    vm.proxbox_sync_state = sync_state

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


def test_console_button_hides_when_management_console_url_contains_whitespace(
    template_content_module,
):
    harness = template_content_module
    _set_console_url(harness, "https://console example")
    vm = harness.virtual_machine()
    vm.pk = 78
    vm.proxbox_sync_state = SimpleNamespace(
        endpoint=SimpleNamespace(pk=1, enabled=True),
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
    )

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    assert extension.console_button() == ""
    assert extension.render_calls == []


@pytest.mark.parametrize(
    ("extension_name", "tracking_model", "tracking_attr", "pk"),
    [
        (
            "ProxmoxClusterTemplateExtension",
            "ProxmoxCluster",
            "proxmox_cluster_tracking",
            41,
        ),
        (
            "ProxmoxNodeTemplateExtension",
            "ProxmoxNode",
            "proxmox_node_tracking",
            42,
        ),
    ],
)
def test_tracking_pages_reverse_the_linked_plugin_action(
    template_content_module,
    extension_name,
    tracking_model,
    tracking_attr,
    pk,
):
    harness = template_content_module
    tracking = harness.classes[tracking_model]()
    tracking.pk = pk
    page_object = SimpleNamespace(**{tracking_attr: _Relation(tracking)})

    extension = getattr(harness.module, extension_name)(
        _context(page_object, SYNC_PERMISSION)
    )

    model_name = tracking_model.lower()
    viewname = f"plugins:netbox_proxbox:{model_name}_proxbox_sync_now"
    assert extension.buttons() == f"/route/{viewname}/{pk}/"
    assert harness.calls["get_viewname"] == [(tracking, "proxbox_sync_now", False)]
    assert harness.calls["reverse"] == [(viewname, {"pk": pk})]


@pytest.mark.parametrize(
    ("extension_name", "model_name", "pk"),
    [
        ("ProxmoxStorageTemplateExtension", "ProxmoxStorage", 51),
        ("VMBackupTemplateExtension", "VMBackup", 52),
        ("VMSnapshotTemplateExtension", "VMSnapshot", 53),
        ("VMTaskHistoryTemplateExtension", "VMTaskHistory", 54),
    ],
)
def test_plugin_pages_reverse_their_own_registered_action(
    template_content_module,
    extension_name,
    model_name,
    pk,
):
    harness = template_content_module
    target = harness.classes[model_name]()
    target.pk = pk

    extension = getattr(harness.module, extension_name)(
        _context(target, SYNC_PERMISSION)
    )

    viewname = f"plugins:netbox_proxbox:{model_name.lower()}_proxbox_sync_now"
    assert extension.buttons() == f"/route/{viewname}/{pk}/"
    assert harness.calls["get_viewname"] == [(target, "proxbox_sync_now", False)]
    assert harness.calls["reverse"] == [(viewname, {"pk": pk})]


def test_virtual_machine_reverses_its_core_registered_action(template_content_module):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 61

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, SYNC_PERMISSION)
    )

    viewname = "virtualization:virtualmachine_proxbox_sync_now"
    assert extension.buttons() == f"/route/{viewname}/61/"
    assert harness.calls["get_viewname"] == [(vm, "proxbox_sync_now", False)]
    assert harness.calls["reverse"] == [(viewname, {"pk": 61})]


def test_virtual_machine_card_renders_typed_state_and_cloud_init(
    template_content_module,
):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 62
    sync_state = SimpleNamespace(
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
        proxmox_node=SimpleNamespace(name="pve-a"),
        proxmox_cluster=SimpleNamespace(name="cluster-a"),
    )
    cloud_init = SimpleNamespace(
        ciuser="ubuntu",
        ipconfig0="ip=dhcp",
        sshkeys="ssh-ed25519 AAAA first\n\nssh-rsa BBBB second\n",
    )
    vm.proxbox_sync_state = sync_state
    vm.proxmox_cloudinit = cloud_init
    harness.vm_objects.value = vm

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))

    assert extension.left_page() == "rendered-proxmox-card"
    assert harness.vm_objects.select_related_fields == (
        "proxbox_sync_state__proxmox_node",
        "proxbox_sync_state__proxmox_cluster",
        "proxmox_cloudinit",
    )
    template_name, context = extension.render_calls[-1]
    assert template_name == "netbox_proxbox/inc/vm_proxmox_card.html"
    assert context == {
        "sync_state": sync_state,
        "cloud_init": cloud_init,
        "ssh_key_count": 2,
    }


def test_virtual_machine_card_renders_sidecar_without_cloud_init(
    template_content_module,
):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 63
    vm.proxbox_sync_state = SimpleNamespace(proxmox_vm_id=101)
    harness.vm_objects.value = vm

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))

    assert extension.left_page() == "rendered-proxmox-card"
    assert extension.render_calls[-1][1]["cloud_init"] is None
    assert extension.render_calls[-1][1]["ssh_key_count"] == 0


def test_virtual_machine_card_is_hidden_when_neither_related_row_exists(
    template_content_module,
):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 64
    harness.vm_objects.value = vm

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))

    assert extension.left_page() == ""
    assert extension.render_calls == []


def test_virtual_machine_card_never_renders_ssh_key_material_as_template_data():
    template = CARD_TEMPLATE_PATH.read_text()

    assert 'target="_blank" rel="noopener"' in template
    assert "{{ ssh_key_count }}" in template
    assert "cloud_init.sshkeys" not in template
    assert "|safe" not in template


def test_tracking_page_without_a_tracking_row_stays_hidden(template_content_module):
    harness = template_content_module
    page_object = SimpleNamespace(proxmox_cluster_tracking=_Relation(None))
    extension = harness.module.ProxmoxClusterTemplateExtension(
        _context(page_object, SYNC_PERMISSION)
    )

    assert extension.buttons() == ""
    assert harness.calls == {"get_viewname": [], "reverse": []}


@pytest.mark.parametrize("extension_kind", ["plugin", "virtual_machine"])
def test_permission_denied_never_resolves_or_renders_a_sync_action(
    template_content_module,
    extension_kind,
):
    harness = template_content_module
    if extension_kind == "plugin":
        target = harness.classes["ProxmoxStorage"]()
        extension_class = harness.module.ProxmoxStorageTemplateExtension
    else:
        target = harness.virtual_machine()
        extension_class = harness.module.ProxboxVirtualMachineTemplateExtension
    target.pk = 71

    assert extension_class(_context(target)).buttons() == ""
    assert harness.calls == {"get_viewname": [], "reverse": []}


def test_unregistered_action_stays_hidden(template_content_module, monkeypatch):
    harness = template_content_module
    target = harness.classes["ProxmoxStorage"]()
    target.pk = 81

    def missing_route(*args, **kwargs):
        raise harness.module.NoReverseMatch

    monkeypatch.setattr(harness.module, "reverse", missing_route)

    extension = harness.module.ProxmoxStorageTemplateExtension(
        _context(target, SYNC_PERMISSION)
    )
    assert extension.buttons() == ""
