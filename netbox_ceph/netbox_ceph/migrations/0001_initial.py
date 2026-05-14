"""Initial schema for netbox-ceph read-only inventory models."""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("extras", "0002_squashed_0059"),
        ("netbox_proxbox", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CephPluginSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("singleton_key", models.CharField(default="default", editable=False, max_length=32, unique=True)),
                ("branching_enabled", models.BooleanField(default=False)),
                ("branch_name_prefix", models.CharField(default="ceph-sync", max_length=64)),
                (
                    "branch_on_conflict",
                    models.CharField(
                        choices=[
                            ("fail", "Fail (leave branch open for review)"),
                            ("acknowledge", "Acknowledge and merge anyway"),
                        ],
                        default="fail",
                        max_length=16,
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph plugin settings",
                "verbose_name_plural": "Ceph plugin settings",
            },
        ),
        migrations.CreateModel(
            name="CephCluster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=255)),
                ("fsid", models.CharField(blank=True, max_length=64)),
                ("health", models.CharField(default="unknown", max_length=32)),
                (
                    "quorum_names",
                    models.JSONField(blank=True, default=list, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                (
                    "status",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_clusters",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "proxmox_cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ceph_clusters",
                        to="netbox_proxbox.proxmoxcluster",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph cluster",
                "verbose_name_plural": "Ceph clusters",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephcluster",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_cluster_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephDaemon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("daemon_type", models.CharField(default="unknown", max_length=16)),
                ("name", models.CharField(max_length=255)),
                ("daemon_id", models.CharField(blank=True, max_length=255)),
                ("host", models.CharField(blank=True, max_length=255)),
                ("state", models.CharField(default="unknown", max_length=32)),
                ("status", models.CharField(blank=True, max_length=255)),
                ("version", models.CharField(blank=True, max_length=128)),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_daemons",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daemons",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                (
                    "proxmox_node",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ceph_daemons",
                        to="netbox_proxbox.proxmoxnode",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph daemon",
                "verbose_name_plural": "Ceph daemons",
                "ordering": ("endpoint", "daemon_type", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephdaemon",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "daemon_type", "name"),
                name="netbox_ceph_daemon_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephOSD",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("osd_id", models.PositiveIntegerField()),
                ("name", models.CharField(blank=True, max_length=255)),
                ("host", models.CharField(blank=True, max_length=255)),
                ("up", models.BooleanField(default=False)),
                ("in_cluster", models.BooleanField(default=False)),
                ("status", models.CharField(blank=True, max_length=255)),
                ("device_class", models.CharField(blank=True, max_length=64)),
                ("weight", models.FloatField(blank=True, null=True)),
                ("reweight", models.FloatField(blank=True, null=True)),
                ("used_bytes", models.BigIntegerField(blank=True, null=True)),
                ("available_bytes", models.BigIntegerField(blank=True, null=True)),
                ("total_bytes", models.BigIntegerField(blank=True, null=True)),
                ("pgs", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_osds",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="osds",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                (
                    "proxmox_node",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ceph_osds",
                        to="netbox_proxbox.proxmoxnode",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph OSD",
                "verbose_name_plural": "Ceph OSDs",
                "ordering": ("endpoint", "osd_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephosd",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "osd_id"),
                name="netbox_ceph_osd_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephPool",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=255)),
                ("pool_id", models.PositiveIntegerField(blank=True, null=True)),
                ("size", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("min_size", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("pg_num", models.PositiveIntegerField(blank=True, null=True)),
                ("pg_autoscale_mode", models.CharField(blank=True, max_length=32)),
                ("crush_rule", models.CharField(blank=True, max_length=255)),
                ("application", models.CharField(blank=True, max_length=64)),
                ("used_bytes", models.BigIntegerField(blank=True, null=True)),
                ("max_available_bytes", models.BigIntegerField(blank=True, null=True)),
                ("percent_used", models.FloatField(blank=True, null=True)),
                (
                    "status",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_pools",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pools",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph pool",
                "verbose_name_plural": "Ceph pools",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephpool",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_pool_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephFilesystem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=255)),
                (
                    "data_pools",
                    models.JSONField(blank=True, default=list, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("standby_count_wanted", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_filesystems",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="filesystems",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                (
                    "metadata_pool",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="metadata_filesystems",
                        to="netbox_ceph.cephpool",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph filesystem",
                "verbose_name_plural": "Ceph filesystems",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephfilesystem",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_filesystem_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephCrushRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=255)),
                ("rule_id", models.IntegerField(blank=True, null=True)),
                ("rule_type", models.CharField(blank=True, max_length=64)),
                ("device_class", models.CharField(blank=True, max_length=64)),
                (
                    "steps",
                    models.JSONField(blank=True, default=list, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                (
                    "raw",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_crush_rules",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crush_rules",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph CRUSH rule",
                "verbose_name_plural": "Ceph CRUSH rules",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephcrushrule",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_crush_rule_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephFlag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=64)),
                ("enabled", models.BooleanField(blank=True, null=True)),
                ("value", models.CharField(blank=True, max_length=255)),
                (
                    "raw",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_flags",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flags",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph flag",
                "verbose_name_plural": "Ceph flags",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephflag",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_flag_identity",
            ),
        ),
        migrations.CreateModel(
            name="CephHealthCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ("name", models.CharField(max_length=255)),
                ("severity", models.CharField(default="unknown", max_length=32)),
                ("summary", models.CharField(blank=True, max_length=512)),
                (
                    "detail",
                    models.JSONField(blank=True, default=list, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ("source", models.CharField(blank=True, max_length=64)),
                ("first_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ceph_health_checks",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="health_checks",
                        to="netbox_ceph.cephcluster",
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Ceph health check",
                "verbose_name_plural": "Ceph health checks",
                "ordering": ("endpoint", "severity", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="cephhealthcheck",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_health_check_identity",
            ),
        ),
    ]
