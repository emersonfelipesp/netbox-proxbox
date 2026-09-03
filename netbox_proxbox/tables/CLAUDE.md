# `netbox_proxbox.tables`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

This directory defines `django_tables2` and NetBox tables for plugin list and tabular views.

## Files And Ownership

- [`__init__.py`](./__init__.py): tables for Proxmox, NetBox, and FastAPI endpoints plus exports for cluster, storage, backup routine, replication, backup, snapshot, and task-history tables.
- [`cluster.py`](./cluster.py): `ProxmoxClusterTable` and `ProxmoxNodeTable` used by cluster summary and endpoint tabs.
- [`storage.py`](./storage.py): table for `ProxmoxStorage`.
- [`backup_routine.py`](./backup_routine.py): table for `BackupRoutine`.
- [`replication.py`](./replication.py): table for `Replication`.
- [`vm_backup.py`](./vm_backup.py): table for `VMBackup`.
- [`vm_snapshot.py`](./vm_snapshot.py): table for `VMSnapshot`.
- [`vm_task_history.py`](./vm_task_history.py): table for `VMTaskHistory`.
- [`vm_intent.py`](./vm_intent.py): table for operator-owned `ProxmoxVMIntent` rows.

## Dependencies

- Inbound: list views and VM detail tabs use these table classes.
- Outbound: `netbox_proxbox.models`, NetBox table base classes, and `django_tables2`.

## Notes

- Default columns here shape the primary NetBox list views for the plugin.
- `ProxmoxEndpointTable` must include `enabled` in `Meta.default_columns` so operators can see endpoint participation state on `/plugins/proxbox/endpoints/proxmox/` without table customization.
- Endpoint/SSH credential tables expose only a secret-free
  `credential_state` column. Never use decrypted virtual properties such as
  `FastAPIEndpoint.token` as table accessors; corrupt/wrong-key ciphertext must
  render `Recovery required` instead of raising or exposing values.
- `ProxmoxMetricsInfluxDBTable` must resolve `influx_url` through the model's
  fail-closed `influx_url_display` property in both `render_influx_url()` and
  `value_influx_url()`, keeping malformed or credential-bearing legacy values
  out of list-page HTML and CSV/export output.
- Table changes often imply matching updates to filter forms, list views, and sometimes templates.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
