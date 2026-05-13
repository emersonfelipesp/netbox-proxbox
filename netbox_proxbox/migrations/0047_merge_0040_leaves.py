from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0040_pluginsettings_ensure_netbox_objects"),
        ("netbox_proxbox", "0040_pluginsettings_parse_description_metadata"),
        ("netbox_proxbox", "0046_pluginsettings_delete_orphans"),
    ]

    operations = []
