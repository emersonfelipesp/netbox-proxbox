"""Seed the two default VM DeviceRole rows and assign them to the plugin singleton.

Idempotent: existing DeviceRoles with the well-known slugs are reused; the
ProxboxPluginSettings singleton's default_role_qemu / default_role_lxc fields
are only populated when they are currently NULL.

DeviceRole is MPTT-tracked (level/lft/rght/tree_id are NOT NULL). Historical
models returned by ``apps.get_model`` do not carry the custom TreeManager that
fills these on save, so the values are set explicitly here. The seeded rows
are roots with no children: level=0, lft=1, rght=2, and a tree_id picked
above the current MAX(tree_id) so each row owns its own tree.
"""

from django.db import migrations
from django.db.models import Max


VM_ROLE_SEEDS = (
    {
        "slug": "virtual-machine-qemu",
        "name": "Virtual Machine (QEMU)",
        "color": "9c27b0",
    },
    {
        "slug": "container-lxc",
        "name": "Container (LXC)",
        "color": "00bcd4",
    },
)


def seed_default_vm_roles(apps, schema_editor):
    DeviceRole = apps.get_model("dcim", "DeviceRole")
    ProxboxPluginSettings = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")

    next_tree_id = (DeviceRole.objects.aggregate(Max("tree_id"))["tree_id__max"] or 0) + 1

    roles_by_slug = {}
    for seed in VM_ROLE_SEEDS:
        role, created = DeviceRole.objects.get_or_create(
            slug=seed["slug"],
            defaults={
                "name": seed["name"],
                "color": seed["color"],
                "vm_role": True,
                "level": 0,
                "lft": 1,
                "rght": 2,
                "tree_id": next_tree_id,
            },
        )
        if created:
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


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0044_default_role_fk_fields"),
        ("dcim", "0227_alter_interface_speed_bigint"),
    ]

    operations = [
        migrations.RunPython(seed_default_vm_roles, reverse_code=migrations.RunPython.noop),
    ]
