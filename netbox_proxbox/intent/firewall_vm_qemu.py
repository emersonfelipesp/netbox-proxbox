"""QEMU VM firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import (
    FirewallPushResult,
    push_alias,
    push_ipset,
    push_ipset_entry,
    push_options,
    push_rule,
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
    del endpoint, vmid, node
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
    del endpoint, vmid, node
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
    del endpoint, vmid, node
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
    del endpoint, vmid, node
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
    del endpoint, vmid, node
    return push_options(options, actor=actor, client=client)
