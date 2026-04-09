"""Add extended Proxmox storage fields to ProxmoxStorage."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0024_replication_add_endpoint_status_rawconfig_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxstorage",
            name="server",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="username",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="export",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="share",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="pool",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="monhost",
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="namespace",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="datastore",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="subdir",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="mountpoint",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="is_mountpoint",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="preallocation",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="format",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="prune_backups",
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="max_protected_backups",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="raw_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Full raw configuration returned by the Proxmox storage API.",
            ),
        ),
    ]
