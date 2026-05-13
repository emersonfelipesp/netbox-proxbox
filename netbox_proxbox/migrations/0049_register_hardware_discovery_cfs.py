"""Register the six hardware-discovery custom fields on dcim.Device and dcim.Interface.

Reflects the parsed dmidecode + ethtool output onto NetBox. Three chassis fields
land on ``dcim.Device`` (serial, manufacturer, product) and three NIC fields land
on ``dcim.Interface`` (speed in Gbps, duplex, link state). All six are written by
proxbox-api's hardware-discovery pass when ``ProxboxPluginSettings.hardware_discovery_enabled``
is True; they are user-visible read-mostly fields, not internal snapshots.

Idempotent: ``get_or_create`` on each name and content-type assignment via
``cf.object_types.add(...)`` only when not already present. Same defensive
pattern as ``0046_register_last_synced_role_cf.py``.
"""

from django.db import migrations


DEVICE_FIELDS = (
    (
        "hardware_chassis_serial",
        "text",
        "Chassis serial",
        (
            "Chassis serial number reported by dmidecode -t 3 during SSH-based "
            "hardware discovery. Populated automatically by Proxbox when enabled."
        ),
    ),
    (
        "hardware_chassis_manufacturer",
        "text",
        "Chassis manufacturer",
        (
            "Chassis manufacturer string reported by dmidecode -t 1 during "
            "SSH-based hardware discovery."
        ),
    ),
    (
        "hardware_chassis_product",
        "text",
        "Chassis product name",
        (
            "Chassis product / model name reported by dmidecode -t 1 during "
            "SSH-based hardware discovery."
        ),
    ),
)

INTERFACE_FIELDS = (
    (
        "nic_speed_gbps",
        "integer",
        "NIC speed (Gbps)",
        (
            "Negotiated NIC link speed in Gbps, parsed from ethtool output during "
            "SSH-based hardware discovery."
        ),
    ),
    (
        "nic_duplex",
        "text",
        "NIC duplex",
        (
            "Negotiated NIC duplex mode (full/half/unknown), parsed from ethtool "
            "output during SSH-based hardware discovery."
        ),
    ),
    (
        "nic_link",
        "boolean",
        "NIC link up",
        (
            "Whether the NIC reports link up, parsed from ethtool output during "
            "SSH-based hardware discovery."
        ),
    ),
)


def _ensure_cf(CustomField, ContentType, name, type_, label, description, app_label, model):
    ct, _ = ContentType.objects.get_or_create(
        app_label=app_label,
        model=model,
    )
    cf, _created = CustomField.objects.get_or_create(
        name=name,
        defaults={
            "type": type_,
            "label": label,
            "description": description,
            "ui_visible": "always",
            "ui_editable": "hidden",
            "filter_logic": "disabled",
            "required": False,
            "search_weight": 0,
        },
    )
    if not cf.object_types.filter(pk=ct.pk).exists():
        cf.object_types.add(ct)


def register_hardware_discovery_cfs(apps, schema_editor):
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    for name, type_, label, description in DEVICE_FIELDS:
        _ensure_cf(CustomField, ContentType, name, type_, label, description, "dcim", "device")
    for name, type_, label, description in INTERFACE_FIELDS:
        _ensure_cf(CustomField, ContentType, name, type_, label, description, "dcim", "interface")


def unregister_hardware_discovery_cfs(apps, schema_editor):
    CustomField = apps.get_model("extras", "CustomField")
    names = [name for name, _, _, _ in DEVICE_FIELDS + INTERFACE_FIELDS]
    CustomField.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0048_node_ssh_credential"),
        ("extras", "0100_customfield_ui_attrs"),
        ("dcim", "0001_squashed"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            register_hardware_discovery_cfs,
            reverse_code=unregister_hardware_discovery_cfs,
        ),
    ]
