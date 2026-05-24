"""VNet/SDN firewall push helpers."""

from __future__ import annotations

from netbox_proxbox.intent.firewall_common import (
    FirewallPushResult,
    push_rule,
    validate_vnet_firewall_scope,
)
from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxFirewallRule
from netbox_proxbox.services.http_client import HttpClient


def push_vnet_rules(
    endpoint: ProxmoxEndpoint,
    vnet: str,
    rules: list[ProxmoxFirewallRule],
    *,
    actor: str,
    client: HttpClient | None = None,
) -> list[FirewallPushResult]:
    """Push VNet firewall rules."""
    for rule in rules:
        validate_vnet_firewall_scope(rule, endpoint=endpoint, vnet=vnet)
    return [push_rule(rule, actor=actor, client=client) for rule in rules]
