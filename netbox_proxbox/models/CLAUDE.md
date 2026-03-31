# `netbox_proxbox.models`

This directory defines the plugin's persisted data model.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports all plugin model classes and shared model helpers.
- [`base.py`](./base.py): shared endpoint base classes and common validators/properties.
- [`proxmox_endpoint.py`](./proxmox_endpoint.py): Proxmox endpoint model.
- [`netbox_endpoint.py`](./netbox_endpoint.py): remote NetBox endpoint model.
- [`fastapi_endpoint.py`](./fastapi_endpoint.py): ProxBox backend endpoint model.
- [`plugin_settings.py`](./plugin_settings.py): singleton plugin settings model.
- [`storage.py`](./storage.py): `ProxmoxStorage` model and relations.
- [`vm_backup.py`](./vm_backup.py): `VMBackup` model.
- [`vm_snapshot.py`](./vm_snapshot.py): `VMSnapshot` model.
- [`vm_task_history.py`](./vm_task_history.py): `VMTaskHistory` model.

## Main Models

- `EndpointBase`: shared endpoint identity and URL-building fields.
- `ProxmoxEndpoint`: stores Proxmox API connection settings, credentials, mode, and version metadata.
- `NetBoxEndpoint`: stores the remote NetBox API target and either v1 token or v2 key/secret credentials.
- `FastAPIEndpoint`: stores the ProxBox backend HTTP/WebSocket target and optional backend token.
- `ProxmoxStorage`: stores Proxmox storage inventory synchronized from backend.
- `VMBackup`: stores backup inventory for NetBox virtual machines.
- `VMSnapshot`: stores snapshot inventory for NetBox virtual machines.
- `VMTaskHistory`: stores VM task history records linked to NetBox virtual machines.
- `ProxboxPluginSettings`: singleton settings for plugin runtime behavior.

## Dependencies

- Inbound: forms, tables, filtersets, views, serializers, and migrations all rely on these model definitions.
- Outbound: NetBox core model base classes plus related objects in `ipam`, `users`, and `virtualization`.

## Notes

- `CommonProperties` and `EndpointBase` centralize endpoint URL semantics.
- `FastAPIEndpoint.websocket_url` is distinct from the backend HTTP URL and is used by `websocket_client.py`.
- `NetBoxEndpoint.has_configured_token` and serializer/form validation together define the remote NetBox credential behavior.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
