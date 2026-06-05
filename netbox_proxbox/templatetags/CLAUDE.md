# `netbox_proxbox.templatetags`

This directory contains custom Django template tags and filters for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`proxbox_tags.py`](./proxbox_tags.py): custom template tags and filters used in ProxBox templates.

## Dependencies

- Inbound: Django template loader imports tags when templates use `{% load proxbox_tags %}`.
- Outbound: Django template context and NetBox template utilities.

## Usage

In templates:

```django
{% load proxbox_tags %}
```

## Notes

- Template tags are registered in the `proxbox_tags` library.
- Tags provide helper functions for rendering ProxBox-specific template content.
- `proxbox_paginate_url(param_name, value)` (a `takes_context=True` simple tag)
  builds a pagination URL that preserves the current query string while setting
  one page parameter. It backs the shared paginator partial at
  `templates/netbox_proxbox/inc/paginator.html`, which is included by the custom
  list pages (devices, virtual machines, LXC containers, virtual disks, clusters)
  and — with `page_param="vm_page"` / `page_param="node_page"` — by the
  two-table interfaces and IP-address pages. Changing `per_page` resets every
  page cursor so the user is never stranded on an out-of-range page.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)