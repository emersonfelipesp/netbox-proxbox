"""Django migration for netbox_proxbox."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0016_proxmox_cluster_node_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="ignore_ipv6_link_local_addresses",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, IPv6 link-local addresses (fe80::/64) are ignored during VM interface IP address selection. Disable this only if you need link-local addresses to be included.",
                verbose_name="Ignore IPv6 link-local addresses",
            ),
        ),
    ]
