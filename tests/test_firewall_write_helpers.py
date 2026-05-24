"""Focused tests for plugin-side firewall push helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Saved:
    def __init__(self) -> None:
        self.save_calls: list[dict] = []

    def save(self, **kwargs):
        self.save_calls.append(kwargs)


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self, response: _Response | None = None) -> None:
        self.response = response or _Response({"status": "pushed"})
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.response

    def put(self, url: str, **kwargs):
        self.calls.append(("put", url, kwargs))
        return self.response


@pytest.fixture
def fw_common(monkeypatch):
    """Load firewall_common with small in-memory stubs."""
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.FirewallSyncStatusChoices = SimpleNamespace(
        ACTIVE="active",
        STALE="stale",
        ERROR="error",
    )
    choices.FirewallZoneChoices = SimpleNamespace(
        DATACENTER="datacenter",
        NODE="node",
        VM_QEMU="vm_qemu",
        VM_LXC="vm_lxc",
        SECURITY_GROUP="security_group",
        VNET="vnet",
    )
    choices.FirewallScopeChoices = SimpleNamespace(
        DATACENTER="datacenter",
        VM_QEMU="vm_qemu",
        VM_LXC="vm_lxc",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    class Endpoint(_Saved):
        pass

    class Rule(_Saved):
        pass

    class SecurityGroup(_Saved):
        pass

    class IPSet(_Saved):
        pass

    class IPSetEntry(_Saved):
        pass

    class Alias(_Saved):
        pass

    class Options(_Saved):
        pass

    class Node(_Saved):
        pass

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxEndpoint = Endpoint
    models.ProxmoxFirewallRule = Rule
    models.ProxmoxFirewallSecurityGroup = SecurityGroup
    models.ProxmoxFirewallIPSet = IPSet
    models.ProxmoxFirewallIPSetEntry = IPSetEntry
    models.ProxmoxFirewallAlias = Alias
    models.ProxmoxFirewallOptions = Options
    models.ProxmoxNode = Node
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    services = types.ModuleType("netbox_proxbox.services")
    services.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services)

    endpoint_errors = types.ModuleType("netbox_proxbox.services._endpoint_errors")
    endpoint_errors.translate_request_exception = str
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services._endpoint_errors", endpoint_errors
    )

    backend_context = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context.get_fastapi_request_context = lambda: SimpleNamespace(
        http_url="https://proxbox-api.local",
        headers={"Authorization": "Bearer token"},
        verify_ssl=False,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )

    http_client = types.ModuleType("netbox_proxbox.services.http_client")

    class HttpError(Exception):
        pass

    http_client.HttpClient = object
    http_client.HttpError = HttpError
    http_client.get_default_http_client = lambda: _Client()
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services.http_client", http_client)

    module_name = "netbox_proxbox.intent.firewall_common"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        REPO_ROOT / "netbox_proxbox" / "intent" / "firewall_common.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _endpoint(fw_common, *, allow_writes=True):
    endpoint = fw_common.ProxmoxEndpoint()
    endpoint.pk = 1
    endpoint.id = 1
    endpoint.name = "pve01"
    endpoint.allow_writes = allow_writes
    return endpoint


def _rule(fw_common, endpoint):
    rule = fw_common.ProxmoxFirewallRule()
    rule.endpoint = endpoint
    rule.zone = fw_common.FirewallZoneChoices.DATACENTER
    rule.proxmox_node = None
    rule.virtual_machine = None
    rule.security_group = None
    rule.pos = 7
    rule.rule_type = "in"
    rule.action = "ACCEPT"
    rule.enable = True
    rule.macro = ""
    rule.iface = ""
    rule.source = "10.0.0.0/8"
    rule.dest = ""
    rule.proto = "tcp"
    rule.dport = "22"
    rule.sport = ""
    rule.log = ""
    rule.icmp_type = ""
    rule.comment = "Allow SSH"
    rule.digest = "abc123"
    rule.raw_config = {}
    rule.status = "stale"
    return rule


def test_datacenter_rule_push_uses_backend_put_and_actor_header(fw_common):
    endpoint = _endpoint(fw_common)
    rule = _rule(fw_common, endpoint)
    client = _Client(_Response({"status": "pushed", "path": "cluster/firewall/rules/7"}))

    result = fw_common.push_firewall_object(rule, actor="alice", client=client)

    method, url, kwargs = client.calls[0]
    assert method == "put"
    assert url == "https://proxbox-api.local/proxmox/firewall/datacenter/rules/7?endpoint_id=1"
    assert kwargs["headers"]["X-Proxbox-Actor"] == "alice"
    assert kwargs["headers"]["Authorization"] == "Bearer token"
    assert kwargs["json"]["type"] == "in"
    assert kwargs["json"]["dport"] == "22"
    assert result.status == "pushed"
    assert rule.status == "active"
    assert rule.save_calls == [{"update_fields": ["status"]}]


def test_disabled_endpoint_sets_error_status_and_raises(fw_common):
    rule = _rule(fw_common, _endpoint(fw_common, allow_writes=False))

    with pytest.raises(fw_common.FirewallPushError) as exc:
        fw_common.push_firewall_object(rule, actor="alice", client=_Client())

    assert exc.value.reason == "writes_disabled_for_endpoint"
    assert exc.value.status_code == 403
    assert rule.status == "error"


def test_vm_rule_path_keeps_vm_query_params_before_endpoint_id(fw_common):
    endpoint = _endpoint(fw_common)
    vm = SimpleNamespace(
        custom_field_data={"proxmox_vm_id": "101", "proxmox_node": "pve-a"},
    )
    rule = _rule(fw_common, endpoint)
    rule.zone = fw_common.FirewallZoneChoices.VM_QEMU
    rule.virtual_machine = vm
    client = _Client()

    fw_common.push_firewall_object(rule, actor="alice", client=client)

    _method, url, _kwargs = client.calls[0]
    assert url == (
        "https://proxbox-api.local/proxmox/firewall/vms/101/rules/7"
        "?node=pve-a&vm_type=qemu&endpoint_id=1"
    )


def test_vnet_skipped_response_leaves_rule_stale(fw_common):
    endpoint = _endpoint(fw_common)
    rule = _rule(fw_common, endpoint)
    rule.zone = fw_common.FirewallZoneChoices.VNET
    rule.iface = "tenant-vnet"
    client = _Client(
        _Response(
            {"status": "skipped", "reason": "vnet_firewall_not_supported"},
            status_code=200,
        )
    )

    result = fw_common.push_firewall_object(rule, actor="alice", client=client)

    assert result.status == "skipped"
    assert result.reason == "vnet_firewall_not_supported"
    assert rule.status == "stale"


def test_rule_validation_requires_vm_id_and_vnet_name(fw_common):
    vm_errors = fw_common.validation_errors_for_rule(
        {"zone": fw_common.FirewallZoneChoices.VM_LXC, "virtual_machine": object()}
    )
    vnet_errors = fw_common.validation_errors_for_rule(
        {"zone": fw_common.FirewallZoneChoices.VNET, "iface": ""}
    )

    assert "virtual_machine" in vm_errors
    assert "iface" in vnet_errors
