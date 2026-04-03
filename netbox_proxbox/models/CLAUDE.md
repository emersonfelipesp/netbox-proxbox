# `netbox_proxbox.models`

This directory defines the plugin's persisted data model.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports all plugin model classes and shared model helpers.
- [`base.py`](./base.py): shared endpoint base classes and common validators/properties.
- [`proxmox_endpoint.py`](./proxmox_endpoint.py): Proxmox endpoint model.
- [`netbox_endpoint.py`](./netbox_endpoint.py): remote NetBox endpoint model.
- [`fastapi_endpoint.py`](./fastapi_endpoint.py): ProxBox backend endpoint model.
- [`proxmox_cluster.py`](./proxmox_cluster.py): discovered Proxmox cluster model linked to endpoint and NetBox cluster data.
- [`proxmox_node.py`](./proxmox_node.py): discovered Proxmox node model linked to endpoint and NetBox device data.
- [`plugin_settings.py`](./plugin_settings.py): singleton plugin settings model.
- [`storage.py`](./storage.py): `ProxmoxStorage` model and `ProxmoxStorageVirtualDisk` relation model.
- [`backup_routine.py`](./backup_routine.py): backup routine inventory model.
- [`replication.py`](./replication.py): replication inventory model.
- [`vm_backup.py`](./vm_backup.py): `VMBackup` model.
- [`vm_snapshot.py`](./vm_snapshot.py): `VMSnapshot` model.
- [`vm_task_history.py`](./vm_task_history.py): `VMTaskHistory` model.

## Main Models

- `EndpointBase`: shared endpoint identity and URL-building fields.
- `ProxmoxEndpoint`: stores Proxmox API connection settings, credentials, mode, and version metadata.
- `NetBoxEndpoint`: stores the remote NetBox API target and either v1 token or v2 key/secret credentials.
- `FastAPIEndpoint`: stores the ProxBox backend HTTP/WebSocket target and optional backend token.
- `ProxmoxCluster`: stores synchronized cluster metadata and relationships to the source endpoint and NetBox cluster.
- `ProxmoxNode`: stores synchronized hypervisor nodes and their relationships to the source endpoint and NetBox device.
- `ProxmoxStorage`: stores Proxmox storage inventory synchronized from the backend.
- `ProxmoxStorageVirtualDisk`: links storage rows to virtual disks.
- `BackupRoutine`: stores backup routine inventory for NetBox-backed ProxBox sync.
- `Replication`: stores replication job inventory for NetBox-backed ProxBox sync.
- `VMBackup`: stores backup inventory for NetBox virtual machines.
- `VMSnapshot`: stores snapshot inventory for NetBox virtual machines.
- `VMTaskHistory`: stores VM task history records linked to NetBox virtual machines.
- `ProxboxPluginSettings`: singleton settings for plugin runtime behavior.

## Dependencies

- Inbound: forms, tables, filtersets, views, serializers, and migrations all rely on these model definitions.
- Outbound: NetBox core model base classes plus related objects in `dcim`, `ipam`, `users`, and `virtualization`.

## Notes

- `CommonProperties` and `EndpointBase` centralize endpoint URL semantics.
- `FastAPIEndpoint.websocket_url` is distinct from the backend HTTP URL and is used by `websocket_client.py`.
- `NetBoxEndpoint.has_configured_token` and serializer/form validation together define the remote NetBox credential behavior.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
