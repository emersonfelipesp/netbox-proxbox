# `netbox_proxbox.api`

This directory contains the NetBox plugin API surface for ProxBox. It exposes the API root, the nested plugin endpoint namespace, and model-backed viewsets and serializers for the plugin's persisted objects.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`urls.py`](./urls.py): API routing for the plugin root, endpoint namespace, and model viewsets.
- [`views.py`](./views.py): `APIRootView` subclasses and `NetBoxModelViewSet` classes for `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, `BackupRoutine`, and `Replication`.
- [`filters.py`](./filters.py): additional filter utilities used by the API router if needed.
- [`serializers/`](./serializers): package of API serializers for endpoints, clusters, storage, backups, snapshots, task history, backup routines, and replications, including write-only secret fields and v1/v2 NetBox token rules.

## Dependencies

- Inbound: the NetBox plugin API router imports this package to expose `/api/plugins/proxbox/...`.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.filtersets`, NetBox serializer/viewset base classes, nested serializers from `ipam`, `dcim`, and `virtualization`, and `users.Token`.

## Notes

- `NetBoxEndpointSerializer` is the main place where v1 versus v2 remote NetBox credential rules are enforced for API writes.
- `ProxmoxEndpointSerializer` marks password and token value fields write-only.
- The root view adds a convenience `endpoints` URL into the API response.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
