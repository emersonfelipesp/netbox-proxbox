"""Django migration: add endpoint, status, raw_config to Replication; centralize choices; update unique constraint."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0023_proxboxpluginsettings_encryption_key"),
    ]

    operations = [
        # Add endpoint FK (nullable to preserve existing rows)
        migrations.AddField(
            model_name="replication",
            name="endpoint",
            field=models.ForeignKey(
                blank=True,
                help_text="ProxmoxEndpoint this replication job is discovered from.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="replications",
                to="netbox_proxbox.proxmoxendpoint",
                verbose_name="Proxmox endpoint",
            ),
        ),
        # Add status field
        migrations.AddField(
            model_name="replication",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("stale", "Stale")],
                default="active",
                help_text="Active or stale — stale jobs no longer exist in Proxmox.",
                max_length=20,
                verbose_name="Status",
            ),
        ),
        # Add raw_config field
        migrations.AddField(
            model_name="replication",
            name="raw_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Full raw configuration from Proxmox API for reference.",
                verbose_name="Raw Configuration",
            ),
        ),
        # Remove old unique=True on replication_id
        migrations.AlterField(
            model_name="replication",
            name="replication_id",
            field=models.CharField(
                help_text="Replication job ID. Composed of guest ID and job number: '<GUEST>-<JOBNUM>'.",
                max_length=255,
            ),
        ),
        # Update job_type choices (no data change, just new choices class reference)
        migrations.AlterField(
            model_name="replication",
            name="job_type",
            field=models.CharField(
                choices=[("local", "Local")],
                default="local",
                help_text="Replication type.",
                max_length=50,
            ),
        ),
        # Update remove_job choices
        migrations.AlterField(
            model_name="replication",
            name="remove_job",
            field=models.CharField(
                blank=True,
                choices=[("local", "Local"), ("full", "Full")],
                help_text="Mark the replication job for removal.",
                max_length=50,
                null=True,
            ),
        ),
        # Update ordering via AlterModelOptions
        migrations.AlterModelOptions(
            name="replication",
            options={
                "ordering": ("endpoint", "replication_id"),
                "verbose_name": "Replication",
                "verbose_name_plural": "Replications",
            },
        ),
        # Add new unique constraint on (endpoint, replication_id)
        migrations.AddConstraint(
            model_name="replication",
            constraint=models.UniqueConstraint(
                fields=["endpoint", "replication_id"],
                name="netbox_proxbox_replication_unique_endpoint_replication_id",
            ),
        ),
    ]
