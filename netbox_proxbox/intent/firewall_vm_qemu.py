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
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
)
from netbox_proxbox.services.http_client import HttpClient


def push_vm_rules(
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM firewall rules."""
    return [push_rule(rule, actor=actor, client=client) for rule in rules]


def push_vm_ipsets(
    ipsets: list[ProxmoxFirewallIPSet],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM IP sets."""
    return [push_ipset(ipset, actor=actor, client=client) for ipset in ipsets]


def push_vm_ipset_entries(
    entries: list[ProxmoxFirewallIPSetEntry],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM IP set entries."""
    return [push_ipset_entry(entry, actor=actor, client=client) for entry in entries]


def push_vm_aliases(
    aliases: list[ProxmoxFirewallAlias],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push QEMU VM aliases."""
    return [push_alias(alias, actor=actor, client=client) for alias in aliases]


def push_vm_options(
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push QEMU VM firewall options."""
    return push_options(options, actor=actor, client=client)
