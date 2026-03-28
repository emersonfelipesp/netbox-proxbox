# `netbox_proxbox.models`

This directory defines the plugin's persisted data model.

## Files And Ownership

- [`__init__.py`](./__init__.py): shared endpoint base classes plus the main endpoint and sync-process models.
- [`vm_backup.py`](./vm_backup.py): standalone `VMBackup` model tied to NetBox virtual machines.

## Main Models

- `EndpointBase`: shared endpoint identity and URL-building fields.
- `ProxmoxEndpoint`: stores Proxmox API connection settings, credentials, mode, and version metadata.
- `NetBoxEndpoint`: stores the remote NetBox API target and either v1 token or v2 key/secret credentials.
- `FastAPIEndpoint`: stores the ProxBox backend HTTP/WebSocket target and optional backend token.
- `SyncProcess`: records sync type, status, timing, and runtime metadata.
- `VMBackup`: stores backup inventory for NetBox virtual machines.

## Dependencies

- Inbound: forms, tables, filtersets, views, serializers, and migrations all rely on these model definitions.
- Outbound: NetBox core model base classes plus related objects in `ipam`, `users`, and `virtualization`.

## Notes

- `CommonProperties` and `EndpointBase` centralize endpoint URL semantics.
- `FastAPIEndpoint.websocket_url` is distinct from the backend HTTP URL and is used by `websocket_client.py`.
- `NetBoxEndpoint.has_configured_token` and serializer/form validation together define the remote NetBox credential behavior.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
