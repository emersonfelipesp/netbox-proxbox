# `netbox_proxbox.templates`

This directory contains Django templates bundled with the plugin.

## Structure

- [`netbox_proxbox/`](./netbox_proxbox/): the plugin template namespace used by all plugin views.

## Notes

- Template names in Python views resolve into this namespaced subtree.
- Most behavior-rich pages pair templates here with JS under `static/netbox_proxbox/js/`.
- The namespaced subtree includes shared layout templates, page fragments, table snippets, test pages, and widget partials.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
