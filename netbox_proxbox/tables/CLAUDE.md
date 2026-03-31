# `netbox_proxbox.tables`

This directory defines `django_tables2`/NetBox tables for plugin list and tabular views.

## Files And Ownership

- [`__init__.py`](./__init__.py): tables for endpoint models plus exports for storage/backup/
  snapshot/task-history tables.
- [`storage.py`](./storage.py): table for `ProxmoxStorage`.
- [`vm_backup.py`](./vm_backup.py): table for `VMBackup`.
- [`vm_snapshot.py`](./vm_snapshot.py): table for `VMSnapshot`.
- [`vm_task_history.py`](./vm_task_history.py): table for `VMTaskHistory`.

## Dependencies

- Inbound: list views and VM detail tabs use these table classes.
- Outbound: `netbox_proxbox.models`, NetBox table base classes, and `django_tables2`.

## Notes

- Default columns here shape the primary NetBox list views for the plugin.
- Table changes often imply matching updates to filter forms, list views, and sometimes templates.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
