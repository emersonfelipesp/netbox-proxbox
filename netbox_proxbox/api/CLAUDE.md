# `netbox_proxbox.api`

This directory contains the NetBox plugin API surface for ProxBox. It exposes the API root, the nested plugin endpoint namespace, model-backed viewsets and serializers for the plugin's persisted objects, and non-model `APIView` classes that mirror every data-bearing UI page.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`urls.py`](./urls.py): API routing for the plugin root, endpoint namespace, non-model views, and model viewsets.
- [`views.py`](./views.py): `APIRootView` subclasses, `NetBoxModelViewSet` classes, and non-model `APIView` classes (see table below).
- [`filters.py`](./filters.py): additional filter utilities used by the API router if needed.
- [`serializers/`](./serializers): package of API serializers for endpoints, clusters, storage, backups, snapshots, task history, backup routines, replications, and the non-model resource/schedule serializers in `resource_views.py`.

## Model Viewsets

These follow the standard `NetBoxModelViewSet` + `NetBoxRouter` pattern:

| Viewset | Route |
|---|---|
| `ProxmoxEndpointViewSet` | `endpoints/proxmox/` |
| `NetBoxEndpointViewSet` | `endpoints/netbox/` |
| `FastAPIEndpointViewSet` | `endpoints/fastapi/` |
| `ProxmoxClusterViewSet` | `clusters/` |
| `ProxmoxNodeViewSet` | `nodes/` |
| `ProxmoxStorageViewSet` | `storage/` |
| `VMBackupViewSet` | `backups/` |
| `BackupRoutineViewSet` | `backup-routines/` |
| `ReplicationViewSet` | `replications/` |
| `VMSnapshotViewSet` | `snapshots/` |
| `VMTaskHistoryViewSet` | `task-history/` |
| `ProxboxPluginSettingsViewSet` | `settings/` |

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
- `ProxmoxEndpointSerializer` marks password and token value fields write-only.
- Resource views use `get_proxbox_tagged_object_ids()` from `netbox_proxbox/utils.py` to look up objects tagged `proxbox` without repeating the `TaggedItem` query pattern.
- `DashboardAPIView` makes live HTTP calls to the proxbox-api backend to fetch current cluster/VM statistics; it returns partial data (with error context) when the backend is unreachable rather than failing the entire request.
- Contract tests for this API layer live in `tests/test_api_source_contracts.py`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
