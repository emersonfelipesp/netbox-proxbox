# Agent Entry Points

## Pre-commit Checklist

**Before committing ANY change:**

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `ruff check .`
3. Run tests: `pytest tests/`

---

## Framework stack preference

When implementing or changing behavior, prefer solutions in this order:

1. **NetBox plugin idioms** — Patterns used in this plugin and in NetBox’s plugin framework (`netbox.plugins`, plugin models, views, tables, filtersets, serializers as NetBox documents them).
2. **NetBox core** — Built-in modules such as `utilities.forms`, `utilities.views`, `netbox.*` model and API bases, and DRF usage aligned with upstream NetBox.
3. **Django** — Standard `django.*` APIs when NetBox does not expose an equivalent.

Do **not** add new third-party PyPI dependencies to replace what NetBox or Django already provides (forms, widgets, routing, auth, REST patterns). Existing runtime deps in `pyproject.toml` (for example `requests`, `websockets`, optional CLI extras) are fine; avoid piling on more libraries for the same problems.

## Security

Use NetBox view mixins from `utilities.views` (`ConditionalLoginRequiredMixin`, `TokenConditionalLoginRequiredMixin`, `ContentTypePermissionRequiredMixin`) for custom routes; enforce object visibility with `QuerySet.restrict()`. Permission strings for ProxBox-specific operations are centralized in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py). Details: [`CLAUDE.md`](./CLAUDE.md) (Security and permissions).

---

Read [`CLAUDE.md`](./CLAUDE.md) first for the plugin architecture and the full documentation map. Use the lower-level `CLAUDE.md` files when working in a specific directory or when changing only one layer of the plugin.

## CLAUDE.md Index

- [`CLAUDE.md`](./CLAUDE.md)
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
- [`tests/CLAUDE.md`](./tests/CLAUDE.md)
