# Agent Entry Points

## Pre-commit Checklist

Before committing any change:

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run type checker: `rtk ty check proxbox_cli`
4. Run tests: `rtk pytest tests/`

## Framework Stack

When implementing or changing behavior, prefer solutions in this order:

1. NetBox plugin idioms - patterns already used in this plugin and in NetBox's plugin framework.
2. NetBox core - `utilities.forms`, `utilities.views`, `netbox.*` bases, and NetBox-aligned DRF usage.
3. Django - standard `django.*` APIs when NetBox does not provide an equivalent.

Do not add new third-party PyPI dependencies to replace what NetBox or Django already provides. Existing runtime dependencies in `pyproject.toml` — `requests`, `websockets`, `pydantic` (used throughout `schemas/`), and the optional CLI extras — are fine.

## Security

Use NetBox view mixins from `utilities.views` (`ConditionalLoginRequiredMixin`, `TokenConditionalLoginRequiredMixin`, `ContentTypePermissionRequiredMixin`) for custom routes. Enforce object visibility with `QuerySet.restrict()`. Permission strings for ProxBox-specific operations are centralized in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py); see [`CLAUDE.md`](./CLAUDE.md) for the current permission and workflow notes.

## Configuration policy

**Prefer DB-backed plugin settings over `.env` variables.**
When adding a new runtime tunable that the plugin or the companion `proxbox-api`
backend needs to read, default to making it a
[`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py) field —
NetBox-UI-editable and persisted in the NetBox database. On the backend it is read
via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`, which
already resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** with
no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer,
template — and existing fields plus migration
[`0037_pluginsettings_runtime_tunables.py`](./netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py)
show the pattern. See [`CLAUDE.md → Plugin settings and configuration`](./CLAUDE.md)
for the full keep-list.

## Navigation

Read [`CLAUDE.md`](./CLAUDE.md) first for the plugin architecture and documentation map. Use the lower-level `CLAUDE.md` files when working in a specific directory or when changing only one layer of the plugin.

Key architectural invariants to keep in mind:

- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons.** The backend proxy (`services/backend_proxy.py`) and dashboard views always resolve the backend via `.first()`. Import views enforce the singleton constraint — if a record exists, the user is prompted to confirm the override before the existing record is deleted and replaced.
- **Endpoint export views require token proof for sensitive fields.** `_validate_sensitive_export_token()` supports v1 (dropdown or manual) and v2 (key + secret) modes. Never bypass this check or expose credential fields without it.
- **Export JS is inlined, not a separate static file.** All three endpoint list templates contain the export-modal IIFE directly in `{% block javascript %}`. Do not move it to a `.js` file — it would then require `collectstatic` to be served.
- **Import forms auto-create IPAddress objects.** All three import forms call `IPAddress.objects.get_or_create` in `clean_ip_address()`. Do not replace this with `CSVModelChoiceField` for `ip_address` — that would break cross-instance imports.

## CLAUDE.md Index

Read the nearest scoped guide for the code you are changing.

- [CLAUDE.md](CLAUDE.md)
- [netbox_proxbox/CLAUDE.md](netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/api/CLAUDE.md](netbox_proxbox/api/CLAUDE.md)
- [netbox_proxbox/forms/CLAUDE.md](netbox_proxbox/forms/CLAUDE.md)
- [netbox_proxbox/management/CLAUDE.md](netbox_proxbox/management/CLAUDE.md)
- [netbox_proxbox/management/commands/CLAUDE.md](netbox_proxbox/management/commands/CLAUDE.md)
- [netbox_proxbox/migrations/CLAUDE.md](netbox_proxbox/migrations/CLAUDE.md)
- [netbox_proxbox/models/CLAUDE.md](netbox_proxbox/models/CLAUDE.md)
- [netbox_proxbox/schemas/CLAUDE.md](netbox_proxbox/schemas/CLAUDE.md)
- [netbox_proxbox/services/CLAUDE.md](netbox_proxbox/services/CLAUDE.md)
- [netbox_proxbox/static/CLAUDE.md](netbox_proxbox/static/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [netbox_proxbox/tables/CLAUDE.md](netbox_proxbox/tables/CLAUDE.md)
- [netbox_proxbox/templates/CLAUDE.md](netbox_proxbox/templates/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [netbox_proxbox/templatetags/CLAUDE.md](netbox_proxbox/templatetags/CLAUDE.md)
- [netbox_proxbox/views/CLAUDE.md](netbox_proxbox/views/CLAUDE.md)
- [netbox_proxbox/views/endpoints/CLAUDE.md](netbox_proxbox/views/endpoints/CLAUDE.md)
- [netbox_proxbox/views/sync_now/CLAUDE.md](netbox_proxbox/views/sync_now/CLAUDE.md)
- [proxbox_cli/CLAUDE.md](proxbox_cli/CLAUDE.md)
- [tests/CLAUDE.md](tests/CLAUDE.md)
