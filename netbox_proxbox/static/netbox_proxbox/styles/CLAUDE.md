# `netbox_proxbox.static.netbox_proxbox.styles`

This directory contains SCSS sources and compiled theme/static CSS assets used by the plugin UI.

## Contents

- SCSS partials for light/dark themes, external pages, print, side navigation, tables, cable trace, rack elevation, and utility variables.
- Compiled CSS outputs such as `netbox-light.css`, `netbox-dark.css`, `netbox-external.css`, `netbox-print.css`, `cable_trace.css`, and `rack_elevation.css`.
- Vendored or generated front-end assets such as `graphiql.*`, `netbox.js*`, and icon font files.

## Dependencies

- Inbound: base templates and page templates include these styles.
- Outbound: none in Python; these files are presentation-only.

## Notes

- Preserve the distinction between SCSS sources and generated artifacts when editing.
- Some files appear to be upstream or vendored NetBox style assets; avoid rewriting them casually unless the change is intentional.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
