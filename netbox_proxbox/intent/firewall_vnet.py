"""VNet/SDN firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import FirewallPushResult, push_rule
from netbox_proxbox.models import ProxmoxFirewallRule
from netbox_proxbox.services.http_client import HttpClient


def push_vnet_rules(
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push VNet firewall rules."""
    return [push_rule(rule, actor=actor, client=client) for rule in rules]
