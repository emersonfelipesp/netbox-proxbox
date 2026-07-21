"""Record the last-synced Proxmox VM name on the VM sync-state sidecar.

netbox-proxbox issue #617: a VM renamed in Proxmox never had that rename written
back to NetBox. proxbox-api's `resolve_unique_vm_name()` treats any mismatch
between the stored NetBox name and the incoming Proxmox name as "an operator
renamed this inside NetBox" and pushes the stale name back onto the sync payload.

That heuristic cannot be correct, because the two situations are
indistinguishable from its inputs -- both are simply "stored name != incoming
name". Persisting the name Proxmox last reported gives the resolver a third data
point and separates them:

    stored NetBox name != proxmox_vm_name         -> edited in NetBox -> preserve
    stored NetBox name == proxmox_vm_name != new  -> renamed in Proxmox -> update

Additive and back-compatible: the column starts blank on every existing row, and
proxbox-api must fall back to the previous behaviour whenever it is blank, so
nothing regresses mid-rollout. Rows become authoritative as they are re-synced.
"""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    # Depends on 0071_settings_custom_fields_enabled, not 0070 directly: that
    # sibling 0071 also branched off 0070, so pointing this migration at 0070
    # too left the graph with two leaf nodes at 0071 ("multiple leaf nodes in
    # the migration graph"), which breaks `manage.py migrate` on every NetBox
    # start. Chaining after it makes the history linear (0070 -> 0071_settings
    # -> 0072_sync_state).
    dependencies = [
        ("netbox_proxbox", "0071_settings_custom_fields_enabled"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxvirtualmachinesyncstate",
            field_name="proxmox_vm_name",
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text=(
                    "Name this VM had in Proxmox as of the last successful sync. "
                    "Lets a Proxmox-side rename be told apart from an operator "
                    "renaming the VM inside NetBox. Blank means not yet recorded."
                ),
            ),
        ),
    ]
