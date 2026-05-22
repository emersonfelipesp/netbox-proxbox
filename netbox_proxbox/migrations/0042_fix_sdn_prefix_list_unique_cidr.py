from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0041_pve_9_2"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="proxmoxsdnprefixlist",
            name="netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name",
        ),
        migrations.AddConstraint(
            model_name="proxmoxsdnprefixlist",
            constraint=models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "name", "cidr"],
                name="netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name_cidr",
            ),
        ),
    ]
