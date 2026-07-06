"""Add netbox_openapi_persist setting for in-memory NetBox OpenAPI schema mode."""

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0056_proxmoxendpoint_access_methods"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="netbox_openapi_persist",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When enabled (default), proxbox-api caches the resolved NetBox OpenAPI "
                    "schema on disk. Disable to run schema resolution fully in-memory and never "
                    "write to the filesystem (read-only filesystems or no-disk-write "
                    "deployments). The PROXBOX_NETBOX_OPENAPI_PERSIST environment variable "
                    "overrides this setting."
                ),
                verbose_name="Persist NetBox OpenAPI schema to disk",
            ),
        ),
    ]
