# netbox-ceph

`netbox-ceph` is a sibling NetBox plugin for `netbox-proxbox`.

Version 0.0.1 is intentionally read-only. It mirrors Proxmox-managed Ceph
inventory through `proxbox-api` and reuses `netbox-proxbox` backend context,
branch lifecycle, endpoint relationships, and job conventions.

Out of scope for v1: direct Ceph Dashboard API integration, Prometheus metric
ingestion, RGW/S3 bucket inventory, RBD image inventory, external non-Proxmox
Ceph clusters, and all NetBox-to-Ceph write operations.
