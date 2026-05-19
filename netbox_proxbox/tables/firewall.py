"""Tables for Proxmox firewall models."""
from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from netbox_proxbox import models


class ProxmoxFirewallSecurityGroupTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallSecurityGroup
        fields = ("pk", "id", "name", "endpoint", "status", "comment", "tags", "created", "last_updated")
        default_columns = ("name", "endpoint", "status", "comment")


class ProxmoxFirewallRuleTable(NetBoxTable):
    zone = columns.ChoiceFieldColumn()
    rule_type = columns.ChoiceFieldColumn()
    action = tables.Column()
    enable = columns.BooleanColumn()
    endpoint = tables.Column(linkify=True)
    security_group = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()
    log = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallRule
        fields = (
            "pk", "id", "endpoint", "zone", "pos", "rule_type", "action",
            "enable", "macro", "iface", "source", "dest", "proto", "dport",
            "sport", "log", "status", "security_group", "proxmox_node",
            "virtual_machine", "comment", "tags", "created", "last_updated",
        )
        default_columns = ("zone", "pos", "rule_type", "action", "enable", "source", "dest", "status")


class ProxmoxFirewallIPSetTable(NetBoxTable):
    name = tables.Column(linkify=True)
    scope = columns.ChoiceFieldColumn()
    endpoint = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallIPSet
        fields = ("pk", "id", "name", "scope", "endpoint", "virtual_machine", "status", "comment", "tags", "created", "last_updated")
        default_columns = ("name", "scope", "endpoint", "virtual_machine", "status")


class ProxmoxFirewallIPSetEntryTable(NetBoxTable):
    ipset = tables.Column(linkify=True)
    cidr = tables.Column(linkify=True)
    nomatch = columns.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallIPSetEntry
        fields = ("pk", "id", "ipset", "cidr", "nomatch", "comment", "tags", "created", "last_updated")
        default_columns = ("ipset", "cidr", "nomatch", "comment")


class ProxmoxFirewallAliasTable(NetBoxTable):
    name = tables.Column(linkify=True)
    scope = columns.ChoiceFieldColumn()
    endpoint = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallAlias
        fields = ("pk", "id", "name", "scope", "cidr", "endpoint", "virtual_machine", "status", "comment", "tags", "created", "last_updated")
        default_columns = ("name", "scope", "cidr", "endpoint", "status")


class ProxmoxFirewallOptionsTable(NetBoxTable):
    zone = columns.ChoiceFieldColumn()
    endpoint = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    enable = columns.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxFirewallOptions
        fields = ("pk", "id", "endpoint", "zone", "proxmox_node", "virtual_machine", "enable", "policy_in", "policy_out", "tags", "created", "last_updated")
        default_columns = ("endpoint", "zone", "proxmox_node", "virtual_machine", "enable", "policy_in", "policy_out")
