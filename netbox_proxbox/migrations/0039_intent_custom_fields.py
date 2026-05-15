"""Sub-PR C (#380): register the twelve NetBox→Proxmox intent custom fields.

Ten VM CFs land on ``virtualization.virtualmachine``; two Branch CFs land
on ``netbox_branching.branch`` when that plugin is installed. The data
callable lives in ``_v0_0_16_release_data.py`` so it can be reused.
"""

from __future__ import annotations

from django.db import migrations

from netbox_proxbox.migrations._v0_0_16_release_data import (
    register_intent_custom_fields,
    unregister_intent_custom_fields,
)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('extras', '0134_owner'),
        ('netbox_proxbox', '0038_intent_permissions'),
    ]

    operations = [
        migrations.RunPython(
            register_intent_custom_fields,
            reverse_code=unregister_intent_custom_fields,
        ),
    ]
