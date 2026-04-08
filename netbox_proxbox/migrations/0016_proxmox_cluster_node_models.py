"""Django migration for netbox_proxbox."""

# Manual migration for ProxmoxCluster and ProxmoxNode models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0015_alter_vmbackup_unique_together_alter_vmbackup_vmid_and_more"),
        ("dcim", "0226_modulebay_rebuild_tree"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxmoxCluster",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(auto_now_add=True, null=True),
                ),
                (
                    "last_updated",
                    models.DateTimeField(auto_now=True, null=True),
                ),
                (
                    "custom_field_data",
                    models.JSONField(blank=True, default=dict, null=True),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Proxmox cluster name as reported by the API.",
                        max_length=255,
                        verbose_name="Cluster name",
                    ),
                ),
                (
                    "cluster_id",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox cluster ID.",
                        max_length=255,
                        verbose_name="Cluster ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("undefined", "Undefined"),
                            ("standalone", "Standalone"),
                            ("cluster", "Cluster"),
                        ],
                        default="cluster",
                        help_text="Cluster mode: standalone or cluster.",
                        max_length=255,
                        verbose_name="Mode",
                    ),
                ),
                (
                    "nodes_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of nodes in the cluster.",
                        verbose_name="Nodes count",
                    ),
                ),
                (
                    "quorate",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the cluster has quorum.",
                        verbose_name="Quorate",
                    ),
                ),
                (
                    "version",
                    models.IntegerField(
                        blank=True,
                        help_text="Corosync configuration version.",
                        null=True,
                        verbose_name="Corosync version",
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        help_text="ProxmoxEndpoint this cluster is discovered from.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_clusters",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "netbox_cluster",
                    models.ForeignKey(
                        blank=True,
                        help_text="Linked NetBox cluster object created during device sync.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proxmox_cluster_tracking",
                        to="virtualization.cluster",
                        verbose_name="NetBox cluster",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox cluster",
                "verbose_name_plural": "Proxmox clusters",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.CreateModel(
            name="ProxmoxNode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(auto_now_add=True, null=True),
                ),
                (
                    "last_updated",
                    models.DateTimeField(auto_now=True, null=True),
                ),
                (
                    "custom_field_data",
                    models.JSONField(blank=True, default=dict, null=True),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Proxmox node hostname.",
                        max_length=255,
                        verbose_name="Node name",
                    ),
                ),
                (
                    "node_id",
                    models.IntegerField(
                        blank=True,
                        help_text="Corosync node ID (null for standalone nodes).",
                        null=True,
                        verbose_name="Node ID",
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        help_text="Node IP address.",
                        verbose_name="IP address",
                    ),
                ),
                (
                    "online",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the node is currently online.",
                        verbose_name="Online",
                    ),
                ),
                (
                    "local",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this is the local node of the cluster.",
                        verbose_name="Local node",
                    ),
                ),
                (
                    "cpu_usage",
                    models.FloatField(
                        blank=True,
                        help_text="CPU utilization percentage.",
                        null=True,
                        verbose_name="CPU usage",
                    ),
                ),
                (
                    "max_cpu",
                    models.IntegerField(
                        blank=True,
                        help_text="Number of CPU cores available.",
                        null=True,
                        verbose_name="Max CPU",
                    ),
                ),
                (
                    "memory_usage",
                    models.BigIntegerField(
                        blank=True,
                        help_text="Used memory in bytes.",
                        null=True,
                        verbose_name="Memory usage",
                    ),
                ),
                (
                    "max_memory",
                    models.BigIntegerField(
                        blank=True,
                        help_text="Total memory available in bytes.",
                        null=True,
                        verbose_name="Max memory",
                    ),
                ),
                (
                    "ssl_fingerprint",
                    models.CharField(
                        blank=True,
                        help_text="SSL certificate fingerprint.",
                        max_length=255,
                        verbose_name="SSL fingerprint",
                    ),
                ),
                (
                    "support_level",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox subscription/support level.",
                        max_length=100,
                        verbose_name="Support level",
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        help_text="ProxmoxEndpoint this node is discovered from.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_nodes",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "proxmox_cluster",
                    models.ForeignKey(
                        blank=True,
                        help_text="ProxmoxCluster this node belongs to (null for standalone).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="nodes",
                        to="netbox_proxbox.proxmoxcluster",
                        verbose_name="Proxmox cluster",
                    ),
                ),
                (
                    "netbox_device",
                    models.ForeignKey(
                        blank=True,
                        help_text="Linked NetBox device object created during device sync.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proxmox_node_tracking",
                        to="dcim.device",
                        verbose_name="NetBox device",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox node",
                "verbose_name_plural": "Proxmox nodes",
                "ordering": ("endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="proxmoxcluster",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_proxbox_proxmoxcluster_unique_endpoint_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxnode",
            constraint=models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_proxbox_proxmoxnode_unique_endpoint_name",
            ),
        ),
    ]
