"""Register the proxmox_last_synced_role_id custom field on VirtualMachine.

This field is the snapshot used by the sync reconciler to detect operator
edits to a VM's role: when the stored snapshot diverges from the current
role_id, the VM is considered operator-edited and the role is preserved
across sync runs. The field is hidden in the NetBox UI.

Idempotent: uses get_or_create on the name and adds the VirtualMachine
content type to object_types if missing.
"""

from django.db import migrations


CUSTOM_FIELD_NAME = "proxmox_last_synced_role_id"


def register_last_synced_role_cf(apps, schema_editor):
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        vm_ct = ContentType.objects.get(app_label="virtualization", model="virtualmachine")
    except ContentType.DoesNotExist:
        return

    cf, _created = CustomField.objects.get_or_create(
        name=CUSTOM_FIELD_NAME,
        defaults={
            "type": "integer",
            "label": "Proxmox last-synced role id",
            "description": (
                "Snapshot of the role id last written by Proxbox sync. Used to "
                "detect operator edits to the VM role between sync runs. Managed "
                "automatically by Proxbox; do not edit."
            ),
            "ui_visible": "hidden",
            "ui_editable": "hidden",
            "filter_logic": "disabled",
            "required": False,
            "search_weight": 0,
        },
    )
    if not cf.object_types.filter(pk=vm_ct.pk).exists():
        cf.object_types.add(vm_ct)


def unregister_last_synced_role_cf(apps, schema_editor):
    CustomField = apps.get_model("extras", "CustomField")
    CustomField.objects.filter(name=CUSTOM_FIELD_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0045_seed_default_vm_roles"),
        ("extras", "0100_customfield_ui_attrs"),
        ("virtualization", "0001_squashed_0022"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            register_last_synced_role_cf,
            reverse_code=unregister_last_synced_role_cf,
        ),
    ]
