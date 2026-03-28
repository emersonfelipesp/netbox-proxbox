# `netbox_proxbox.forms`

This directory contains Django/NetBox forms for plugin models and the filter forms used by list views.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports all concrete form classes.
- [`proxmox.py`](./proxmox.py): create/edit and filter forms for `ProxmoxEndpoint`.
- [`netbox.py`](./netbox.py): create/edit and filter forms for `NetBoxEndpoint`, including local validation for token version selection.
- [`fastapi.py`](./fastapi.py): create/edit and filter forms for `FastAPIEndpoint`, including WebSocket and backend token fields.
- [`sync_process.py`](./sync_process.py): create/edit and filter forms for `SyncProcess`.
- [`vm_backup.py`](./vm_backup.py): create/edit and filter forms for `VMBackup`.

## Dependencies

- Inbound: view classes in `views/` import these forms for object edit and list pages.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.choices`, NetBox form base classes, and NetBox core models such as `IPAddress`, `Token`, and `VirtualMachine`.

## Notes

- `NetBoxEndpointForm.clean()` mirrors the API serializer's credential validation and clears unused token fields depending on token version.
- Endpoint forms use `DynamicModelChoiceField` for NetBox-managed related objects.
- These forms define how plugin fields are presented in the NetBox UI; model constraints still remain the source of truth for persistence.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
