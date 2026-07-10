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
- [`guest_vm_interface.py`](./guest_vm_interface.py): guest-agent OS interfaces and address links for dual VM interface sync.
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
- `PBSEndpoint`: stores Proxmox Backup Server connection settings and credentials for companion inventory/status paths.
- `PDMEndpoint`: stores Proxmox Datacenter Manager connection settings plus declared PVE/PBS federation links.
- `ProxmoxCluster`: stores synchronized cluster metadata and relationships to the source endpoint and NetBox cluster.
- `ProxmoxNode`: stores synchronized hypervisor nodes and their relationships to the source endpoint and NetBox device.
- `ProxmoxStorage`: stores Proxmox storage inventory synchronized from the backend.
- `ProxmoxStorageVirtualDisk`: links storage rows to virtual disks.
- `GuestVMInterface`: stores guest-agent OS interface names (for example `ens18`) for a NetBox `VirtualMachine`, mapped **one-to-one** (`OneToOneField`, `SET_NULL`) to the canonical core `VMInterface` (for example `net0`) by MAC. `SET_NULL` (not `CASCADE`) so deleting/recreating the core interface during churn preserves the guest OS inventory row and only clears the link; `vm_interface` is nullable for agent-only interfaces with no matching Proxmox NIC.
- `GuestVMInterfaceAddress`: links a guest OS interface to an existing core `ipam.IPAddress`; it never duplicates IP rows and protects referenced IPs from deletion. `clean()` enforces that the linked IP is the **same object** assigned to the mapped core `VMInterface` (or, for agent-only guests, at least on the same VM) so a bad ID/privileged user can never cross-link a foreign VM's IP.
- `BackupRoutine`: stores backup routine inventory for NetBox-backed ProxBox sync.
- `Replication`: stores replication job inventory for NetBox-backed ProxBox sync.
- `VMBackup`: stores backup inventory for NetBox virtual machines.
- `VMSnapshot`: stores snapshot inventory for NetBox virtual machines.
- `VMTaskHistory`: stores VM task history records linked to NetBox virtual machines.
- `ProxmoxServiceCollection`, `ProxmoxServiceSample`, and
  `ProxmoxServiceStatus`: store asynchronous netbox-rpc systemctl service
  collection history, raw per-run samples, and latest projected service state
  for opt-in Proxmox endpoint service monitoring. The systemd `id` property is
  stored as `service_id` to avoid colliding with the NetBox row primary key.
- `ProxboxPluginSettings`: singleton settings for plugin runtime behavior.

## Dependencies

- Inbound: forms, tables, filtersets, views, serializers, and migrations all rely on these model definitions.
- Outbound: NetBox core model base classes plus related objects in `dcim`, `ipam`, `users`, and `virtualization`.

## Notes

- `CommonProperties` and `EndpointBase` centralize endpoint URL semantics.
- `EndpointBase.enabled` is operational: `False` means inventory-only. Service, signal, startup, OpenAPI, and sync code must return before any backend or remote-service connection attempt for disabled endpoint-like rows.
- `FastAPIEndpoint.websocket_url` is distinct from the backend HTTP URL and is used by `websocket_client.py`.
- `NetBoxEndpoint.has_configured_token` and serializer/form validation together define the remote NetBox credential behavior.
- Primary endpoint secrets are exposed as compatibility properties and stored in
  encrypted backing fields: `ProxmoxEndpoint.password_enc`,
  `ProxmoxEndpoint.token_value_enc`, `FastAPIEndpoint.token_enc`,
  `PBSEndpoint.token_secret_enc`, and `PDMEndpoint.token_secret_enc`. Use the
  public properties (`password`, `token_value`, `token`, `token_secret`) in
  service code and serializers; never add plaintext model fields for these
  secrets.
- `ProxmoxEndpoint.ssh_credential_source` controls the proxbox-native endpoint
  SSH credential surface used by the browser terminal. The default
  `dedicated` mode keeps the encrypted `ssh_*_enc` behavior unchanged.
  `reuse_endpoint` mode derives `effective_ssh_username` from
  `username.split("@", 1)[0]` and treats the endpoint plaintext `password` as
  the SSH password; it still requires `ssh_host` and
  `ssh_known_host_fingerprint`.
- `ProxmoxEndpoint.service_monitoring_enabled` is gated by
  `service_monitoring_eligible`, which is true only when `allow_writes`,
  `ssh_access_enabled`, and `has_ssh_terminal_credentials` are all true. The
  collector creates asynchronous netbox-rpc executions; this plugin does not
  perform SSH itself.
- `ProxboxPluginSettings` is the singleton home for runtime tunables shared with the
  `proxbox-api` backend (timeouts, concurrency, batch sizes, cache limits, diagnostic
  flags). Add new tunables here rather than as fresh `PROXBOX_*` env vars on the
  backend; the backend reads them through `proxbox_api.runtime_settings.get_*` which
  resolves env > plugin settings > default. See
  [top-level `CLAUDE.md` → Plugin settings and configuration](../../CLAUDE.md) and
  migration [`0037_pluginsettings_runtime_tunables.py`](../migrations/0037_pluginsettings_runtime_tunables.py)
  for the migration shape (`SeparateDatabaseAndState` + `IF NOT EXISTS`).
- `ProxboxPluginSettings.vm_interface_sync_strategy` defaults to `guest_os_model`.
  This strategy keeps Proxmox config NICs as core `virtualization.VMInterface`
  rows named `net0`/`net1` and stores guest-agent names in `GuestVMInterface`.
  The `legacy_rename` strategy is retained only for the old single-interface
  rename behavior controlled by deprecated `use_guest_agent_interface_name`.
- Cloud-customer network discovery fields also live on `ProxboxPluginSettings`:
  `cloud_network_lock_enabled`, `cloud_customer_prefix_id`,
  `cloud_customer_bridge`, `cloud_customer_vlan_tag`, and
  `cloud_customer_gateway`. They are populated by the
  `ensure_cloud_customer_network` management command so proxbox-api and
  nms-backend discover the designated customer network from NetBox instead of
  hardcoded estate constants.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
