from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0052_proxmoxendpoint_allowed_tenants"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="enable_tenant_from_cluster",
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="enable_tenant_from_cluster",
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
