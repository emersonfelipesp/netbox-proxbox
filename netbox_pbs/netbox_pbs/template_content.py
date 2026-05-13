"""Cross-plugin template hooks for ``netbox_pbs``.

When ``netbox_proxbox`` is also installed, render a presentation-only
cross-link between :class:`netbox_proxbox.models.VMBackup` and
:class:`netbox_pbs.models.PBSSnapshot` rows that share a natural key:

* ``VMBackup.vmid``           == ``int(PBSSnapshot.backup_group.backup_id)``
* ``VMBackup.creation_time``  == ``PBSSnapshot.backup_time``
* ``PBSSnapshot.backup_group.backup_type`` == ``"vm"``

The integration is read-only (issue #325 v1 scope): no foreign key, no
schema change, no signal-backed backfill. If proxbox is not installed
the extensions are simply not registered.
"""

from __future__ import annotations

from django.apps import apps
from django.utils.safestring import mark_safe
from netbox.plugins import PluginTemplateExtension

__all__ = (
    "PBSSnapshotVMBackupExtension",
    "VMBackupPBSSnapshotExtension",
    "template_extensions",
)


def _match_pbs_snapshots(vmbackup):
    """Return PBSSnapshot rows whose natural key matches ``vmbackup``."""
    if vmbackup.vmid is None or vmbackup.creation_time is None:
        return []
    from netbox_pbs.models import PBSSnapshot

    return list(
        PBSSnapshot.objects.filter(
            backup_group__backup_type="vm",
            backup_group__backup_id=str(vmbackup.vmid),
            backup_time=vmbackup.creation_time,
        ).select_related("backup_group__datastore")
    )


def _match_vm_backups(snapshot):
    """Return VMBackup rows whose natural key matches ``snapshot``."""
    group = snapshot.backup_group
    if group.backup_type != "vm":
        return []
    try:
        vmid = int(group.backup_id)
    except (TypeError, ValueError):
        return []
    from netbox_proxbox.models import VMBackup  # noqa: PLC0415

    return list(
        VMBackup.objects.filter(
            vmid=vmid,
            creation_time=snapshot.backup_time,
        ).select_related("virtual_machine")
    )


class VMBackupPBSSnapshotExtension(PluginTemplateExtension):
    """List matching PBS snapshots on the ``VMBackup`` detail page."""

    models = ["netbox_proxbox.vmbackup"]

    def right_page(self) -> str:
        obj = self.context["object"]
        snapshots = _match_pbs_snapshots(obj)
        if not snapshots:
            return ""
        return mark_safe(  # nosec
            self.render(
                "netbox_pbs/inc/vmbackup_pbs_snapshots_panel.html",
                {"snapshots": snapshots, "vmbackup": obj},
            )
        )


class PBSSnapshotVMBackupExtension(PluginTemplateExtension):
    """List matching ``VMBackup`` rows on the PBS snapshot detail page."""

    models = ["netbox_pbs.pbssnapshot"]

    def right_page(self) -> str:
        obj = self.context["object"]
        backups = _match_vm_backups(obj)
        if not backups:
            return ""
        return mark_safe(  # nosec
            self.render(
                "netbox_pbs/inc/pbssnapshot_vm_backups_panel.html",
                {"backups": backups, "snapshot": obj},
            )
        )


if apps.is_installed("netbox_proxbox"):
    template_extensions = [
        VMBackupPBSSnapshotExtension,
        PBSSnapshotVMBackupExtension,
    ]
else:
    template_extensions = []
