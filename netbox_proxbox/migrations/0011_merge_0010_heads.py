"""Merge divergent 0010 migration heads."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0010_alter_fastapiendpoint_options_and_more"),
        ("netbox_proxbox", "0010_netboxendpoint_token_v2_support"),
    ]

    operations = []
