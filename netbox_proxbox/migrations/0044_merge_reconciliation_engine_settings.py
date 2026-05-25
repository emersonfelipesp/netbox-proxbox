"""Merge reconciliation engine migration branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0043_proxboxpluginsettings_reconciliation_engine"),
        ("netbox_proxbox", "0043_reconciliation_engine_settings"),
    ]

    operations = []
