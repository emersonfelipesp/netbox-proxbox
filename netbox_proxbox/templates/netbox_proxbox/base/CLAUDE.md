# `templates/netbox_proxbox/base`

This directory contains shared layout templates for the plugin.

## Files And Ownership

- [`base.html`](./base.html): plugin base template wrapper.
- [`layout.html`](./layout.html): shared page layout scaffold.
- [`sidenav.html`](./sidenav.html): plugin side navigation markup.
- [`40x.html`](./40x.html): error-page template.

## Dependencies

- Inbound: many plugin templates extend or include these base templates.
- Outbound: NetBox's own base layout and plugin static styling.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
