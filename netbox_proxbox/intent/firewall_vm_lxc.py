"""LXC container firewall push helpers."""

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


def push_ct_rules(
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push LXC firewall rules."""
    return [push_rule(rule, actor=actor, client=client) for rule in rules]


def push_ct_ipsets(
    ipsets: list[ProxmoxFirewallIPSet],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push LXC IP sets."""
    return [push_ipset(ipset, actor=actor, client=client) for ipset in ipsets]


def push_ct_ipset_entries(
    entries: list[ProxmoxFirewallIPSetEntry],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push LXC IP set entries."""
    return [push_ipset_entry(entry, actor=actor, client=client) for entry in entries]


def push_ct_aliases(
    aliases: list[ProxmoxFirewallAlias],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push LXC aliases."""
    return [push_alias(alias, actor=actor, client=client) for alias in aliases]


def push_ct_options(
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push LXC firewall options."""
    return push_options(options, actor=actor, client=client)
