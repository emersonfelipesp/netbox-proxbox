"""Add ``embed_description_metadata`` plugin setting for issue #423.

Mirrors ``parse_description_metadata`` (#366, read-side) by adding a single
opt-in BooleanField that gates the intent-path write of a fenced
``netbox-metadata`` JSON block into the Proxmox description. Default
``False`` keeps the intent path byte-for-byte identical to v0.0.15 for
existing deployments.

Also merges the 0044 leaf fork (``0044_overwrite_vm_proxmox_tags`` was added
in parallel with ``0044_cloud_image_template`` -> ``0045_proxmoxendpoint_environment``)
by depending on both leaves so Django sees a single linear graph again.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0044_overwrite_vm_proxmox_tags"),
        ("netbox_proxbox", "0045_proxmoxendpoint_environment"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="embed_description_metadata",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, intent-direction create/update writes to Proxmox "
                    "append a fenced ``netbox-metadata`` JSON block of NetBox FK ids "
                    "(role, tenant, site, platform, cluster, device) to the Proxmox "
                    "object's description. Pairs with ``parse_description_metadata`` "
                    "to round-trip NetBox metadata through Proxmox without drift. "
                    "Disabled by default."
                ),
                verbose_name="Embed description metadata",
            ),
        ),
    ]
