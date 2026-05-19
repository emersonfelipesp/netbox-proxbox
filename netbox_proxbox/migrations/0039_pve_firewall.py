"""Migration 0039: PVE Firewall sync models.

Adds 6 new read-only reflection models for Proxmox VE firewall objects:
  - ProxmoxFirewallSecurityGroup
  - ProxmoxFirewallRule
  - ProxmoxFirewallIPSet
  - ProxmoxFirewallIPSetEntry
  - ProxmoxFirewallAlias
  - ProxmoxFirewallOptions

Every CreateModel is wrapped with create_model_idempotent() so this
migration is safe to run against clean installs and any partial-legacy
environment.
"""
from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0038_v0_0_16_release"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        # ── ProxmoxFirewallSecurityGroup ─────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallSecurityGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firewall_security_groups",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("name", models.CharField(help_text="Security group name.", max_length=255)),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall Security Group",
                "verbose_name_plural": "Firewall Security Groups",
                "ordering": ("endpoint", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "name"],
                        name="netbox_proxbox_firewallsecuritygroup_unique_endpoint_name",
                    )
                ],
            },
        ),
        # ── ProxmoxFirewallRule ──────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firewall_rules",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "zone",
                    models.CharField(
                        choices=[
                            ("datacenter", "Datacenter"),
                            ("node", "Node"),
                            ("vm_qemu", "VM (QEMU)"),
                            ("vm_lxc", "CT (LXC)"),
                            ("security_group", "Security Group"),
                            ("vnet", "VNet (SDN)"),
                        ],
                        help_text="Firewall zone this rule belongs to.",
                        max_length=20,
                    ),
                ),
                (
                    "proxmox_node",
                    models.ForeignKey(
                        blank=True,
                        help_text="Node — set for node-level rules.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="firewall_rules",
                        to="netbox_proxbox.proxmoxnode",
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        blank=True,
                        help_text="VM/CT — set for VM-level rules.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_firewall_rules",
                        to="virtualization.virtualmachine",
                    ),
                ),
                (
                    "security_group",
                    models.ForeignKey(
                        blank=True,
                        help_text="Security group — set for security-group rules.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rules",
                        to="netbox_proxbox.proxmoxfirewallsecuritygroup",
                    ),
                ),
                ("pos", models.PositiveIntegerField(help_text="Rule position in the ruleset.")),
                (
                    "rule_type",
                    models.CharField(
                        choices=[
                            ("in", "In"),
                            ("out", "Out"),
                            ("forward", "Forward"),
                            ("group", "Group"),
                        ],
                        help_text="Rule direction/type.",
                        max_length=16,
                    ),
                ),
                ("action", models.CharField(help_text="ACCEPT, DROP, REJECT, or security group name.", max_length=128)),
                ("enable", models.BooleanField(default=True, help_text="Rule enabled flag.")),
                ("macro", models.CharField(blank=True, help_text="Predefined macro name.", max_length=128)),
                ("iface", models.CharField(blank=True, help_text="Network interface.", max_length=64)),
                ("source", models.CharField(blank=True, help_text="Source address/IP set/alias.", max_length=512)),
                ("dest", models.CharField(blank=True, help_text="Destination address/IP set/alias.", max_length=512)),
                ("proto", models.CharField(blank=True, help_text="IP protocol.", max_length=32)),
                ("dport", models.CharField(blank=True, help_text="Destination port(s).", max_length=128)),
                ("sport", models.CharField(blank=True, help_text="Source port(s).", max_length=128)),
                (
                    "log",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("nolog", "No Log"),
                            ("emerg", "Emergency"),
                            ("alert", "Alert"),
                            ("crit", "Critical"),
                            ("err", "Error"),
                            ("warning", "Warning"),
                            ("notice", "Notice"),
                            ("info", "Info"),
                            ("debug", "Debug"),
                        ],
                        help_text="Per-rule log level.",
                        max_length=16,
                    ),
                ),
                ("icmp_type", models.CharField(blank=True, help_text="ICMP type (when proto is icmp).", max_length=64)),
                ("comment", models.TextField(blank=True, null=True)),
                ("digest", models.CharField(blank=True, help_text="Proxmox concurrency token.", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall Rule",
                "verbose_name_plural": "Firewall Rules",
                "ordering": ("endpoint", "zone", "pos"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "zone", "pos", "proxmox_node", "virtual_machine", "security_group"],
                        name="netbox_proxbox_firewallrule_unique_endpoint_zone_pos",
                    )
                ],
            },
        ),
        # ── ProxmoxFirewallIPSet ─────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallIPSet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firewall_ipsets",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("datacenter", "Datacenter"),
                            ("vm_qemu", "VM (QEMU)"),
                            ("vm_lxc", "CT (LXC)"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_firewall_ipsets",
                        to="virtualization.virtualmachine",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall IP Set",
                "verbose_name_plural": "Firewall IP Sets",
                "ordering": ("endpoint", "scope", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "scope", "name", "virtual_machine"],
                        name="netbox_proxbox_firewallipset_unique_endpoint_scope_name_vm",
                    )
                ],
            },
        ),
        # ── ProxmoxFirewallIPSetEntry ────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallIPSetEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "ipset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="netbox_proxbox.proxmoxfirewallipset",
                    ),
                ),
                ("cidr", models.CharField(help_text="Network/IP in CIDR format.", max_length=256)),
                ("comment", models.TextField(blank=True, null=True)),
                ("nomatch", models.BooleanField(default=False, help_text="Negate/exclude this CIDR from the set.")),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall IP Set Entry",
                "verbose_name_plural": "Firewall IP Set Entries",
                "ordering": ("ipset", "cidr"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["ipset", "cidr"],
                        name="netbox_proxbox_firewallipsetentry_unique_ipset_cidr",
                    )
                ],
            },
        ),
        # ── ProxmoxFirewallAlias ─────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firewall_aliases",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("datacenter", "Datacenter"),
                            ("vm_qemu", "VM (QEMU)"),
                            ("vm_lxc", "CT (LXC)"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_firewall_aliases",
                        to="virtualization.virtualmachine",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("cidr", models.CharField(help_text="Network/IP in CIDR format.", max_length=256)),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall Alias",
                "verbose_name_plural": "Firewall Aliases",
                "ordering": ("endpoint", "scope", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "scope", "name", "virtual_machine"],
                        name="netbox_proxbox_firewallalias_unique_endpoint_scope_name_vm",
                    )
                ],
            },
        ),
        # ── ProxmoxFirewallOptions ───────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallOptions",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firewall_options",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "zone",
                    models.CharField(
                        choices=[
                            ("datacenter", "Datacenter"),
                            ("node", "Node"),
                            ("vm_qemu", "VM (QEMU)"),
                            ("vm_lxc", "CT (LXC)"),
                            ("security_group", "Security Group"),
                            ("vnet", "VNet (SDN)"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "proxmox_node",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="firewall_options",
                        to="netbox_proxbox.proxmoxnode",
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_firewall_options",
                        to="virtualization.virtualmachine",
                    ),
                ),
                ("enable", models.BooleanField(blank=True, help_text="Firewall enable flag for this zone.", null=True)),
                ("policy_in", models.CharField(blank=True, help_text="Input policy: ACCEPT/DROP/REJECT.", max_length=16)),
                ("policy_out", models.CharField(blank=True, help_text="Output policy: ACCEPT/DROP/REJECT.", max_length=16)),
                (
                    "options",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Zone-specific options (nosmurfs, tcpflags, conntrack, dhcp, ipfilter, etc.).",
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Firewall Options",
                "verbose_name_plural": "Firewall Options",
                "ordering": ("endpoint", "zone"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "zone", "proxmox_node", "virtual_machine"],
                        name="netbox_proxbox_firewalloptions_unique_endpoint_zone_node_vm",
                    )
                ],
            },
        ),
    ]
