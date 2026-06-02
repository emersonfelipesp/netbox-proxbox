# Reusing Existing NetBox Objects

By default, Proxbox is careful never to take over NetBox objects it did not
create. When a Proxmox node's hostname matches a `Device` that already exists
in NetBox **in a different site or cluster**, Proxbox does not touch that
device — it creates its own node device in the Proxmox default site instead.

This protects manually curated records (asset data, photos, patching history,
rack position) from being silently modified by sync.

## The problem this solves

A common scenario: you already documented your physical hypervisor in NetBox —
with real asset data — long before installing Proxbox. When you then sync the
Proxmox cluster, the existing device was left out of the cluster and the
node-level steps were skipped, leaving a duplicate device behind.

## Opting in with the `proxbox` tag

To let Proxbox **reuse and adopt** a pre-existing object instead of creating a
duplicate, assign the **`proxbox`** tag to it:

1. In NetBox, open the existing object (for example the hypervisor `Device`).
2. Add the **`proxbox`** tag (slug `proxbox`) to it and save.
3. Run a Proxbox sync.

On the next sync, a same-name device carrying the `proxbox` tag is adopted:

- It is **attached to the Proxmox cluster** so the node-level sync steps run.
- It is **kept in its own existing site**, so the unique-device-name-per-site
  constraint is respected and your manually curated data is preserved.
- No duplicate device is created.

Devices **without** the `proxbox` tag keep the safe default behavior and are
never silently adopted.

## Notes

- The `proxbox` tag is auto-created by the plugin (slug `proxbox`). If it does
  not yet exist in your NetBox, it is created on the first sync; you can also
  create it manually with the exact slug `proxbox`.
- This opt-in applies to the device/node reconciliation performed by the
  companion `proxbox-api` backend. Make sure both the plugin and backend are
  up to date.
- Per-field overwrite behavior on an adopted device still honors the
  [Sync Overwrite Flags](./sync-overwrite-flags.md) — for example, you can keep
  a custom `device_type` or `role` by disabling the matching flag.
