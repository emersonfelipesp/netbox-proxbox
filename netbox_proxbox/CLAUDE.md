# `netbox_proxbox` Package

This package contains the NetBox plugin itself. It defines the plugin config, URL registration, navigation, models, forms, tables, API layer, background jobs, sync helpers, dashboard views, template hooks, and bundled static assets.

## Files And Ownership

- [`__init__.py`](./__init__.py): plugin registration via `PluginConfig`, plugin metadata, and supported NetBox version range.
- [`urls.py`](./urls.py): plugin URL map for UI pages, model views, sync routes, keepalive checks, card hydration, and the WebSocket test endpoint.
- [`navigation.py`](./navigation.py): NetBox plugin menu groups and buttons.
- [`choices.py`](./choices.py): `ChoiceSet` definitions for endpoint modes, sync types/statuses, token versions, and VM backup metadata.
- [`fields.py`](./fields.py): custom model/form field helpers used by the endpoint models.
- [`filtersets.py`](./filtersets.py): NetBox filtersets backing list views and API query filtering.
- [`jobs.py`](./jobs.py): `ProxboxSyncJob` background job class, enqueue helpers, and concurrent-run ownership guards.
- [`sync_types.py`](./sync_types.py): regex-based targeted VM job name parsing and sync-type expansion helpers used by `jobs.py`.
- [`sync_params.py`](./sync_params.py): normalises and serialises sync parameters passed into `ProxboxSyncJob.enqueue`.
- [`sync_stages.py`](./sync_stages.py): runs a single named sync stage against the backend SSE stream.
- [`sync_ownership.py`](./sync_ownership.py): helpers that claim and release RQ job ownership to prevent concurrent duplicate runs.
- [`schedule_hints.py`](./schedule_hints.py): quick-schedule heuristics and UI defaults for the home dashboard.
- [`github.py`](./github.py): fetches markdown content from GitHub for the contributing page.
- [`template_content.py`](./template_content.py): plugin template extensions for Job and VirtualMachine buttons/panels.
- [`type_defs.py`](./type_defs.py): shared type aliases and lightweight protocol helpers used across the package.
- [`utils.py`](./utils.py): URL and host helpers, especially for the FastAPI backend and mkcert-aware local TLS handling.
- [`websocket_client.py`](./websocket_client.py): long-lived WebSocket client, message queue, and HTTP view used to stream backend messages into NetBox pages.
- [`signals.py`](./signals.py): Django signal handlers for automatic token generation and backend registration when FastAPIEndpoint objects are created or updated.
- [`schemas/`](./schemas): Pydantic models and formatters for backend payloads, normalized sync context, and OpenAPI helpers.
- [`services/`](./services): backend proxy, schema caching, service status, and sync coordination helpers.
- [`management/`](./management): Django management commands package.
- [`templatetags/`](./templatetags): custom template tags for ProxBox templates.
- [`models/`](./models): persisted plugin models for Proxmox, remote NetBox, FastAPI, clusters, nodes, storage, backups, snapshots, task history, backup routines, replications, and settings.
- [`forms/`](./forms): create/edit, filter, and scheduling forms for plugin models and sync actions.
- [`tables/`](./tables): list-view table classes for endpoint, storage, backup, snapshot, replication, and cluster views.
- [`views/`](./views): dashboard pages, endpoint CRUD, sync actions, job helpers, status checks, and targeted sync buttons.
- [`api/`](./api): NetBox plugin API viewsets, serializers, filters, and URL wiring.
- [`migrations/`](./migrations): Django schema history for the plugin models.
- [`templates/`](./templates): bundled Django templates for plugin pages and template fragments.
- [`static/`](./static): bundled images, JS, CSS, SCSS, and generated theme assets.

## Data Flow

- Endpoint objects are created in NetBox through forms and model views.
- List and detail pages are rendered by classes in `views/` using tables, filtersets, and templates.
- Sync routes call the external ProxBox FastAPI backend using the configured `FastAPIEndpoint`. Two sync transport modes are available:
  - POST polling (traditional): the plugin waits for completion and returns a single JSON response.
  - GET SSE streaming: the plugin proxies `text/event-stream` from the FastAPI backend to the browser via `StreamingHttpResponse`. The browser JS parses SSE frames and renders granular per-object progress in real time.
- The API layer exposes the same main models through NetBox plugin API endpoints.
- Browser-side pages use templates plus JS from `static/netbox_proxbox/js/` for dashboard hydration, keepalive polling, SSE streaming, log rendering, and WebSocket updates.

## Dependencies

- Inbound: NetBox plugin loader imports `config`, NetBox route registration imports `urls.py`, and the menu system imports `navigation.py`.
- Outbound: Django/NetBox APIs, `requests`, `websockets`, the external ProxBox FastAPI service, GitHub raw content for the contributing page, and standard NetBox core models like `users.Token`, `ipam.IPAddress`, `virtualization.VirtualMachine`, and `virtualization.Cluster`.

## Installation Docs

- Docker-based NetBox installation guidance is documented at [`../docs/installation/3-installing-plugin-docker.md`](../docs/installation/3-installing-plugin-docker.md).
- Traditional host/venv installation remains documented in [`../docs/installation/2-installing-plugin-git.md`](../docs/installation/2-installing-plugin-git.md).

## Child Docs

- [`../CLAUDE.md`](../CLAUDE.md)
- [`api/CLAUDE.md`](./api/CLAUDE.md)
- [`forms/CLAUDE.md`](./forms/CLAUDE.md)
- [`management/CLAUDE.md`](./management/CLAUDE.md)
- [`management/commands/CLAUDE.md`](./management/commands/CLAUDE.md)
- [`migrations/CLAUDE.md`](./migrations/CLAUDE.md)
- [`models/CLAUDE.md`](./models/CLAUDE.md)
- [`schemas/CLAUDE.md`](./schemas/CLAUDE.md)
- [`services/CLAUDE.md`](./services/CLAUDE.md)
- [`static/CLAUDE.md`](./static/CLAUDE.md)
- [`tables/CLAUDE.md`](./tables/CLAUDE.md)
- [`templates/CLAUDE.md`](./templates/CLAUDE.md)
- [`templatetags/CLAUDE.md`](./templatetags/CLAUDE.md)
- [`views/CLAUDE.md`](./views/CLAUDE.md)
