# `netbox_proxbox.static.netbox_proxbox.styles`

This directory contains SCSS sources and compiled theme/static CSS assets used by the plugin UI.

## Contents

- Theme source files such as `theme-base.scss`, `theme-dark.scss`, `theme-light.scss`, `_dark.scss`, `_light.scss`, `bootstrap.scss`, `utilities.scss`, `overrides.scss`, `sidenav.scss`, `flatpickr-dark.scss`, `_external.scss`, `_print.scss`, `_cable_trace.scss`, and `_rack_elevation.scss`.
- Compiled CSS and generated assets such as `netbox-dark.css`, `netbox-light.css`, `netbox-external.css`, `netbox-print.css`, `cable_trace.css`, `rack_elevation.css`, `logs.css`, `graphiql.css`, `graphiql.js`, `netbox.js`, and `netbox.js.map`.
- Vendored fonts and icon assets used by the NetBox theme overrides.

## Dependencies

- Inbound: base templates and page templates include these styles.
- Outbound: none in Python; these files are presentation-only.

## Notes

- Preserve the distinction between SCSS sources and generated artifacts when editing.
- Some files appear to be upstream or vendored NetBox style assets; avoid rewriting them casually unless the change is intentional.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
