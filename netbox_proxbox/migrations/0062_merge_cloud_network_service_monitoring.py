"""Merge the cloud-customer-network and service-monitoring migration branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0059_cloud_customer_network_settings"),
        ("netbox_proxbox", "0061_service_monitoring"),
    ]

    operations = []
