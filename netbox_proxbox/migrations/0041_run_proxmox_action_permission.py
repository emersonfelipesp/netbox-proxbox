"""Register the ``core.run_proxmox_action`` permission used by operational verbs.

Issue #376: operational verbs (start, stop, snapshot, migrate) are gated by a
single permission whose literal string is ``core.run_proxmox_action`` (pinned
by ``docs/design/operational-verbs.md``). To produce that exact string Django
needs an ``auth_permission`` row whose content type is in the ``core`` app —
a regular plugin-model ``Meta.permissions`` declaration would yield
``netbox_proxbox.run_proxmox_action`` instead.

The row is attached to ``core.ObjectType`` (the most neutral ``core`` content
type — not coupled to ``Job`` background semantics or ``ObjectChange`` audit
semantics). ``ContentTypePermissionRequiredMixin`` performs a literal
``user.has_perm("core.run_proxmox_action")`` lookup and does not care which
content type the row is attached to.
"""

from django.db import migrations


PERM_CODENAME = "run_proxmox_action"
PERM_NAME = "Can dispatch Proxmox operational verbs"
CT_APP_LABEL = "core"
CT_MODEL = "objecttype"


def _create_perm(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    ct = ContentType.objects.get(app_label=CT_APP_LABEL, model=CT_MODEL)
    Permission.objects.get_or_create(
        content_type=ct,
        codename=PERM_CODENAME,
        defaults={"name": PERM_NAME},
    )


def _delete_perm(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        content_type__app_label=CT_APP_LABEL,
        content_type__model=CT_MODEL,
        codename=PERM_CODENAME,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0040_proxmoxendpoint_allow_writes"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0018_concrete_objecttype"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(_create_perm, _delete_perm),
    ]
