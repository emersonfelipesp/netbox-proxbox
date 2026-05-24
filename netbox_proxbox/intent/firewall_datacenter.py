"""Datacenter firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import (
    FirewallPushResult,
    push_alias,
    push_ipset,
    push_ipset_entry,
    push_options,
    push_rule,
    push_security_group,
)
from netbox_proxbox.models import (
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
)
from netbox_proxbox.services.http_client import HttpClient


def push_datacenter_rules(
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push datacenter firewall rules."""
    return [push_rule(rule, actor=actor, client=client) for rule in rules]


def push_security_groups(
    groups: list[ProxmoxFirewallSecurityGroup],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push datacenter security groups."""
    return [push_security_group(group, actor=actor, client=client) for group in groups]


def push_datacenter_ipsets(
    ipsets: list[ProxmoxFirewallIPSet],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push datacenter IP sets."""
    return [push_ipset(ipset, actor=actor, client=client) for ipset in ipsets]


def push_datacenter_ipset_entries(
    entries: list[ProxmoxFirewallIPSetEntry],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push datacenter IP set entries."""
    return [push_ipset_entry(entry, actor=actor, client=client) for entry in entries]


def push_datacenter_aliases(
    aliases: list[ProxmoxFirewallAlias],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push datacenter aliases."""
    return [push_alias(alias, actor=actor, client=client) for alias in aliases]


def push_datacenter_options(
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push datacenter options."""
    return push_options(options, actor=actor, client=client)
