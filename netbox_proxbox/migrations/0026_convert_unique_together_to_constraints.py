"""Convert unique_together to UniqueConstraint with explicit names."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0025_add_operational_settings"),
    ]

    operations = [
        # Remove old unique_together constraints and add new named constraints
        # Using RunSQL for PostgreSQL to safely handle constraint removal
        migrations.RunSQL(
            sql=[
                "ALTER TABLE netbox_proxbox_proxmoxstorage DROP CONSTRAINT IF EXISTS netbox_proxbox_proxmoxstorage_cluster_id_name_key;",
                "ALTER TABLE netbox_proxbox_proxmoxstoragevirtualdisk DROP CONSTRAINT IF EXISTS netbox_proxbox_proxmoxstor_proxmox_s_virtual__key;",
                "ALTER TABLE netbox_proxbox_vmbackup DROP CONSTRAINT IF EXISTS netbox_proxbox_vmbackup_storage_virtual_machi_key;",
                "ALTER TABLE netbox_proxbox_vmsnapshot DROP CONSTRAINT IF EXISTS netbox_proxbox_vmsnapshot_vmid_name_node_key;",
            ],
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[],
        ),
        migrations.AddConstraint(
            model_name="proxmoxstorage",
            constraint=models.UniqueConstraint(
                fields=("cluster", "name"),
                name="unique_proxmox_storage_cluster_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxstoragevirtualdisk",
            constraint=models.UniqueConstraint(
                fields=("proxmox_storage", "virtual_disk"),
                name="unique_proxmox_storage_virtual_disk",
            ),
        ),
        migrations.AddConstraint(
            model_name="vmbackup",
            constraint=models.UniqueConstraint(
                fields=(
                    "storage",
                    "virtual_machine",
                    "subtype",
                    "format",
                    "volume_id",
                    "vmid",
                ),
                name="unique_vm_backup_fields",
            ),
        ),
        migrations.AddConstraint(
            model_name="vmsnapshot",
            constraint=models.UniqueConstraint(
                fields=("vmid", "name", "node"),
                name="unique_vm_snapshot_vmid_name_node",
            ),
        ),
    ]
