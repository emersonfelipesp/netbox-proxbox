# `netbox_proxbox.forms`

This directory contains Django/NetBox forms for plugin models, plugin settings, and the filter forms used by list views.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports all concrete form classes.
- [`proxmox.py`](./proxmox.py): create/edit and filter forms for `ProxmoxEndpoint`.
- [`netbox.py`](./netbox.py): create/edit and filter forms for `NetBoxEndpoint`, including local validation for token version selection.
- [`fastapi.py`](./fastapi.py): create/edit and filter forms for `FastAPIEndpoint`, including WebSocket and backend token fields.
- [`backup_routine.py`](./backup_routine.py): create/edit and filter forms for `BackupRoutine`.
- [`replication.py`](./replication.py): create/edit and filter forms for `Replication`.
- [`schedule_sync.py`](./schedule_sync.py): scheduling form for `ProxboxSyncJob` and quick-schedule defaults.
- [`settings.py`](./settings.py): plugin settings form (`ProxboxPluginSettings` singleton).
- [`storage.py`](./storage.py): create/edit and filter forms for `ProxmoxStorage`.
- [`vm_backup.py`](./vm_backup.py): create/edit and filter forms for `VMBackup`.
- [`vm_snapshot.py`](./vm_snapshot.py): create/edit and filter forms for `VMSnapshot`.
- [`vm_task_history.py`](./vm_task_history.py): create/edit and filter forms for `VMTaskHistory`.
- [`widgets.py`](./widgets.py): custom widgets used by forms, including bootstrap checkbox styles.

## Dependencies

- Inbound: view classes in `views/` import these forms for object edit and list pages.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.choices`, NetBox form base classes, and NetBox core models such as `IPAddress`, `Token`, and `VirtualMachine`.

## Notes

- `NetBoxEndpointForm.clean()` mirrors the API serializer's credential validation and clears unused token fields depending on token version.
- Endpoint forms use `DynamicModelChoiceField` for NetBox-managed related objects.
- These forms define how plugin fields are presented in the NetBox UI; model constraints and the API serializers still remain the source of truth for persistence and credential rules.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
