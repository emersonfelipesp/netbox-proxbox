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
- [`proxmox_metrics.py`](./proxmox_metrics.py): Proxmox cluster InfluxDB metrics endpoint metadata with `nms-secret:<uuid>` token references.
- [`plugin_settings.py`](./plugin_settings.py): singleton plugin settings model.
- [`storage.py`](./storage.py): `ProxmoxStorage` model and `ProxmoxStorageVirtualDisk` relation model.
- [`guest_vm_interface.py`](./guest_vm_interface.py): guest-agent OS interfaces and address links for dual VM interface sync.
- [`sync_state.py`](./sync_state.py): typed sidecar models for the legacy
  Proxbox custom-field payload, keyed one-to-one to NetBox core objects.
- [`backup_routine.py`](./backup_routine.py): backup routine inventory model.
- [`replication.py`](./replication.py): replication inventory model.
- [`vm_backup.py`](./vm_backup.py): `VMBackup` model.
- [`vm_snapshot.py`](./vm_snapshot.py): `VMSnapshot` model.
- [`vm_task_history.py`](./vm_task_history.py): `VMTaskHistory` model.

## Main Models

- `EndpointBase`: shared endpoint identity and URL-building fields.
- `ProxmoxEndpoint`: stores Proxmox API connection settings, credentials, mode, and version metadata. `effective_connection_tuning()` owns the nullable endpoint timeout/retry/back-off contract: endpoint values win when not `None` (including zero retries/back-off), otherwise the matching `ProxboxPluginSettings` value is returned, and all three outputs are concrete typed values. The model also carries `pushed_credential_fingerprint` (migration 0074) — the Proxmox twin of the `NetBoxEndpoint` field below, under a distinct HMAC salt so the two namespaces can never compare equal. It lets the preflight's soft push budget detect a secret rotated *in place* (invisible on the wire: `ProxmoxEndpointPublic` withholds `password`/`token_name`/`token_value`) and re-push instead of skipping. Unlike the NetBox twin it fails **toward pushing**: an empty or stale fingerprint costs one extra push, never a blocked run. Written by the push itself with `queryset.update()`, never `save()`, because the model's `post_save` handler re-pushes to the backend.
- `NetBoxEndpoint`: stores the remote NetBox API target and either v1 token or v2 key/secret credentials. Also carries `pushed_credential_fingerprint` (migration 0073) — a keyed HMAC-SHA256 digest of the credentials the last **successful** push handed proxbox-api. It is **not** a credential and must never be treated as one: `salted_hmac` keys the digest off NetBox's `SECRET_KEY`, so it is non-reversible and meaningless outside this install. It exists because `NetBoxEndpointResponse` withholds `token`/`token_key`, leaving an in-place token rotation invisible to any comparison against what the backend returns; the sync-job preflight reads it through `views/backend_sync.py::netbox_push_credentials_unchanged()`. Written by the push itself with `queryset.update()`, never `save()`, because the model's `post_save` handler re-pushes to the backend. An **empty** value means "credentials changed" (fail-closed), so nothing should back-fill it.
- `FastAPIEndpoint`: stores the ProxBox backend HTTP/WebSocket target and its
  encrypted backend token plus the credential-free
  `backend_key_target_fingerprint` that durably binds the token to the exact
  canonical HTTP/fallback-IP/WebSocket/TLS target. Disabled new rows may remain
  intentionally keyless.
- `PBSEndpoint`: stores Proxmox Backup Server connection settings and credentials for companion inventory/status paths.
- `PDMEndpoint`: stores Proxmox Datacenter Manager connection settings plus declared PVE/PBS federation links.
- `ProxmoxCluster`: stores synchronized cluster metadata and relationships to the source endpoint and NetBox cluster.
- `ProxmoxNode`: stores synchronized hypervisor nodes and their relationships to the source endpoint and NetBox device.
- `ProxmoxMetricsInfluxDB`: stores the InfluxDB URL, organization, bucket, TLS
  flag, enabled state, and query/writer token secret references for a Proxmox
  cluster. Token fields are `nms-secret:<uuid>` references to netbox-nms
  `ObservabilitySecret` objects, never plaintext credentials or encrypted token
  blobs in this plugin.
- `ProxmoxStorage`: stores Proxmox storage inventory synchronized from the backend.
- `ProxmoxStorageVirtualDisk`: links storage rows to virtual disks.
- `GuestVMInterface`: stores guest-agent OS interface names (for example `ens18`) for a NetBox `VirtualMachine`, mapped **one-to-one** (`OneToOneField`, `SET_NULL`) to the canonical core `VMInterface` (for example `net0`) by MAC. `SET_NULL` (not `CASCADE`) so deleting/recreating the core interface during churn preserves the guest OS inventory row and only clears the link; `vm_interface` is nullable for agent-only interfaces with no matching Proxmox NIC.
- `GuestVMInterfaceAddress`: links a guest OS interface to an existing core `ipam.IPAddress`; it never duplicates IP rows and protects referenced IPs from deletion. `clean()` enforces that the linked IP is the **same object** assigned to the mapped core `VMInterface` (or, for agent-only guests, at least on the same VM) so a bad ID/privileged user can never cross-link a foreign VM's IP.
- `ProxboxSyncStateBase`: abstract base for the custom-field migration
  sidecars. It stores the mirrored source timestamp in
  `proxmox_last_updated` and the backend run identifier in `last_run_id`;
  `last_updated` remains the inherited NetBox row timestamp for change
  tracking and API ETags where the NetBox platform supports them.
- `ProxboxVirtualMachineSyncState`, `ProxboxDeviceSyncState`,
  `ProxboxClusterSyncState`, `ProxboxIPAddressSyncState`,
  `ProxboxInterfaceSyncState`, `ProxboxVLANSyncState`,
  `ProxboxClusterGroupSyncState`, `ProxboxVirtualDiskSyncState`,
  `ProxboxVMInterfaceSyncState`, `ProxboxDeviceRoleSyncState`,
  `ProxboxDeviceTypeSyncState`, `ProxboxManufacturerSyncState`,
  `ProxboxSiteSyncState`, and `ProxboxClusterTypeSyncState`: additive typed
  mirrors for the 43 legacy custom fields proxbox-api currently writes across
  14 NetBox core object types. VM/device sidecars reuse existing
  `ProxmoxEndpoint`, `ProxmoxNode`, and `ProxmoxCluster` rows as nullable FKs,
  with text/raw fallback columns for unresolved legacy values. Legacy
  `proxmox_endpoint_id` is stored as `proxmox_endpoint_raw_id` and never
  treated as a plugin `ProxmoxEndpoint` primary key; legacy
  `proxmox_cluster_id` is stored as `proxmox_cluster_raw_id` to avoid
  colliding with the `proxmox_cluster` FK attname. Legacy virtual-disk storage
  and VM-interface bridge JSON values preserve unresolved numeric IDs in
  `proxbox_storage_raw_id` / `proxbox_bridge_raw_id` and malformed or
  non-numeric payloads in `proxbox_storage_raw_value` /
  `proxbox_bridge_raw_value`.
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
- `FastAPIEndpoint.save()` is the backend-key persistence boundary. New enabled
  endpoints, disabled-to-enabled transitions, connection/TLS target changes,
  and token changes must pass `prepare_backend_key_transition()` before
  `token_enc` is written. Each such transition requires an explicitly
  resubmitted candidate; no key is generated implicitly. A disabled existing
  row cannot accept a replacement token because the hard no-connection gate
  prevents authenticating it. Security-sensitive saves lock and compare the
  loaded ciphertext/target snapshot, while explicitly non-security
  `update_fields` saves cannot widen their field set or restore stale trust
  state. Runtime HTTP and WebSocket paths recompute
  `backend_key_target_fingerprint` (including a fresh IP FK lookup) before
  exposing the key; target drift remains blocked until explicit re-adoption.
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
  `ssh_access_enabled`, `has_ssh_terminal_credentials`, and
  `effective_rpc_enabled()` are all true (an RPC-disabled endpoint is excluded
  because each collection tick would 403 at the backend RPC gate). The
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
- Proxmox connection defaults are `proxmox_timeout=5`,
  `proxmox_max_retries=0`, and `proxmox_retry_backoff=0.50`. Keep operator docs,
  model defaults, and backend registration payloads aligned with those values.
- `ProxboxPluginSettings.vm_interface_sync_strategy` defaults to `guest_os_model`.
  This strategy keeps Proxmox config NICs as core `virtualization.VMInterface`
  rows named `net0`/`net1` and stores guest-agent names in `GuestVMInterface`.
  The `legacy_rename` strategy is retained only for the old single-interface
  rename behavior controlled by deprecated `use_guest_agent_interface_name`.
- `ProxboxClusterSyncState` is intentionally separate from `ProxmoxCluster`.
  `ProxmoxCluster` is endpoint-scoped and unique by `(endpoint, name)` with a
  nullable FK to `virtualization.Cluster`; it is not a one-to-one extension of
  NetBox's core cluster model. Keep custom-field backfill on the sidecar unless
  that cardinality changes.
- The typed sidecars are now the **standard** source of truth. Migrations
  0065/0066 created and backfilled them; the proxbox-api writer/reader switch has
  landed, so a normal sync writes and reads the sidecars and rebuilds them from
  live Proxmox data. The legacy reflection custom fields are **deprecated** and
  gated behind `ProxboxPluginSettings.custom_fields_enabled` (default `False`):
  by default proxbox-api does not write, read, or reconcile custom fields.
  Setting the flag `True` restores legacy custom-field behavior for a transition
  and emits deprecation warnings. Removing the custom fields entirely is a later
  cleanup; no custom-field data is deleted while the flag exists.
- Concurrency known limitation: on NetBox 4.5.x, sync-state sidecar REST APIs
  do not emit ETags and do not enforce `If-Match`, matching the platform
  behavior for all endpoints on that release. Optimistic concurrency is
  available on NetBox 4.6+. Automated writers should treat sidecar rows as
  proxbox-api-owned during the additive phase.
- Cloud-customer network discovery fields also live on `ProxboxPluginSettings`:
  `cloud_network_lock_enabled`, `cloud_customer_prefix_id`,
  `cloud_customer_bridge`, `cloud_customer_vlan_tag`, and
  `cloud_customer_gateway`. They are populated by the
  `ensure_cloud_customer_network` management command so proxbox-api and
  nms-backend discover the designated customer network from NetBox instead of
  hardcoded estate constants.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
