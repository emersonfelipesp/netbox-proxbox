"""Data callables consolidated for the ``0037_v0_0_15_release`` migration.

These are carried over verbatim from the per-migration sources that lived
between ``0036_add_overwrite_vm_type`` and the v0.0.15 release tip:

  * _backfill_use_https            (was 0038_fastapiendpoint_use_https)
  * _create_run_proxmox_action_perm (was 0041_run_proxmox_action_permission)
  * seed_default_vm_roles          (was develop 0045_seed_default_vm_roles)
  * register_last_synced_role_cf   (was develop 0046_register_last_synced_role_cf)
  * register_hardware_discovery_cfs (was develop 0049_register_hardware_discovery_cfs)

Kept in a leading-underscore module so Django's migration loader skips the
file during discovery (only the parent ``0037_v0_0_15_release`` is loaded as
a migration, and imports the callables from here).
"""

from django.db.models import Max


def _backfill_use_https(apps, schema_editor):
    """Preserve the effective scheme rows used before use_https existed."""
    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")
    FastAPIEndpoint.objects.filter(verify_ssl=True).update(use_https=True)


def _reverse_backfill_use_https(apps, schema_editor):
    return


PERM_CODENAME = "run_proxmox_action"
PERM_NAME = "Can dispatch Proxmox operational verbs"
PERM_CT_APP_LABEL = "core"
PERM_CT_MODEL = "objecttype"


def _create_run_proxmox_action_perm(apps, schema_editor):
    """Register the literal ``core.run_proxmox_action`` permission row."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    ct, _ = ContentType.objects.get_or_create(
        app_label=PERM_CT_APP_LABEL, model=PERM_CT_MODEL
    )
    Permission.objects.get_or_create(
        content_type=ct,
        codename=PERM_CODENAME,
        defaults={"name": PERM_NAME},
    )


def _delete_run_proxmox_action_perm(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        content_type__app_label=PERM_CT_APP_LABEL,
        content_type__model=PERM_CT_MODEL,
        codename=PERM_CODENAME,
    ).delete()


VM_ROLE_SEEDS = (
    {"slug": "virtual-machine-qemu", "name": "Virtual Machine (QEMU)", "color": "9c27b0"},
    {"slug": "container-lxc", "name": "Container (LXC)", "color": "00bcd4"},
)


#: django-mptt bookkeeping columns on the historical ``dcim.DeviceRole`` model.
#: NetBox 4.7 migrated nested group models from django-mptt to PostgreSQL
#: ltree and dropped all four; there, ``path`` is maintained by per-table
#: triggers and ``sort_path`` carries a default, so a plain create is correct
#: and writing to them from Python is explicitly unsupported.
_MPTT_BOOKKEEPING_FIELDS = frozenset({"tree_id", "lft", "rght", "level"})


def _model_has_mptt_columns(model) -> bool:
    """True on NetBox <=4.6, where DeviceRole is still django-mptt backed.

    Keyed off the historical model's concrete field set rather than a NetBox
    version string: inside a data migration the model is reconstructed from
    migration state, so its fields are the only trustworthy signal.
    """
    field_names = {field.name for field in model._meta.get_fields()}
    return _MPTT_BOOKKEEPING_FIELDS <= field_names


def seed_default_vm_roles(apps, schema_editor):
    """Seed the two default VM DeviceRoles and assign them on the singleton."""
    DeviceRole = apps.get_model("dcim", "DeviceRole")
    ProxboxPluginSettings = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")

    uses_mptt = _model_has_mptt_columns(DeviceRole)
    parent_field_available = "parent" in {
        field.name for field in DeviceRole._meta.get_fields()
    }
    next_tree_id = 0
    if uses_mptt:
        next_tree_id = (
            DeviceRole.objects.aggregate(Max("tree_id"))["tree_id__max"] or 0
        ) + 1

    roles_by_slug = {}
    for seed in VM_ROLE_SEEDS:
        defaults = {
            "name": seed["name"],
            "color": seed["color"],
            "vm_role": True,
        }
        if uses_mptt:
            defaults.update(
                {"level": 0, "lft": 1, "rght": 2, "tree_id": next_tree_id}
            )
        # Look up by (parent, slug), not slug alone. NetBox 4.7 makes
        # DeviceRole.slug unique **per parent**
        # (``UniqueConstraint(fields=('parent', 'slug'))``) rather than
        # globally, so a slug-only lookup on an installation that already
        # nests roles can raise MultipleObjectsReturned and block the
        # migration, or silently adopt somebody's child role as the seeded
        # default. These seeds are root roles by construction — the MPTT
        # defaults above say so explicitly — so scoping the lookup to
        # ``parent=None`` states that and is correct on both hierarchy
        # backends.
        lookup = {"slug": seed["slug"]}
        if parent_field_available:
            lookup["parent"] = None
        role, created = DeviceRole.objects.get_or_create(
            defaults=defaults,
            **lookup,
        )
        if created and uses_mptt:
            next_tree_id += 1
        roles_by_slug[seed["slug"]] = role

    settings = ProxboxPluginSettings.objects.filter(singleton_key="default").first()
    if settings is None:
        return

    update_fields = []
    if settings.default_role_qemu_id is None:
        settings.default_role_qemu = roles_by_slug["virtual-machine-qemu"]
        update_fields.append("default_role_qemu")
    if settings.default_role_lxc_id is None:
        settings.default_role_lxc = roles_by_slug["container-lxc"]
        update_fields.append("default_role_lxc")
    if update_fields:
        settings.save(update_fields=update_fields)


LAST_SYNCED_ROLE_CF = "proxmox_last_synced_role_id"


def register_last_synced_role_cf(apps, schema_editor):
    """Register the internal proxmox_last_synced_role_id custom field on VM."""
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")

    vm_ct, _ = ContentType.objects.get_or_create(
        app_label="virtualization", model="virtualmachine"
    )

    cf, _created = CustomField.objects.get_or_create(
        name=LAST_SYNCED_ROLE_CF,
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
    CustomField.objects.filter(name=LAST_SYNCED_ROLE_CF).delete()


HARDWARE_DEVICE_FIELDS = (
    (
        "hardware_chassis_serial",
        "text",
        "Chassis serial",
        "Chassis serial number reported by dmidecode -t 3 during SSH-based "
        "hardware discovery. Populated automatically by Proxbox when enabled.",
    ),
    (
        "hardware_chassis_manufacturer",
        "text",
        "Chassis manufacturer",
        "Chassis manufacturer string reported by dmidecode -t 1 during "
        "SSH-based hardware discovery.",
    ),
    (
        "hardware_chassis_product",
        "text",
        "Chassis product name",
        "Chassis product / model name reported by dmidecode -t 1 during "
        "SSH-based hardware discovery.",
    ),
)

HARDWARE_INTERFACE_FIELDS = (
    (
        "nic_speed_gbps",
        "integer",
        "NIC speed (Gbps)",
        "Negotiated NIC link speed in Gbps, parsed from ethtool output during "
        "SSH-based hardware discovery.",
    ),
    (
        "nic_duplex",
        "text",
        "NIC duplex",
        "Negotiated NIC duplex mode (full/half/unknown), parsed from ethtool "
        "output during SSH-based hardware discovery.",
    ),
    (
        "nic_link",
        "boolean",
        "NIC link up",
        "Whether the NIC reports link up, parsed from ethtool output during "
        "SSH-based hardware discovery.",
    ),
)


def _ensure_hardware_cf(CustomField, ContentType, name, type_, label, description, app_label, model):
    ct, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
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
    """Register the six hardware-discovery custom fields on Device/Interface."""
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    for name, type_, label, description in HARDWARE_DEVICE_FIELDS:
        _ensure_hardware_cf(CustomField, ContentType, name, type_, label, description, "dcim", "device")
    for name, type_, label, description in HARDWARE_INTERFACE_FIELDS:
        _ensure_hardware_cf(CustomField, ContentType, name, type_, label, description, "dcim", "interface")


def unregister_hardware_discovery_cfs(apps, schema_editor):
    CustomField = apps.get_model("extras", "CustomField")
    names = [n for n, _, _, _ in HARDWARE_DEVICE_FIELDS + HARDWARE_INTERFACE_FIELDS]
    CustomField.objects.filter(name__in=names).delete()
