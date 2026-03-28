# netbox-proxbox Codebase Guide

This repository packages the `netbox_proxbox` NetBox plugin. The plugin adds endpoint inventory for Proxmox, NetBox, and the companion ProxBox FastAPI backend; UI pages for sync operations and status checks; REST API endpoints for those models; and a small amount of browser-side JavaScript and styling for the plugin pages.

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.7` and NetBox compatibility `4.5.0` through `4.5.99`.

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `SyncProcess`, and `VMBackup` are the plugin's main persisted models.
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes.
- Sync actions do not perform the sync themselves inside NetBox. They enqueue or trigger work on the external ProxBox FastAPI service over HTTP, and optional browser updates can flow over WebSocket.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.

## How To Navigate

- Start with [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md) for the package-level map.
- Go to `models`, `views`, and `api` first when changing behavior.
- Use `forms`, `filtersets`, and `tables` when changing how plugin objects are edited or listed in NetBox.
- Use `templates` and `static` together when adjusting UI behavior, page structure, or browser-side interactions.
- Check `migrations` before changing any model field or constraint.

## Index

- [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/api/CLAUDE.md`](./netbox_proxbox/api/CLAUDE.md)
- [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md)
- [`netbox_proxbox/migrations/CLAUDE.md`](./netbox_proxbox/migrations/CLAUDE.md)
- [`netbox_proxbox/models/CLAUDE.md`](./netbox_proxbox/models/CLAUDE.md)
- [`netbox_proxbox/static/CLAUDE.md`](./netbox_proxbox/static/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [`netbox_proxbox/tables/CLAUDE.md`](./netbox_proxbox/tables/CLAUDE.md)
- [`netbox_proxbox/templates/CLAUDE.md`](./netbox_proxbox/templates/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [`netbox_proxbox/views/CLAUDE.md`](./netbox_proxbox/views/CLAUDE.md)
- [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md)
