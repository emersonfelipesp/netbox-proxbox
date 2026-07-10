"""Add plugin settings for the cloud customer network designation."""

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0058_encrypt_primary_endpoint_secrets"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="cloud_network_lock_enabled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, cloud provisioning integrations should use the "
                    "configured customer network fields below as the authoritative "
                    "NetBox source for customer-facing instance networking."
                ),
                verbose_name="Enable cloud customer network lock",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="cloud_customer_prefix_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Primary key of the NetBox IPAM Prefix designated as the cloud "
                    "customer network. Populate it with the "
                    "ensure_cloud_customer_network management command rather than "
                    "hardcoding estate-specific values."
                ),
                null=True,
                verbose_name="Cloud customer prefix ID",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="cloud_customer_bridge",
            field=models.CharField(
                default="vmbr1",
                help_text=(
                    "Proxmox bridge name used for cloud customer interfaces. The "
                    "default is only a conventional bridge label; the active "
                    "estate-specific network is selected by the management command."
                ),
                max_length=64,
                verbose_name="Cloud customer bridge",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="cloud_customer_vlan_tag",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "VLAN tag associated with the configured cloud customer network. "
                    "Leave blank until an operator runs ensure_cloud_customer_network."
                ),
                null=True,
                verbose_name="Cloud customer VLAN tag",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="cloud_customer_gateway",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Gateway address for the cloud customer network. Stored as "
                    "operator configuration so proxbox-api and nms-backend can "
                    "discover it without hardcoded estate values."
                ),
                max_length=64,
                verbose_name="Cloud customer gateway",
            ),
        ),
    ]
