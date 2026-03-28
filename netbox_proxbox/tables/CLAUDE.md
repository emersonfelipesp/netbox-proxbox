# `netbox_proxbox.tables`

This directory defines `django_tables2`/NetBox tables for plugin list and tabular views.

## Files And Ownership

- [`__init__.py`](./__init__.py): tables for `SyncProcess`, `ProxmoxEndpoint`, `NetBoxEndpoint`, and `FastAPIEndpoint`.
- [`vm_backup.py`](./vm_backup.py): table for `VMBackup`.

## Dependencies

- Inbound: list views and the `VMBackup` tab view use these table classes.
- Outbound: `netbox_proxbox.models`, NetBox table base classes, and `django_tables2`.

## Notes

- Default columns here shape the primary NetBox list views for the plugin.
- Table changes often imply matching updates to filter forms, list views, and sometimes templates.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
