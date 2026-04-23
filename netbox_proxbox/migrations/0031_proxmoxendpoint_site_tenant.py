import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0030_vmtaskhistory_status_exitstatus_to_textfield"),
        ("dcim", "0227_alter_interface_speed_bigint"),
        ("tenancy", "0023_add_mptt_tree_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="dcim.site",
                verbose_name="Site",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="tenancy.tenant",
                verbose_name="Tenant",
            ),
        ),
    ]
