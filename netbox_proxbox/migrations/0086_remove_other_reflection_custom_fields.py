"""Remove remaining reflection custom fields after typed-state cutover."""

from __future__ import annotations

from django.db import migrations


OTHER_REFLECTION_CUSTOM_FIELD_NAMES = (
    "hardware_chassis_manufacturer",
    "hardware_chassis_product",
    "hardware_chassis_serial",
    "nic_duplex",
    "nic_link",
    "nic_speed_gbps",
    "proxmox_cluster_id",
    "proxmox_cluster_name",
    "proxmox_cluster_status",
    "proxmox_interface",
    "proxmox_ip_addresses",
    "proxmox_mac",
    "proxmox_vlan_id",
    "proxbox_bridge",
    "proxbox_storage_id",
    "proxmox_cluster",
    "proxmox_cpu_type",
    "proxmox_device_names",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_link",
    "proxmox_notes",
    "proxmox_os",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_tags",
    "proxmox_tcp_states",
    "proxmox_vmid",
    "proxbox_last_run_id",
    "proxmox_last_updated",
)

OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS = (
    {
        "name": "hardware_chassis_manufacturer",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis manufacturer",
        "description": (
            "Chassis manufacturer string reported by dmidecode -t 1 during "
            "SSH-based hardware discovery."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "hardware_chassis_product",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis product name",
        "description": (
            "Chassis product / model name reported by dmidecode -t 1 during "
            "SSH-based hardware discovery."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "hardware_chassis_serial",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis serial",
        "description": (
            "Chassis serial number reported by dmidecode -t 3 during SSH-based "
            "hardware discovery. Populated automatically by Proxbox when enabled."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "nic_duplex",
        "object_types": ("dcim.interface",),
        "type": "text",
        "label": "NIC duplex",
        "description": (
            "Negotiated NIC duplex mode (full/half/unknown), parsed from ethtool "
            "output during SSH-based hardware discovery."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "nic_link",
        "object_types": ("dcim.interface",),
        "type": "boolean",
        "label": "NIC link up",
        "description": (
            "Whether the NIC reports link up, parsed from ethtool output during "
            "SSH-based hardware discovery."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "nic_speed_gbps",
        "object_types": ("dcim.interface",),
        "type": "integer",
        "label": "NIC speed (Gbps)",
        "description": (
            "Negotiated NIC link speed in Gbps, parsed from ethtool output during "
            "SSH-based hardware discovery."
        ),
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "proxmox_cluster_id",
        "object_types": ("virtualization.cluster",),
        "type": "integer",
        "label": "Cluster ID",
        "description": "Proxmox cluster ID",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_cluster_name",
        "object_types": (
            "virtualization.cluster",
            "virtualization.clustergroup",
        ),
        "type": "text",
        "label": "Cluster Name",
        "description": "Cluster name from Proxmox",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_cluster_status",
        "object_types": (
            "virtualization.cluster",
            "virtualization.clustergroup",
        ),
        "type": "text",
        "label": "Cluster Status",
        "description": "Cluster status from Proxmox",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_interface",
        "object_types": ("ipam.ipaddress",),
        "type": "text",
        "label": "Proxmox Interface",
        "description": "Proxmox network interface name",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_ip_addresses",
        "object_types": ("ipam.ipaddress",),
        "type": "text",
        "label": "IP Addresses",
        "description": "All IP addresses from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_mac",
        "object_types": ("ipam.ipaddress",),
        "type": "text",
        "label": "Proxmox MAC",
        "description": "MAC address from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_vlan_id",
        "object_types": ("ipam.vlan",),
        "type": "integer",
        "label": "Proxmox VLAN ID",
        "description": "VLAN ID from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxbox_bridge",
        "object_types": ("virtualization.vminterface",),
        "type": "object",
        "label": "Proxbox Bridge",
        "related_object_type": "dcim.interface",
        "description": "Node-level bridge interface (vmbr) used by this VM interface",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxbox_storage_id",
        "object_types": ("virtualization.virtualdisk",),
        "type": "object",
        "label": "Proxbox Storage",
        "related_object_type": "netbox_proxbox.proxmoxstorage",
        "description": "Proxmox storage hosting this virtual disk",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_cluster",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Proxmox Cluster",
        "description": "Proxmox cluster name",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_cpu_type",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "CPU Type",
        "description": "CPU type from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_device_names",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Device Names",
        "description": "Comma-separated device names",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_disk",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Disk (GB)",
        "description": "Total disk size in GB",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_interfaces",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Network Interfaces",
        "description": "Network interface count",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_link",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "url",
        "label": "Proxmox Link",
        "description": "Link to Proxmox web interface",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_notes",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Proxmox Notes",
        "description": "Notes from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_os",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Operating System",
        "description": "Operating system from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_storage_ids",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Storage IDs",
        "description": "Comma-separated storage IDs",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_storage_names",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Storage Names",
        "description": "Comma-separated storage names",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_tags",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Proxmox Tags",
        "description": "Comma-separated tags from Proxmox",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_tcp_states",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "TCP States",
        "description": "TCP connection states",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_vmid",
        "object_types": (
            "dcim.device",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Proxmox VMID",
        "description": "VM ID for reference",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxbox_last_run_id",
        "object_types": (
            "dcim.device",
            "virtualization.cluster",
            "virtualization.virtualmachine",
        ),
        "type": "text",
        "label": "Last Run ID",
        "description": "UUID of the most recent Proxbox sync run that touched this object.",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 250,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxbox",
    },
    {
        "name": "proxmox_last_updated",
        "object_types": (
            "dcim.device",
            "dcim.devicerole",
            "dcim.devicetype",
            "dcim.interface",
            "dcim.manufacturer",
            "dcim.site",
            "ipam.ipaddress",
            "ipam.vlan",
            "virtualization.cluster",
            "virtualization.clustertype",
            "virtualization.virtualdisk",
            "virtualization.virtualmachine",
            "virtualization.vminterface",
        ),
        "type": "datetime",
        "label": "Last Updated",
        "description": "Proxmox Plugin last modified this object",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 200,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
)

AFFECTED_OBJECT_TYPES = (
    ("dcim", "Device"),
    ("dcim", "Interface"),
    ("dcim", "Manufacturer"),
    ("dcim", "Site"),
    ("dcim", "DeviceRole"),
    ("dcim", "DeviceType"),
    ("ipam", "IPAddress"),
    ("ipam", "VLAN"),
    ("virtualization", "Cluster"),
    ("virtualization", "ClusterGroup"),
    ("virtualization", "ClusterType"),
    ("virtualization", "VirtualMachine"),
    ("virtualization", "VirtualDisk"),
    ("virtualization", "VMInterface"),
)

_BATCH_SIZE = 500


def _strip_stale_values(model, db_alias: str, names) -> None:
    """Remove exactly *names* from this model's stored custom-field JSON.

    The caller decides the names per object type, and that is the point: a field
    retained because an operator bound it somewhere Proxbox never did keeps its
    values on that binding. Stripping every target name from every affected type
    would delete those values, and the reverse restores definitions and bindings
    but never JSON, so they would be gone for good.
    """
    if not names:
        return
    pending = []
    rows = (
        model.objects.using(db_alias)
        .only("pk", "custom_field_data")
        .iterator(chunk_size=_BATCH_SIZE)
    )
    for obj in rows:
        data = obj.custom_field_data
        if not isinstance(data, dict):
            continue
        cleaned = dict(data)
        for name in names:
            cleaned.pop(name, None)
            # The backfill era accepted both spellings, so a row can still carry
            # the prefixed alias. Removing only the bare key leaves the same
            # retired value readable through any generic JSON or API reader.
            cleaned.pop(f"cf_{name}", None)
        if cleaned == data:
            continue
        obj.custom_field_data = cleaned
        pending.append(obj)
        if len(pending) >= _BATCH_SIZE:
            model.objects.using(db_alias).bulk_update(
                pending,
                ("custom_field_data",),
                batch_size=_BATCH_SIZE,
            )
            pending.clear()
    if pending:
        model.objects.using(db_alias).bulk_update(
            pending,
            ("custom_field_data",),
            batch_size=_BATCH_SIZE,
        )


_OWNERSHIP_FIELDS = ("type", "label")


def _looks_like_proxbox_field(custom_field, definition) -> bool:
    """Return whether this row still matches the definition Proxbox created.

    Name plus object type is not proof of ownership: an operator can repurpose
    one of these names on an object type we also used. Comparing the fields that
    define what the custom field *is* -- its data type and its label -- separates
    "the field we made" from "a field that happens to share its name". A row
    that has drifted is left completely untouched, which is the only safe
    reading, because nothing in the reverse could restore its values.

    Deliberately narrow: description and UI flags are the sort of thing an
    operator may legitimately tidy without repurposing anything, and treating
    that as foreign would strand our own fields forever.
    """
    for attribute in _OWNERSHIP_FIELDS:
        expected = definition.get(attribute)
        if expected is None:
            continue
        if getattr(custom_field, attribute, None) != expected:
            return False
    return True


def _canonical_binding_ids(ContentType, db_alias: str, definition) -> set:
    """Return the content-type ids Proxbox itself bound this field to."""
    ids = set()
    for dotted_name in definition["object_types"]:
        content_type = _content_type(ContentType, db_alias, dotted_name)
        if content_type is not None:
            ids.add(content_type.pk)
    return ids


def remove_other_reflection_custom_fields(apps, schema_editor) -> None:
    """Release Proxbox's own bindings; delete only fields left with none.

    Deleting by name alone is wrong on an installation that is not ours. This
    plugin is public, and nothing stops an operator binding one of these names
    to an object type Proxbox never used, or repurposing the field outright. A
    `filter(name__in=...).delete()` would take the definition and every value
    with it, including data this plugin never wrote and cannot restore -- the
    reverse only knows Proxbox's own bindings.

    So each field is matched by name, the canonical Proxbox bindings are
    removed, and the definition itself is deleted only when no other binding
    survives. A field carrying an unrelated binding keeps its row and that
    binding; NetBox drops the stored values for the object types that were
    unbound, which is exactly the intended effect and no more.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias

    definitions = {
        definition["name"]: definition
        for definition in OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS
    }
    # Names whose stored values this migration is entitled to remove, per object
    # type. A field Proxbox owned outright is released everywhere; a field an
    # operator also bound elsewhere is released only from the object types
    # Proxbox itself bound it to, so their values on their binding survive.
    # Built from the definition table, not from which rows happen to exist: a
    # name whose definition was already removed can still have orphaned JSON
    # keys, and those are exactly what this pass is for. Only the object types
    # Proxbox itself bound appear here, so an operator's own binding elsewhere
    # keeps its values.
    released_by_type: dict[str, set] = {}
    for definition in OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS:
        for dotted_name in definition["object_types"]:
            released_by_type.setdefault(dotted_name, set()).add(definition["name"])

    skipped_names: set = set()
    for custom_field in CustomField.objects.using(db_alias).filter(
        name__in=OTHER_REFLECTION_CUSTOM_FIELD_NAMES
    ):
        definition = definitions.get(custom_field.name)
        if definition is None:
            continue
        if not _looks_like_proxbox_field(custom_field, definition):
            # Same name, different field. An operator can repurpose one of these
            # names while keeping a binding we also used, and then the name and
            # the object type together prove nothing about ownership. Releasing
            # that binding would strip values we never wrote, and the reverse
            # restores no JSON, so the loss is permanent. Leave it entirely
            # alone -- including its values, which the released set below is
            # keyed on.
            skipped_names.add(custom_field.name)
            continue
        canonical = _canonical_binding_ids(ContentType, db_alias, definition)
        bound = set(custom_field.object_types.values_list("pk", flat=True))
        if canonical:
            custom_field.object_types.remove(*canonical)
        if not (bound - canonical):
            custom_field.delete()

    for app_label, model_name in AFFECTED_OBJECT_TYPES:
        # AFFECTED_OBJECT_TYPES carries model *class* names for get_model();
        # the definition table carries content-type labels, which are
        # lowercase. Looking up without folding silently matches nothing, and
        # the failure is invisible -- the definitions still go, and every stale
        # JSON key stays behind.
        names = released_by_type.get(f"{app_label}.{model_name}".lower())
        if names:
            names = names - skipped_names
        _strip_stale_values(apps.get_model(app_label, model_name), db_alias, names)


def _content_type(ContentType, db_alias: str, dotted_name: str):
    app_label, model = dotted_name.split(".", 1)
    try:
        return ContentType.objects.using(db_alias).get(
            app_label=app_label,
            model=model,
        )
    except ContentType.DoesNotExist:
        return None


def restore_other_reflection_custom_fields(apps, schema_editor) -> None:
    """Restore every original definition and available object-type binding."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias
    manager = CustomField.objects.using(db_alias)

    for definition in OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS:
        object_types = [
            content_type
            for dotted_name in definition["object_types"]
            if (content_type := _content_type(ContentType, db_alias, dotted_name))
            is not None
        ]
        if not object_types:
            continue
        defaults = {
            key: value
            for key, value in definition.items()
            if key not in {"name", "object_types", "related_object_type"}
        }
        related_object_type = definition.get("related_object_type")
        if related_object_type is not None:
            related_content_type = _content_type(
                ContentType,
                db_alias,
                str(related_object_type),
            )
            if related_content_type is None:
                continue
            defaults["related_object_type"] = related_content_type

        # get_or_create, not update_or_create. A field that survived the forward
        # migration did so because an operator had bound it somewhere Proxbox
        # never did -- it is theirs, and its type, label, description and
        # visibility may be nothing like the definition below. Overwriting those
        # with our metadata would make the rollback destructive in a second way,
        # so an existing row keeps its own definition and only regains the
        # bindings the forward pass released.
        custom_field, _created = manager.get_or_create(
            name=definition["name"],
            defaults=defaults,
        )
        for content_type in object_types:
            custom_field.object_types.add(content_type)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0085_remove_vm_reflection_custom_fields"),
    ]

    operations = [
        migrations.RunPython(
            remove_other_reflection_custom_fields,
            reverse_code=restore_other_reflection_custom_fields,
        ),
    ]
