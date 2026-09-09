# Orphan VM review and purge

Proxbox can identify NetBox virtual machines and LXC containers that were
discovered previously but did not appear in a later full synchronization. The
workflow is intentionally two-phase:

1. Enable **Mark orphan VMs for deletion** in **Plugins → Proxbox → Plugin
   Settings**, or set `PROXBOX_DELETE_ORPHANS=true` for proxbox-api. The backend
   marks each stale QEMU/LXC record with the `proxbox-soft-deleted` tag and the
   `decommissioning` status. It preserves existing tags and never deletes the
   NetBox record.
2. Review the dry-run stream at
   `/full-update/stream?dry_run=true` before enabling the setting.
3. Open **Plugins → Proxbox → Soft-deleted VMs**. The page is available only to
   users with NetBox delete permission on virtual machines.
4. Select individual rows, or select all records matching the page query, and
   submit the delete action. NetBox displays a confirmation page before the
   records are permanently removed from NetBox.

The purge page is restricted server-side to records carrying the marker tag
and `decommissioning` status. This restriction applies to selected primary
keys and to the “all matching” operation, so a submitted ID cannot expand the
operation to an ordinary VM. The page deletes NetBox inventory only; it does
not call Proxmox or delete a Proxmox guest.

If a deleted Proxmox guest is recreated or returns to inventory before the
human purge, the next successful VM synchronization clears the marker and
restores the record to its normal synchronized state while preserving unrelated
operator tags.
