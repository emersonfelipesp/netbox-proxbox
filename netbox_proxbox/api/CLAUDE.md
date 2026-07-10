# `netbox_proxbox.api`

This directory contains the NetBox plugin API surface for ProxBox. It exposes the API root, the nested plugin endpoint namespace, model-backed viewsets and serializers for the plugin's persisted objects, and non-model `APIView` classes that mirror every data-bearing UI page.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`urls.py`](./urls.py): API routing for the plugin root, endpoint namespace, non-model views, and model viewsets.
- [`views.py`](./views.py): `APIRootView` subclasses, `NetBoxModelViewSet` classes, and non-model `APIView` classes (see table below).
- [`filters.py`](./filters.py): additional filter utilities used by the API router if needed.
- [`serializers/`](./serializers): package of API serializers for endpoints, clusters, storage, backups, snapshots, task history, backup routines, replications, and the non-model resource/schedule serializers in `resource_views.py`. The `pbs_pdm.py` module provides serializers for `PBSEndpoint`, `PDMEndpoint`, and `PDMRemote`; `intent.py` provides read-only serializers for `DeletionRequest` and `ProxmoxApplyJob`.

## Model Viewsets

These follow the standard `NetBoxModelViewSet` + `NetBoxRouter` pattern:

### Endpoint namespace (`endpoints/`)

| Viewset | Route | Notes |
|---|---|---|
| `ProxmoxEndpointViewSet` | `endpoints/proxmox/` | Full CRUD |
| `NetBoxEndpointViewSet` | `endpoints/netbox/` | Full CRUD |
| `FastAPIEndpointViewSet` | `endpoints/fastapi/` | Full CRUD |
| `PBSEndpointViewSet` | `endpoints/pbs/` | Full CRUD; `token_secret` write-only |
| `PDMEndpointViewSet` | `endpoints/pdm/` | Full CRUD; `token_secret` write-only; M2M proxmox/pbs endpoints |

### Main router

| Viewset | Route | Notes |
|---|---|---|
| `ProxmoxClusterViewSet` | `proxmox-clusters/` | Full CRUD |
| `ProxmoxNodeViewSet` | `proxmox-nodes/` | Full CRUD |
| `CloudImageTemplateViewSet` | `cloud-image-templates/` | Full CRUD |
| `FirecrackerHostPoolViewSet` | `firecracker-host-pools/` | Full CRUD |
| `FirecrackerHostViewSet` | `firecracker-hosts/` | Full CRUD |
| `FirecrackerImageTemplateViewSet` | `firecracker-image-templates/` | Full CRUD |
| `FirecrackerMicroVMViewSet` | `firecracker-microvms/` | Full CRUD |
| `ProxmoxStorageViewSet` | `storage/` | Full CRUD |
| `VMBackupViewSet` | `backups/` | Full CRUD |
| `BackupRoutineViewSet` | `backup-routines/` | Full CRUD |
| `ReplicationViewSet` | `replications/` | Full CRUD |
| `VMSnapshotViewSet` | `snapshots/` | Full CRUD |
| `VMTaskHistoryViewSet` | `task-history/` | Full CRUD |
| `ProxmoxServiceCollectionViewSet` | `service-collections/` | GET/HEAD/OPTIONS only — async netbox-rpc collection history |
| `ProxmoxServiceSampleViewSet` | `service-samples/` | GET/HEAD/OPTIONS only — raw projected systemd rows |
| `ProxmoxServiceStatusViewSet` | `service-statuses/` | GET/HEAD/OPTIONS only — latest projected service state |
| `ProxmoxVMCloudInitViewSet` | `vm-cloudinit/` | Full CRUD |
| `ProxmoxVMTemplateViewSet` | `vm-templates/` | Full CRUD |
| `ProxboxPluginSettingsViewSet` | `settings/` | GET+PATCH only (singleton) |
| `NodeSSHCredentialViewSet` | `ssh-credentials/` | Full CRUD |
| `ProxmoxFirewallSecurityGroupViewSet` | `firewall/security-groups/` | Full CRUD |
| `ProxmoxFirewallRuleViewSet` | `firewall/rules/` | Full CRUD |
| `ProxmoxFirewallIPSetViewSet` | `firewall/ipsets/` | Full CRUD |
| `ProxmoxFirewallIPSetEntryViewSet` | `firewall/ipset-entries/` | Full CRUD |
| `ProxmoxFirewallAliasViewSet` | `firewall/aliases/` | Full CRUD |
| `ProxmoxFirewallOptionsViewSet` | `firewall/options/` | Full CRUD |
| `ProxmoxSdnFabricViewSet` | `sdn-fabrics/` | Full CRUD |
| `ProxmoxSdnRouteMapViewSet` | `sdn-route-maps/` | Full CRUD |
| `ProxmoxSdnPrefixListViewSet` | `sdn-prefix-lists/` | Full CRUD |
| `ProxmoxDatacenterCpuModelViewSet` | `datacenter-cpu-models/` | Full CRUD |
| `PDMRemoteViewSet` | `pdm-remotes/` | Full CRUD; FK to PDMEndpoint |
| `DeletionRequestViewSet` | `deletion-requests/` | **GET/HEAD/OPTIONS only** — write paths go through UI approval workflow |
| `ProxmoxApplyJobViewSet` | `apply-jobs/` | **GET/HEAD/OPTIONS only** — jobs created by intent branch-merge workflow |

Firecracker host-pool and image-template serializers expose `allowed_tenants` as
the NMS Cloud tenant visibility contract. Omitting `allowed_tenants` on create or
partial update leaves existing grants untouched; sending an explicit list,
including `[]`, replaces the many-to-many set. Keep
`FirecrackerHostPoolSerializer` and `FirecrackerImageTemplateSerializer`
`create()` / `update()` methods explicitly typed and covered by
`tests/test_firecracker_cloud_contracts.py` when changing this behavior.

## Non-Model API Views

These `APIView` subclasses mirror every data-bearing UI page and expose the same aggregated data as JSON. All are GET-only except `ScheduleSyncAPIView` which also accepts POST.

| View class | Route | Mirrors UI page | Permission |
|---|---|---|---|
| `HomeAPIView` | `home/` | `/plugins/proxbox/` | `_ProxboxDashboardPermission` |
| `DashboardAPIView` | `dashboard/` | `/plugins/proxbox/dashboard/` | `_ProxboxDashboardPermission` |
| `NodesAPIView` | `resources/nodes/` | `/plugins/proxbox/nodes/` | `IsAuthenticatedOrLoginNotRequired` |
| `VirtualMachinesAPIView` | `resources/virtual-machines/` | `/plugins/proxbox/virtual_machines/` | `IsAuthenticatedOrLoginNotRequired` |
| `LXCContainersAPIView` | `resources/lxc-containers/` | `/plugins/proxbox/lxc_containers/` | `IsAuthenticatedOrLoginNotRequired` |
| `InterfacesAPIView` | `resources/interfaces/` | `/plugins/proxbox/interfaces/` | `IsAuthenticatedOrLoginNotRequired` |
| `IPAddressesAPIView` | `resources/ip-addresses/` | `/plugins/proxbox/ip-addresses/` | `IsAuthenticatedOrLoginNotRequired` |
| `VirtualDisksAPIView` | `resources/virtual-disks/` | `/plugins/proxbox/virtual-disks/` | `IsAuthenticatedOrLoginNotRequired` |
| `ScheduleSyncAPIView` | `sync/schedule/` | `/plugins/proxbox/sync/schedule/` | `IsAuthenticatedOrLoginNotRequired` + `core.add_job` check |
| `BackendLogsAPIView` | `logs/` | `/plugins/proxbox/logs/` | `IsAuthenticatedOrLoginNotRequired` |
| `ProxmoxServiceMonitoringRefreshAPIView` | `endpoints/proxmox/{id}/services/refresh/` | Proxmox endpoint Services tab refresh | `IsAuthenticated` + `change_proxmoxendpoint` + endpoint service-monitoring eligibility |

### Permission notes

- `_ProxboxDashboardPermission` wraps `user_may_access_proxbox_dashboard()` and allows unauthenticated access only when `settings.LOGIN_REQUIRED` is `False`, matching the `ConditionalLoginRequiredMixin` UI behavior.
- `IsAuthenticatedOrLoginNotRequired` (from `netbox.api.authentication`) allows anonymous API access when `LOGIN_REQUIRED=False`, matching `ConditionalLoginRequiredMixin` on the UI side.
- `ScheduleSyncAPIView.get()` and `ScheduleSyncAPIView.post()` both invoke `_check_enqueue_permission()`, which verifies the caller holds `core.add_job` (same permission gate as the UI `ContentTypePermissionRequiredMixin`).

### Non-model serializers

`serializers/resource_views.py` holds lightweight `serializers.Serializer` subclasses used for OpenAPI documentation of these views:

- `DeviceResourceSerializer` — nodes list items
- `VirtualMachineResourceSerializer` — VM and LXC items
- `InterfaceResourceSerializer` — interface list items
- `IPAddressResourceSerializer` — IP address items
- `VirtualDiskResourceSerializer` — virtual disk items
- `ScheduledJobSerializer` — GET `/sync/schedule/` response rows
- `ScheduleSyncRequestSerializer` — POST `/sync/schedule/` input body

### API root

`ProxBoxRootView.get()` extends the DRF root response with keys for every non-model URL group: `home`, `dashboard`, `resources` (nested dict with all six sub-paths), `schedule_sync`, and `logs`.

## Dependencies

- Inbound: the NetBox plugin API router imports this package to expose `/api/plugins/proxbox/...`.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.filtersets`, `netbox_proxbox.utils.get_proxbox_tagged_object_ids`, NetBox serializer/viewset base classes, nested serializers from `ipam`, `dcim`, and `virtualization`, and `users.Token`.

## Notes

- `NetBoxEndpointSerializer` is the main place where v1 versus v2 remote NetBox credential rules are enforced for API writes.
- `ProxmoxEndpointSerializer` marks password and token value fields write-only
  and exposes `ssh_credential_source` for endpoint browser-terminal SSH
  configuration.
- `ProxmoxEndpointSSHCredentialSecretsAPIView` preserves the proxbox-api payload
  shape (`host`, `username`, `port`, `auth_method`, fingerprint, booleans,
  `password`, `private_key`). In `reuse_endpoint` mode it returns the
  realm-stripped endpoint username, `auth_method=password`, the endpoint
  plaintext password, and an empty private key without requiring the plugin
  encryption key. The dedicated mode still decrypts `ssh_*_enc` fields and
  returns `503` when the encryption key is missing. **Security:** `reuse_endpoint`
  means this endpoint returns the Proxmox API password, so the `open_ssh_terminal`
  permission (required alongside `view` here) effectively grants retrieval of that
  password — scope it to operators already trusted with the endpoint credentials.
  Token-only endpoints (no stored password) get `422` from this view.
- Proxmox endpoint service-monitoring fields are exposed on
  `ProxmoxEndpointSerializer`, but decrypted SSH material is not. The refresh
  API only queues an async `netbox-rpc` execution for the read-only
  `os.linux.proxmox.show_systemctl_services` procedure. It requires
  `change_proxmoxendpoint` and the same eligibility gate as the UI:
  `allow_writes=True`, `access_methods="api_ssh"`, and complete endpoint SSH
  credentials. `netbox-rpc` remains a soft optional dependency and must be
  imported only inside call-time `try/except ImportError` blocks.
- `NodeHostKeyFingerprintAPIView`
  (`GET ssh-credentials/by-node/<node_id>/host-key-fingerprint/`) backs the
  **"Fetch host key"** button in the **Terminal-tab credential modal** for
  **node** targets. Session-gated by `_ProxmoxEndpointOpenTerminalPermission`
  (`open_ssh_terminal`, the same permission that renders the tab). It resolves
  the node IP server-side, honors the modal `?port=` (default 22), enforces the
  owning endpoint's SSH access method (403 when `access_methods='api'`), and
  proxies to proxbox-api `GET /ssh/host-key-fingerprint`. No credential is sent
  or returned (public host key only); degrades gracefully (no host → 422, no
  backend → 503, old proxbox-api without the route → 503, upstream error → 502).
  The operator reviews/accepts the fingerprint before it is pinned for a
  one-shot session or persisted on a stored `NodeSSHCredential`.
- `ProxmoxEndpointHostKeyFingerprintAPIView`
  (`GET ssh-credentials/by-endpoint/<id>/host-key-fingerprint/`) backs the
  **"Fetch host key"** button on the SSH-settings tab (and the endpoint-target
  Terminal-tab modal). It is **session-gated**
  (`_ProxmoxEndpointChangePermission` → `change_proxmoxendpoint`), resolves the
  endpoint host (`ssh_host`) + `ssh_port` server-side, and proxies to proxbox-api
  `GET /ssh/host-key-fingerprint` (via `get_fastapi_request_context`, X-Proxbox-API-Key),
  returning `{host, port, fingerprint, key_type}` to auto-fill the pinned
  `ssh_known_host_fingerprint` for operator review. No credential is sent or
  returned (public host key only). Degrades gracefully: no host → `422`,
  no backend → `503`, backend without the route (old proxbox-api) → `503`,
  unreachable/upstream error → `502`. The operator still confirms the pin before
  Save — no silent auto-trust.
- Resource views use `get_proxbox_tagged_object_ids()` from `netbox_proxbox/utils.py` to look up objects tagged `proxbox` without repeating the `TaggedItem` query pattern.
- `DashboardAPIView` makes live HTTP calls to the proxbox-api backend to fetch current cluster/VM statistics; it returns partial data (with error context) when the backend is unreachable rather than failing the entire request.
- Contract tests for this API layer live in `tests/test_api_source_contracts.py`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
