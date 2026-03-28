# `netbox_proxbox.static`

This directory is the top-level container for plugin static files served by Django/NetBox.

## Structure

- [`netbox_proxbox/`](./netbox_proxbox/): plugin-specific static namespace containing images, JavaScript, and stylesheets.

## Notes

- Keep static assets under the namespaced `netbox_proxbox/` subtree so they do not collide with other NetBox plugins.
- Browser-side behavior is implemented in the `js/` subtree; CSS and SCSS sources are in `styles/`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
