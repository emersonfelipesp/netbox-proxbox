"""Merge the per-endpoint rpc-enabled branch with the service-monitoring merge.

`main` carried `0059_proxmoxendpoint_rpc_enabled` (per-endpoint netbox-rpc
enablement override) off `0058`, a sibling leaf to the develop-side
`0062_merge_cloud_network_service_monitoring`. Back-merging `main` into
`develop` therefore leaves two leaf nodes; this empty merge migration
reconciles them. No schema operations.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0062_merge_cloud_network_service_monitoring"),
        ("netbox_proxbox", "0059_proxmoxendpoint_rpc_enabled"),
    ]

    operations = []
