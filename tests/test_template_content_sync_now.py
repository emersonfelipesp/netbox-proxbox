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
SYNC_STATE_CARD_TEMPLATE_PATH = (
    MODULE_PATH.parent / "templates" / "netbox_proxbox" / "inc" / "sync_state_card.html"
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


class _RestrictableObjectQuery(_ObjectQuery):
    def __init__(self):
        super().__init__()
        self.restrict_calls = []
        self.visible = True

    def restrict(self, user, action):
        self.restrict_calls.append((user, action))
        if self.visible:
            return self
        return _ObjectQuery()


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

    def reverse(viewname, kwargs=None, args=None):
        values = kwargs or ({"pk": args[0]} if args else {})
        calls["reverse"].append((viewname, values))
        suffix = f"{values['pk']}/" if "pk" in values else ""
        return f"/route/{viewname}/{suffix}"

    class PluginTemplateExtension:
        def __init__(self, context):
            self.context = context
            self.render_calls = []

        def render(self, template_name, context=None):
            context = context or {}
            self.render_calls.append((template_name, context))
            if template_name == "netbox_proxbox/inc/vm_proxmox_card.html":
                return "rendered-proxmox-card"
            if template_name == "netbox_proxbox/inc/sync_state_card.html":
                return "rendered-sync-state-card"
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
            "ProxmoxVMIntent",
            "VMBackup",
            "VMSnapshot",
            "VMTaskHistory",
        )
    }
    model_classes["ProxmoxEndpoint"] = _model_class(
        "ProxmoxEndpoint", app_label="netbox_proxbox"
    )
    model_classes["ProxmoxVMIntent"].objects = _RestrictableObjectQuery()
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


def test_vm_intent_card_is_absent_without_an_intent_row(template_content_module):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 70
    extension = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))

    assert extension.right_page() == ""
    assert extension.render_calls == []


def test_vm_intent_card_has_a_permission_checked_edit_link(
    template_content_module,
):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 71
    intent = SimpleNamespace(pk=91, virtual_machine=vm)
    harness.classes["ProxmoxVMIntent"].objects.value = intent
    view_permission = "netbox_proxbox.view_proxmoxvmintent"
    change_permission = "netbox_proxbox.change_proxmoxvmintent"
    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, view_permission, change_permission)
    )

    assert extension.right_page() == ""
    assert harness.classes["ProxmoxVMIntent"].objects.restrict_calls == [
        (extension.context["request"].user, "view")
    ]
    template, context = extension.render_calls[-1]
    assert template == "netbox_proxbox/inc/vm_proxmox_intent_card.html"
    assert context == {
        "intent": intent,
        "edit_url": "/route/plugins:netbox_proxbox:proxmoxvmintent_edit/91/",
    }


def test_vm_intent_card_is_hidden_without_view_permission(template_content_module):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 72
    harness.classes["ProxmoxVMIntent"].objects.value = SimpleNamespace(
        pk=92, virtual_machine=vm
    )
    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, "netbox_proxbox.change_proxmoxvmintent")
    )

    assert extension.right_page() == ""
    assert extension.render_calls == []
    assert harness.classes["ProxmoxVMIntent"].objects.restrict_calls == []


def test_vm_intent_card_honors_object_visibility(template_content_module):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 73
    manager = harness.classes["ProxmoxVMIntent"].objects
    manager.value = SimpleNamespace(pk=93, virtual_machine=vm)
    manager.visible = False
    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, "netbox_proxbox.view_proxmoxvmintent")
    )

    assert extension.right_page() == ""
    assert extension.render_calls == []


def test_vm_intent_card_fails_closed_without_restrict(template_content_module):
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 74
    unrestricted = _ObjectQuery()
    unrestricted.value = SimpleNamespace(pk=94, virtual_machine=vm)
    harness.classes["ProxmoxVMIntent"].objects = unrestricted
    extension = harness.module.ProxboxVirtualMachineTemplateExtension(
        _context(vm, "netbox_proxbox.view_proxmoxvmintent")
    )

    assert extension.right_page() == ""
    assert extension.render_calls == []


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
    node = _related("pve-a", "/plugins/proxbox/nodes/1/")
    cluster = _related("cluster-a", "/plugins/proxbox/clusters/1/")
    sync_state = SimpleNamespace(
        proxmox_vm_id=100,
        proxmox_vm_type="qemu",
        proxmox_node=node,
        proxmox_cluster=cluster,
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
        "proxbox_sync_state__endpoint",
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
        "proxmox_link_url": None,
        # Permission-checked before rendering: the sidecar links objects this
        # viewer may be denied, and the card must not disclose their name or
        # detail URL to anyone who can merely see the virtual machine. The
        # endpoint is included because the template used to dereference it
        # straight off the sidecar, bypassing the check entirely.
        "visible_endpoint": None,
        "endpoint_denied": False,
        "visible_node": node,
        "node_denied": False,
        "visible_cluster": cluster,
        "cluster_denied": False,
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
    assert extension.render_calls[-1][1]["proxmox_link_url"] is None


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
    for reflected_field in (
        "proxmox_tags",
        "proxmox_os",
        "proxmox_disk",
        "proxmox_interfaces",
        "proxmox_vmid",
        "proxmox_notes",
        "proxmox_tcp_states",
        "proxmox_cpu_type",
        "proxmox_storage_ids",
        "proxmox_storage_names",
        "proxmox_device_names",
    ):
        assert f"sync_state.{reflected_field}" in template


def test_other_sync_state_card_registers_every_sidecar_parent_type(
    template_content_module,
):
    extension = template_content_module.module.ProxboxSyncStateTemplateExtension
    assert set(extension.models) == {
        "dcim.device",
        "dcim.interface",
        "dcim.manufacturer",
        "dcim.site",
        "dcim.devicerole",
        "dcim.devicetype",
        "ipam.ipaddress",
        "ipam.vlan",
        "virtualization.cluster",
        "virtualization.clustergroup",
        "virtualization.clustertype",
        "virtualization.virtualdisk",
        "virtualization.vminterface",
    }


def _related(name, url, *, visible=True):
    """A related object double carrying the restrict() surface the card checks.

    The card asks the related object's own manager whether this viewer may see
    it, because the sidecar links objects a user with access to the *core*
    object may still be denied. A double without `restrict` is treated as not
    visible -- deliberately fail-closed -- so a test meaning "the viewer is
    allowed" has to say so, and `visible=False` models the denied case.
    """

    class _QS:
        @staticmethod
        def filter(**_kwargs):
            return SimpleNamespace(exists=lambda: visible)

    class _Related:
        objects = SimpleNamespace(restrict=lambda *a, **kw: _QS())

        def __init__(self):
            self.pk = 1
            self.name = name

        def get_absolute_url(self):
            return url

        def __str__(self):
            return name

    return _Related()


def test_other_sync_state_card_renders_populated_sidecar_without_custom_fields(
    template_content_module,
):
    harness = template_content_module
    device_class = _model_class("Device", app_label="dcim", model_name="device")
    device_class.objects = _ObjectQuery()

    def reject_custom_fields(_self):
        raise AssertionError("the detail card must not read custom_field_data")

    device_class.custom_field_data = property(reject_custom_fields)
    device = device_class()
    device.pk = 91
    endpoint = _related("endpoint-a", "/plugins/proxbox/endpoints/proxmox/1/")
    device.proxbox_sync_state = SimpleNamespace(
        endpoint=endpoint,
        proxmox_node=None,
        proxmox_node_name="pve-a",
        proxmox_cluster=None,
        proxmox_cluster_name="cluster-a",
        proxmox_link="https://pve.example.invalid/#v1:0:=node%2Fpve-a",
        hardware_chassis_serial="SERIAL-1",
        proxmox_last_updated="2026-09-02T10:00:00Z",
        last_run_id="run-91",
    )
    device_class.objects.value = device

    extension = harness.module.ProxboxSyncStateTemplateExtension(_context(device))

    assert extension.left_page() == "rendered-sync-state-card"
    assert device_class.objects.select_related_fields == (
        "proxbox_sync_state__endpoint",
        "proxbox_sync_state__proxmox_node",
        "proxbox_sync_state__proxmox_cluster",
    )
    template_name, context = extension.render_calls[-1]
    assert template_name == "netbox_proxbox/inc/sync_state_card.html"
    rows = {row["label"]: row for row in context["rows"]}
    assert rows["Endpoint"]["value"] is endpoint
    assert rows["Endpoint"]["url"] == "/plugins/proxbox/endpoints/proxmox/1/"
    assert rows["Node"]["value"] == "pve-a"
    assert rows["Cluster"]["value"] == "cluster-a"
    assert rows["Proxmox interface"]["url"].startswith("https://")
    assert rows["Chassis serial"]["value"] == "SERIAL-1"
    assert rows["Last run ID"]["value"] == "run-91"


def test_other_sync_state_card_is_hidden_without_a_sidecar(template_content_module):
    harness = template_content_module
    site_class = _model_class("Site", app_label="dcim", model_name="site")
    site_class.objects = _ObjectQuery()
    site = site_class()
    site.pk = 92
    site_class.objects.value = site

    extension = harness.module.ProxboxSyncStateTemplateExtension(_context(site))

    assert extension.left_page() == ""
    assert extension.render_calls == []


def test_shared_sync_state_card_keeps_autoescaping_and_safe_link_attributes():
    template = SYNC_STATE_CARD_TEMPLATE_PATH.read_text()

    assert 'target="_blank" rel="noopener"' in template
    assert "|safe" not in template
    assert "autoescape off" not in template


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


def test_sync_state_card_hides_a_related_object_the_viewer_cannot_see(
    template_content_module,
):
    """A card must not disclose a related object the caller is denied.

    The sidecar links a Proxmox endpoint, node, cluster, storage or bridge. Those
    are permission-controlled objects in their own right, so rendering their name
    and detail URL to anyone who can view the *core* object leaks both the
    existence and the identity of something they were refused. An object the
    viewer cannot see is treated exactly as an unresolved relation: the recorded
    name, and no link.
    """
    harness = template_content_module
    device_class = _model_class("Device", app_label="dcim", model_name="device")
    device_class.objects = _ObjectQuery()
    device = device_class()
    device.pk = 92
    device.proxbox_sync_state = SimpleNamespace(
        endpoint=_related(
            "secret-endpoint", "/plugins/proxbox/endpoints/proxmox/9/", visible=False
        ),
        proxmox_node=_related(
            "secret-node", "/plugins/proxbox/nodes/9/", visible=False
        ),
        proxmox_node_name="pve-a",
        proxmox_cluster=None,
        proxmox_cluster_name="cluster-a",
        proxmox_endpoint_raw_id=None,
        proxmox_last_updated=None,
        last_run_id=None,
    )
    device_class.objects.value = device

    extension = harness.module.ProxboxSyncStateTemplateExtension(_context(device))
    extension.left_page()
    rows = {row["label"]: row for row in extension.render_calls[-1][1]["rows"]}

    assert rows["Endpoint"]["url"] is None, "a denied object must not be linked"
    assert rows["Endpoint"]["value"] == harness.module.RESTRICTED_LABEL

    # A denied relation must NOT fall back to the recorded name: that string is
    # the object's identity, so showing it discloses precisely what the
    # permission check just refused. Falling back is correct only for a
    # genuinely unresolved relation, which is a different state.
    assert rows["Node"]["url"] is None
    assert rows["Node"]["value"] == harness.module.RESTRICTED_LABEL
    assert rows["Node"]["value"] != "pve-a"


def test_device_card_surfaces_an_unresolved_endpoint_id_rather_than_a_blank(
    template_content_module,
):
    """An unresolved endpoint keeps its recorded id, labelled as unresolved.

    The sidecar records `proxmox_endpoint_raw_id` precisely so an endpoint that
    did not resolve can still be identified. Dropping it leaves an em dash and
    turns a recoverable state into an unexplained blank.
    """
    harness = template_content_module
    device_class = _model_class("Device", app_label="dcim", model_name="device")
    device_class.objects = _ObjectQuery()
    device = device_class()
    device.pk = 93
    device.proxbox_sync_state = SimpleNamespace(
        endpoint=None,
        proxmox_endpoint_raw_id=14,
        proxmox_node=None,
        proxmox_node_name="",
        proxmox_cluster=None,
        proxmox_cluster_name="",
        proxmox_last_updated=None,
        last_run_id=None,
    )
    device_class.objects.value = device

    extension = harness.module.ProxboxSyncStateTemplateExtension(_context(device))
    extension.left_page()
    rows = {row["label"]: row for row in extension.render_calls[-1][1]["rows"]}

    assert rows["Endpoint"]["value"] == "Unresolved ID 14"
    assert rows["Endpoint"]["url"] is None


def test_virtual_machine_card_hides_an_endpoint_the_viewer_cannot_see(
    template_content_module,
):
    """The VM card's endpoint went through no permission check at all.

    Node and cluster were resolved in Python, but the template dereferenced
    `sync_state.endpoint` directly, so a viewer allowed to see the virtual
    machine but denied its Proxmox endpoint still received the endpoint's name
    and detail URL. All three relations now go through the same check.
    """
    harness = template_content_module
    vm = harness.virtual_machine()
    vm.pk = 64
    vm.proxbox_sync_state = SimpleNamespace(
        proxmox_vm_id=104,
        endpoint=_related(
            "secret-endpoint", "/plugins/proxbox/endpoints/proxmox/9/", visible=False
        ),
        proxmox_node=None,
        proxmox_cluster=None,
    )
    vm.proxmox_cloudinit = None
    harness.vm_objects.value = vm

    extension = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))
    extension.left_page()
    _, context = extension.render_calls[-1]

    assert context["visible_endpoint"] is None
    assert context["endpoint_denied"] is True


def test_cards_suppress_the_proxmox_link_when_the_endpoint_is_denied(
    template_content_module,
):
    """The external link is endpoint information, not a neutral URL.

    Sanitising it is not enough: the href carries the Proxmox origin and the
    object's path there, so rendering it to a viewer denied the endpoint
    relation discloses exactly what that check withheld. Both cards suppress it
    on the same authorization.
    """
    harness = template_content_module

    device_class = _model_class("Device", app_label="dcim", model_name="device")
    device_class.objects = _ObjectQuery()
    device = device_class()
    device.pk = 94
    device.proxbox_sync_state = SimpleNamespace(
        endpoint=_related(
            "secret", "/plugins/proxbox/endpoints/proxmox/9/", visible=False
        ),
        proxmox_endpoint_raw_id=None,
        proxmox_node=None,
        proxmox_node_name="",
        proxmox_cluster=None,
        proxmox_cluster_name="",
        proxmox_link="https://pve.example.invalid/#v1:0:=node%2Fpve-a",
        proxmox_last_updated=None,
        last_run_id=None,
    )
    device_class.objects.value = device

    shared = harness.module.ProxboxSyncStateTemplateExtension(_context(device))
    shared.left_page()
    rows = {row["label"]: row for row in shared.render_calls[-1][1]["rows"]}
    assert rows["Proxmox interface"]["url"] is None
    assert rows["Proxmox interface"]["value"] is None

    vm = harness.virtual_machine()
    vm.pk = 65
    vm.proxbox_sync_state = SimpleNamespace(
        proxmox_vm_id=105,
        endpoint=_related(
            "secret", "/plugins/proxbox/endpoints/proxmox/9/", visible=False
        ),
        proxmox_node=None,
        proxmox_cluster=None,
        proxmox_link="https://pve.example.invalid/#v1:0:=lxc/105",
    )
    vm.proxmox_cloudinit = None
    harness.vm_objects.value = vm

    card = harness.module.ProxboxVirtualMachineTemplateExtension(_context(vm))
    card.left_page()
    assert card.render_calls[-1][1]["proxmox_link_url"] is None
