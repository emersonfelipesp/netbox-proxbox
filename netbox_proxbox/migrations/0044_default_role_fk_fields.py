import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0043_pluginsettings_branching_fields"),
        ("dcim", "0227_alter_interface_speed_bigint"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="default_role_qemu",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default QEMU VM role",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="default_role_lxc",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default LXC container role",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="default_role_qemu",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default QEMU VM role",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="default_role_lxc",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default LXC container role",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxnode",
            name="default_role_qemu",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default QEMU VM role",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxnode",
            name="default_role_lxc",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                limit_choices_to={"vm_role": True},
                to="dcim.devicerole",
                verbose_name="Default LXC container role",
            ),
        ),
    ]
