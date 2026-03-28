# `netbox_proxbox.views.endpoints`

This directory contains NetBox generic model views for the three endpoint models.

## Files And Ownership

- [`proxmox.py`](./proxmox.py): list/detail/edit/delete views for `ProxmoxEndpoint`.
- [`netbox.py`](./netbox.py): list/detail/edit/delete views for `NetBoxEndpoint`.
- [`fastapi.py`](./fastapi.py): list/detail/edit/delete views for `FastAPIEndpoint`.
- [`__init__.py`](./__init__.py): re-exports endpoint view classes.

## Dependencies

- Inbound: `views/__init__.py` imports and re-exports these classes, and `urls.py` mounts them via `get_model_urls(...)`.
- Outbound: matching models, tables, filtersets, and forms for each endpoint type.

## Notes

- These files are intentionally thin; most endpoint-specific behavior lives in the model, form, filterset, and template layers.
- Changes to list columns, validation, or field presentation typically happen outside this directory unless the view wiring itself changes.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
