"""QEMU VM firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import (
    FirewallPushResult,
    push_alias,
    push_ipset,
    push_ipset_entry,
    push_options,
    push_rule,
    validate_vm_firewall_scope,
)
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
)
from netbox_proxbox.services.http_client import HttpClient


def push_vm_rules(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    node: str,
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM firewall rules."""
    for rule in rules:
        validate_vm_firewall_scope(
            rule, endpoint=endpoint, vmid=vmid, node=node, vm_type="qemu"
        )
    return [push_rule(rule, actor=actor, client=client) for rule in rules]


def push_vm_ipsets(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    node: str,
    ipsets: list[ProxmoxFirewallIPSet],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM IP sets."""
    for ipset in ipsets:
        validate_vm_firewall_scope(
            ipset, endpoint=endpoint, vmid=vmid, node=node, vm_type="qemu"
        )
    return [push_ipset(ipset, actor=actor, client=client) for ipset in ipsets]


def push_vm_ipset_entries(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    node: str,
    entries: list[ProxmoxFirewallIPSetEntry],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM IP set entries."""
    for entry in entries:
        validate_vm_firewall_scope(
            entry, endpoint=endpoint, vmid=vmid, node=node, vm_type="qemu"
        )
    return [push_ipset_entry(entry, actor=actor, client=client) for entry in entries]


def push_vm_aliases(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    node: str,
    aliases: list[ProxmoxFirewallAlias],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM aliases."""
    for alias in aliases:
        validate_vm_firewall_scope(
            alias, endpoint=endpoint, vmid=vmid, node=node, vm_type="qemu"
        )
    return [push_alias(alias, actor=actor, client=client) for alias in aliases]


def push_vm_options(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    node: str,
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push QEMU VM firewall options."""
    validate_vm_firewall_scope(
        options, endpoint=endpoint, vmid=vmid, node=node, vm_type="qemu"
    )
    return push_options(options, actor=actor, client=client)
