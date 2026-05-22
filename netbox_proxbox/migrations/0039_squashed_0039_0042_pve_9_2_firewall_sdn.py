"""Consolidated squash of migrations 0039–0042.

Folds all schema changes introduced between ``0038_v0_0_16_release`` and the
v0.0.18 tip into a single forward-only delta:

  * 0039_pve_firewall       — 6 PVE Firewall reflection models
  * 0040_endpoint_enabled   — ``enabled`` field on all 3 endpoint models
  * 0041_pve_9_2            — 4 SDN / datacenter models + ``ProxmoxNode.location``
  * 0042_fix_sdn_prefix_list_unique_cidr — ``cidr`` added to the
      ProxmoxSdnPrefixList unique constraint

There is intentionally no ``replaces = [...]`` attribute: Django's squash
auto-apply path requires *every* replaced migration to be present in
``django_migrations``, which fails for the realistic v0.0.17 → v0.0.18
upgrade where the DB may have applied only 0039–0041 (not 0042). Treating
this as a plain forward migration sidesteps both that problem and the
graph-rewrite errors seen after the v0.0.16.post4 squash (resolved via
v0.0.16.post5 by dropping ``replaces``). Safety comes from idempotent
schema ops (every AddField and CreateModel is wrapped via
``_idempotent_ops``) and from the ``_fix_sdn_prefix_list_constraint``
RunPython that handles the constraint rename idempotently across all three
possible DB states:

  * Clean install: table created by ``_create_model_if_missing`` using the
    live model, which already carries the new constraint → fixer is a no-op.
  * Partial upgrade (0039–0041 applied, not 0042): table exists with the
    *old* constraint → fixer drops old, adds new.
  * Full upgrade (0039–0042 already applied): table exists with the *new*
    constraint → fixer is a no-op.
"""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)

_SDN_PREFIX_LIST_TABLE = "netbox_proxbox_proxmoxsdnprefixlist"
_OLD_CONSTRAINT = "netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name"
_NEW_CONSTRAINT = "netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name_cidr"


def _fix_sdn_prefix_list_constraint(apps, schema_editor):
    """Idempotent: ensure only the CIDR-inclusive unique constraint exists.

    Handles three DB states:
    - Fresh install via squash: live model created the table with the new
      constraint already → no-op.
    - Partial upgrade (0041 applied, 0042 not): old constraint present, new
      missing → swap them.
    - Full upgrade (0042 already applied): new constraint present → no-op.
    """
    db = schema_editor.connection
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = %s
              AND constraint_type = 'UNIQUE'
              AND constraint_name IN (%s, %s)
            """,
            [_SDN_PREFIX_LIST_TABLE, _OLD_CONSTRAINT, _NEW_CONSTRAINT],
        )
        found = {row[0] for row in cur.fetchall()}

    has_old = _OLD_CONSTRAINT in found
    has_new = _NEW_CONSTRAINT in found

    if not has_old and has_new:
        return  # already correct

    if has_old:
        schema_editor.execute(
            f'ALTER TABLE "{_SDN_PREFIX_LIST_TABLE}" '
            f'DROP CONSTRAINT "{_OLD_CONSTRAINT}"'
        )
    if not has_new:
        schema_editor.execute(
            f'ALTER TABLE "{_SDN_PREFIX_LIST_TABLE}" '
            f'ADD CONSTRAINT "{_NEW_CONSTRAINT}" '
            f"UNIQUE (endpoint_id, cluster_name, name, cidr)"
        )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0038_v0_0_16_release"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        # ── 0039: PVE Firewall reflection models ─────────────────────────────
        create_model_idempotent(
            name="ProxmoxFirewallSecurityGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
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
                (
                    "name",
                    models.CharField(help_text="Security group name.", max_length=255),
                ),
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
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
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
        create_model_idempotent(
            name="ProxmoxFirewallRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
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
                (
                    "pos",
                    models.PositiveIntegerField(
                        help_text="Rule position in the ruleset."
                    ),
                ),
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
                (
                    "action",
                    models.CharField(
                        help_text="ACCEPT, DROP, REJECT, or security group name.",
                        max_length=128,
                    ),
                ),
                (
                    "enable",
                    models.BooleanField(default=True, help_text="Rule enabled flag."),
                ),
                (
                    "macro",
                    models.CharField(
                        blank=True, help_text="Predefined macro name.", max_length=128
                    ),
                ),
                (
                    "iface",
                    models.CharField(
                        blank=True, help_text="Network interface.", max_length=64
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        blank=True,
                        help_text="Source address/IP set/alias.",
                        max_length=512,
                    ),
                ),
                (
                    "dest",
                    models.CharField(
                        blank=True,
                        help_text="Destination address/IP set/alias.",
                        max_length=512,
                    ),
                ),
                (
                    "proto",
                    models.CharField(
                        blank=True, help_text="IP protocol.", max_length=32
                    ),
                ),
                (
                    "dport",
                    models.CharField(
                        blank=True, help_text="Destination port(s).", max_length=128
                    ),
                ),
                (
                    "sport",
                    models.CharField(
                        blank=True, help_text="Source port(s).", max_length=128
                    ),
                ),
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
                (
                    "icmp_type",
                    models.CharField(
                        blank=True,
                        help_text="ICMP type (when proto is icmp).",
                        max_length=64,
                    ),
                ),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "digest",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox concurrency token.",
                        max_length=64,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "Firewall Rule",
                "verbose_name_plural": "Firewall Rules",
                "ordering": ("endpoint", "zone", "pos"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=[
                            "endpoint",
                            "zone",
                            "pos",
                            "proxmox_node",
                            "virtual_machine",
                            "security_group",
                        ],
                        name="netbox_proxbox_firewallrule_unique_endpoint_zone_pos",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxFirewallIPSet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
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
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
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
        create_model_idempotent(
            name="ProxmoxFirewallIPSetEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "ipset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="netbox_proxbox.proxmoxfirewallipset",
                    ),
                ),
                (
                    "cidr",
                    models.CharField(
                        help_text="Network/IP in CIDR format.", max_length=256
                    ),
                ),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "nomatch",
                    models.BooleanField(
                        default=False,
                        help_text="Negate/exclude this CIDR from the set.",
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
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
        create_model_idempotent(
            name="ProxmoxFirewallAlias",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
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
                (
                    "cidr",
                    models.CharField(
                        help_text="Network/IP in CIDR format.", max_length=256
                    ),
                ),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
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
        create_model_idempotent(
            name="ProxmoxFirewallOptions",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
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
                (
                    "enable",
                    models.BooleanField(
                        blank=True,
                        help_text="Firewall enable flag for this zone.",
                        null=True,
                    ),
                ),
                (
                    "policy_in",
                    models.CharField(
                        blank=True,
                        help_text="Input policy: ACCEPT/DROP/REJECT.",
                        max_length=16,
                    ),
                ),
                (
                    "policy_out",
                    models.CharField(
                        blank=True,
                        help_text="Output policy: ACCEPT/DROP/REJECT.",
                        max_length=16,
                    ),
                ),
                (
                    "options",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Zone-specific options (nosmurfs, tcpflags, conntrack, dhcp, ipfilter, etc.).",
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
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
        # ── 0040: enabled field on all endpoint models ────────────────────────
        # Covers ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint (original 0040)
        # plus PBSEndpoint and PDMEndpoint (omitted from 0040; gap closed here).
        add_field_idempotent(
            "proxmoxendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "netboxendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "fastapiendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "pbsendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "pdmendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        # ── 0041: PVE 9.2 SDN and datacenter models ───────────────────────────
        create_model_idempotent(
            name="ProxmoxSdnFabric",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_fabrics",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "cluster_name",
                    models.CharField(help_text="Proxmox cluster name.", max_length=255),
                ),
                (
                    "fabric_name",
                    models.CharField(
                        help_text="SDN fabric identifier.", max_length=255
                    ),
                ),
                (
                    "fabric_type",
                    models.CharField(
                        choices=[
                            ("wireguard", "WireGuard"),
                            ("bgp", "BGP"),
                            ("vxlan", "VXLAN"),
                            ("ospf", "OSPF"),
                        ],
                        help_text="SDN fabric type.",
                        max_length=32,
                    ),
                ),
                (
                    "asn",
                    models.IntegerField(blank=True, help_text="BGP ASN.", null=True),
                ),
                ("advertise_subnets", models.BooleanField(default=False)),
                ("disable_arp_nd_suppression", models.BooleanField(default=False)),
                (
                    "vrf_vxlan",
                    models.IntegerField(
                        blank=True, help_text="VRF VXLAN ID.", null=True
                    ),
                ),
                ("peers", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "SDN Fabric",
                "verbose_name_plural": "SDN Fabrics",
                "ordering": ("endpoint", "cluster_name", "fabric_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "fabric_name"],
                        name="netbox_proxbox_sdnfabric_unique_endpoint_cluster_fabric",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxSdnRouteMap",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_route_maps",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "cluster_name",
                    models.CharField(help_text="Proxmox cluster name.", max_length=255),
                ),
                ("name", models.CharField(help_text="Route-map name.", max_length=255)),
                (
                    "action",
                    models.CharField(
                        blank=True, help_text="permit or deny.", max_length=16
                    ),
                ),
                ("match_peer", models.CharField(blank=True, max_length=255)),
                ("match_ip", models.CharField(blank=True, max_length=255)),
                ("set_community", models.CharField(blank=True, max_length=255)),
                ("order", models.IntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "SDN Route Map",
                "verbose_name_plural": "SDN Route Maps",
                "ordering": ("endpoint", "cluster_name", "name", "order"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "name", "order"],
                        name="netbox_proxbox_sdnroutemap_unique_endpoint_cluster_name_order",
                    )
                ],
            },
        ),
        # ProxmoxSdnPrefixList: state uses the FINAL constraint (with cidr).
        # The _fix_sdn_prefix_list_constraint RunPython below handles the DB
        # idempotently for installs where the old constraint is still present.
        create_model_idempotent(
            name="ProxmoxSdnPrefixList",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_prefix_lists",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "cluster_name",
                    models.CharField(help_text="Proxmox cluster name.", max_length=255),
                ),
                (
                    "name",
                    models.CharField(help_text="Prefix-list name.", max_length=255),
                ),
                (
                    "cidr",
                    models.CharField(
                        blank=True, help_text="CIDR prefix.", max_length=64
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        blank=True, help_text="permit or deny.", max_length=16
                    ),
                ),
                (
                    "le",
                    models.IntegerField(
                        blank=True, help_text="Less-or-equal prefix length.", null=True
                    ),
                ),
                (
                    "ge",
                    models.IntegerField(
                        blank=True,
                        help_text="Greater-or-equal prefix length.",
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "SDN Prefix List",
                "verbose_name_plural": "SDN Prefix Lists",
                "ordering": ("endpoint", "cluster_name", "name"),
                # Final constraint — includes cidr (added by original 0042).
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "name", "cidr"],
                        name="netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name_cidr",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxDatacenterCpuModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="datacenter_cpu_models",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "cluster_name",
                    models.CharField(help_text="Proxmox cluster name.", max_length=255),
                ),
                (
                    "cputype",
                    models.CharField(
                        help_text="Custom CPU type identifier.", max_length=255
                    ),
                ),
                (
                    "base_cputype",
                    models.CharField(
                        blank=True, help_text="Base CPU type.", max_length=255
                    ),
                ),
                (
                    "flags",
                    models.CharField(
                        blank=True, help_text="CPU feature flags.", max_length=512
                    ),
                ),
                (
                    "vendor_id",
                    models.CharField(
                        blank=True, help_text="CPUID vendor ID string.", max_length=255
                    ),
                ),
                (
                    "level",
                    models.IntegerField(
                        blank=True, help_text="CPUID level.", null=True
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "Datacenter CPU Model",
                "verbose_name_plural": "Datacenter CPU Models",
                "ordering": ("endpoint", "cluster_name", "cputype"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "cputype"],
                        name="netbox_proxbox_datacentercpumodel_unique_endpoint_cluster_cputype",
                    )
                ],
            },
        ),
        add_field_idempotent(
            "proxmoxnode",
            "location",
            models.CharField(
                blank=True,
                default="",
                help_text="Geographic or physical location of the node (PVE 9.2+).",
                max_length=255,
                verbose_name="Location",
            ),
            preserve_default=False,
        ),
        # ── 0042: idempotent constraint rename on ProxmoxSdnPrefixList ────────
        # state_operations is empty: the CreateModel above already carries the
        # final CIDR-inclusive constraint in Django's project state.
        # database_operations handles the three possible DB states idempotently.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    _fix_sdn_prefix_list_constraint,
                    reverse_code=_noop,
                ),
            ],
            state_operations=[],
        ),
    ]
