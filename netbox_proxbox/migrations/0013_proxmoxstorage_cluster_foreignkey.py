"""Change ProxmoxStorage.cluster from CharField to ForeignKey to Cluster."""

import django.db.models.deletion
from django.db import migrations, models


def migrate_cluster_names_to_foreign_keys(apps, schema_editor):
    """Populate the new cluster ForeignKey by looking up clusters by name."""
    ProxmoxStorage = apps.get_model("netbox_proxbox", "ProxmoxStorage")
    Cluster = apps.get_model("virtualization", "Cluster")

    # Create a mapping of cluster names to cluster objects
    cluster_map = {c.name: c for c in Cluster.objects.all()}

    for storage in ProxmoxStorage.objects.all():
        cluster_name = getattr(storage, "cluster_old", None) or getattr(
            storage, "cluster", None
        )
        if cluster_name and cluster_name in cluster_map:
            storage.cluster = cluster_map[cluster_name]
            storage.save(update_fields=["cluster"])


def reverse_migrate_cluster_foreign_keys(apps, schema_editor):
    """Reverse migration: store cluster names in a temporary field."""
    ProxmoxStorage = apps.get_model("netbox_proxbox", "ProxmoxStorage")

    for storage in ProxmoxStorage.objects.all():
        if storage.cluster:
            # Store the name for potential future use
            storage.cluster_old = storage.cluster.name
            storage.save(update_fields=["cluster_old"])


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0012_fix_missing_storage_tables"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        # Rename the existing cluster field to cluster_old temporarily
        migrations.RenameField(
            model_name="proxmoxstorage",
            old_name="cluster",
            new_name="cluster_old",
        ),
        # Add the new cluster ForeignKey field
        migrations.AddField(
            model_name="proxmoxstorage",
            name="cluster",
            field=models.ForeignKey(
                to="virtualization.Cluster",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="proxmox_storages",
                null=True,  # Allow null temporarily for migration
            ),
        ),
        # Run data migration to populate the new cluster field
        migrations.RunPython(
            migrate_cluster_names_to_foreign_keys,
            reverse_migrate_cluster_foreign_keys,
        ),
        # Remove the old cluster field
        migrations.RemoveField(
            model_name="proxmoxstorage",
            name="cluster_old",
        ),
        # Make the new cluster field non-nullable
        migrations.AlterField(
            model_name="proxmoxstorage",
            name="cluster",
            field=models.ForeignKey(
                to="virtualization.Cluster",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="proxmox_storages",
            ),
        ),
    ]
