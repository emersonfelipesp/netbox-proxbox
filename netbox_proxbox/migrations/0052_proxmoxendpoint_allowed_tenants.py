from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0023_add_mptt_tree_indexes"),
        ("netbox_proxbox", "0051_add_interface_mac_sync_modes"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="allowed_tenants",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Tenants explicitly granted access to this endpoint. Leave empty "
                    "for default visibility; NMS Cloud callers with any explicit "
                    "endpoint grant see only their granted endpoints."
                ),
                related_name="proxbox_proxmox_endpoints",
                to="tenancy.tenant",
                verbose_name="Allowed tenants",
            ),
        ),
    ]
