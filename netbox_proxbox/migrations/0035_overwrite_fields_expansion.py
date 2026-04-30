from django.db import migrations, models


_ENDPOINT_NEW_FIELDS = (
    "overwrite_device_status",
    "overwrite_device_description",
    "overwrite_device_custom_fields",
    "overwrite_vm_description",
    "overwrite_vm_custom_fields",
    "overwrite_cluster_tags",
    "overwrite_cluster_description",
    "overwrite_cluster_custom_fields",
    "overwrite_node_interface_tags",
    "overwrite_node_interface_custom_fields",
    "overwrite_storage_tags",
    "overwrite_vm_interface_tags",
    "overwrite_vm_interface_custom_fields",
    "overwrite_ip_status",
    "overwrite_ip_tags",
    "overwrite_ip_custom_fields",
)


_SETTINGS_NEW_FIELDS = _ENDPOINT_NEW_FIELDS


_VERBOSE_NAMES = {
    "overwrite_device_status": "Overwrite device status",
    "overwrite_device_description": "Overwrite device description",
    "overwrite_device_custom_fields": "Overwrite device custom fields",
    "overwrite_vm_description": "Overwrite VM description",
    "overwrite_vm_custom_fields": "Overwrite VM custom fields",
    "overwrite_cluster_tags": "Overwrite cluster tags",
    "overwrite_cluster_description": "Overwrite cluster description",
    "overwrite_cluster_custom_fields": "Overwrite cluster custom fields",
    "overwrite_node_interface_tags": "Overwrite node interface tags",
    "overwrite_node_interface_custom_fields": "Overwrite node interface custom fields",
    "overwrite_storage_tags": "Overwrite storage tags",
    "overwrite_vm_interface_tags": "Overwrite VM interface tags",
    "overwrite_vm_interface_custom_fields": "Overwrite VM interface custom fields",
    "overwrite_ip_status": "Overwrite IP status",
    "overwrite_ip_tags": "Overwrite IP tags",
    "overwrite_ip_custom_fields": "Overwrite IP custom fields",
}


def _endpoint_db_ops() -> list[migrations.RunSQL]:
    ops: list[migrations.RunSQL] = []
    for name in _ENDPOINT_NEW_FIELDS:
        ops.append(
            migrations.RunSQL(
                sql=f'ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "{name}" boolean NULL;',
                reverse_sql=f'ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "{name}";',
            )
        )
    return ops


def _settings_db_ops() -> list[migrations.RunSQL]:
    ops: list[migrations.RunSQL] = []
    for name in _SETTINGS_NEW_FIELDS:
        ops.append(
            migrations.RunSQL(
                sql=(
                    f'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                    f'ADD COLUMN IF NOT EXISTS "{name}" boolean NOT NULL DEFAULT TRUE;'
                ),
                reverse_sql=(
                    f'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "{name}";'
                ),
            )
        )
    return ops


def _endpoint_state_ops() -> list[migrations.AddField]:
    return [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name=name,
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name=_VERBOSE_NAMES[name],
                help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
            ),
        )
        for name in _ENDPOINT_NEW_FIELDS
    ]


def _settings_state_ops() -> list[migrations.AddField]:
    return [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name=name,
            field=models.BooleanField(
                default=True,
                verbose_name=_VERBOSE_NAMES[name],
            ),
        )
        for name in _SETTINGS_NEW_FIELDS
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0034_proxmoxendpoint_overwrite_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=_endpoint_db_ops(),
            state_operations=_endpoint_state_ops(),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=_settings_db_ops(),
            state_operations=_settings_state_ops(),
        ),
    ]
