# `netbox_proxbox` Package

This package contains the actual NetBox plugin. It defines the plugin config, URL registration, plugin navigation, persistent models, background jobs, backend schemas/services, REST API layer, UI views, and all bundled templates and static assets.

## Files And Ownership

- [`__init__.py`](./__init__.py): plugin registration via `PluginConfig`, plugin metadata, and supported NetBox version range.
- [`urls.py`](./urls.py): plugin URL map for UI pages, model views, sync routes, keepalive checks, card hydration, and the WebSocket polling endpoint.
- [`navigation.py`](./navigation.py): NetBox plugin menu groups and buttons.
- [`choices.py`](./choices.py): `ChoiceSet` definitions for endpoint modes, sync types/statuses, token versions, and VM backup metadata.
- [`fields.py`](./fields.py): custom model/form field helpers used by the endpoint models.
- [`filtersets.py`](./filtersets.py): NetBox filtersets backing list views and API query filtering.
- [`jobs.py`](./jobs.py): `ProxboxSyncJob`, sync-stage ordering, and helpers that rebuild enqueue parameters from saved job data.
- [`schedule_hints.py`](./schedule_hints.py): quick-schedule heuristics and UI defaults for the home dashboard.
- [`schemas/`](./schemas): Pydantic models and formatters for backend payloads, normalized sync context, and OpenAPI helpers.
- [`services/`](./services): backend proxy, schema caching, service status, and sync coordination helpers.
- [`utils.py`](./utils.py): URL and host helpers, especially for the FastAPI backend and mkcert-aware local TLS handling.
- [`github.py`](./github.py): fetches markdown content from GitHub for the contributing page.
- [`template_content.py`](./template_content.py): plugin template extensions for Job and VirtualMachine buttons/panels.
- [`websocket_client.py`](./websocket_client.py): long-lived WebSocket client, message queue, and HTTP view used to stream backend messages into NetBox pages.
- [`views/proxbox_access.py`](./views/proxbox_access.py): canonical `get_permission_for_model()` helpers for custom views (sync, jobs, WebSocket, dashboard gate).
- Child directories: models, forms, tables, views, api, migrations, templates, and static assets.

## Data Flow

- Endpoint objects are created in NetBox through forms and model views.
- List and detail pages are rendered by classes in `views/` using tables, filtersets, and templates.
- Sync routes call the external ProxBox FastAPI backend using the configured `FastAPIEndpoint`. Two sync transport modes are available:
  - POST polling (traditional): plugin waits for completion and returns a single JSON response.
  - GET SSE streaming: plugin proxies `text/event-stream` from the FastAPI backend to the browser via `StreamingHttpResponse`. The browser JS parses SSE frames and renders granular per-object progress in real time.
- The API layer exposes the same main models through NetBox plugin API endpoints.
- Browser-side pages use templates plus JS from `static/netbox_proxbox/js/` for dashboard hydration, keepalive polling, SSE streaming, and WebSocket updates.

## Dependencies

- Inbound: NetBox plugin loader imports `config`, NetBox route registration imports `urls.py`, and the menu system imports `navigation.py`.
- Outbound: Django/NetBox APIs, `requests`, `websockets`, the external ProxBox FastAPI service, GitHub raw content for the contributing page, and standard NetBox core models like `users.Token`, `ipam.IPAddress`, `virtualization.VirtualMachine`, and `virtualization.Cluster`.

## Installation docs pointers

- Docker-based NetBox installation guidance is documented at [`../docs/installation/3-installing-plugin-docker.md`](../docs/installation/3-installing-plugin-docker.md).
- Traditional host/venv installation remains documented in [`../docs/installation/2-installing-plugin-git.md`](../docs/installation/2-installing-plugin-git.md).

## Child Docs

- [`../CLAUDE.md`](../CLAUDE.md)
- [`api/CLAUDE.md`](./api/CLAUDE.md)
- [`forms/CLAUDE.md`](./forms/CLAUDE.md)
- [`migrations/CLAUDE.md`](./migrations/CLAUDE.md)
- [`models/CLAUDE.md`](./models/CLAUDE.md)
- [`static/CLAUDE.md`](./static/CLAUDE.md)
- [`tables/CLAUDE.md`](./tables/CLAUDE.md)
- [`templates/CLAUDE.md`](./templates/CLAUDE.md)
- [`views/CLAUDE.md`](./views/CLAUDE.md)
