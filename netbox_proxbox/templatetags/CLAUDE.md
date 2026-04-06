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

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)