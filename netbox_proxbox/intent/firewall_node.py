"""Node firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import (
    FirewallPushResult,
    push_options,
    push_rule,
)
from netbox_proxbox.models import ProxmoxFirewallOptions, ProxmoxFirewallRule
from netbox_proxbox.services.http_client import HttpClient


def push_node_rules(
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push node firewall rules."""
    return [push_rule(rule, actor=actor, client=client) for rule in rules]


def push_node_options(
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push node firewall options."""
    return push_options(options, actor=actor, client=client)
