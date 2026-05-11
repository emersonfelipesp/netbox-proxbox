"""Custom template tags and filters for netbox-proxbox."""

from __future__ import annotations

import base64
import mimetypes
from functools import lru_cache
from pathlib import Path

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Logos and JS modules referenced by the home dashboard are inlined into the
# HTML response (issue #355). This guarantees the page renders correctly even
# when ``manage.py collectstatic`` was skipped after a plugin install/upgrade,
# which would otherwise leave logos broken and cluster cards stuck on
# "Loading" because ``home.js`` (an ES module) failed to load.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_STATIC_ROOT = _PACKAGE_ROOT / "static"


@lru_cache(maxsize=32)
def _read_static(relative_path: str) -> bytes:
    candidate = (_STATIC_ROOT / relative_path).resolve()
    static_root_resolved = _STATIC_ROOT.resolve()
    if (
        static_root_resolved not in candidate.parents
        and candidate != static_root_resolved
    ):
        raise ValueError(
            f"Refusing to read static asset outside of static root: {relative_path}"
        )
    return candidate.read_bytes()


@register.simple_tag
def proxbox_version() -> str:
    """Return the current Proxbox plugin version string."""
    from netbox_proxbox import config as proxbox_config

    return proxbox_config.version


@register.filter
def hyperlinked_object(obj: object | None) -> str:
    """
    Return a hyperlinked HTML representation of an object.

    Usage:
        {{ object|hyperlinked_object }}

    Returns:
        HTML link: <a href="object.get_absolute_url">object</a>
    """
    if obj is None:
        return "—"

    try:
        url = obj.get_absolute_url()
        return format_html('<a href="{}">{}</a>', url, obj)
    except Exception:  # noqa: BLE001 — template filter must never raise
        return str(obj)


@register.filter
def div(value: object, arg: object) -> int:
    """Divide value by arg and return integer result."""
    try:
        return int(value) // int(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter(name="form_field")
def form_field(form: object, name: str) -> object:
    """Look up a bound form field by string name (for dynamically-named fields)."""
    try:
        return form[name]
    except (KeyError, TypeError):
        return ""


@register.simple_tag
def inline_logo_data_uri(relative_path: str) -> str:
    """Return a ``data:`` URI for a static asset bundled with the plugin.

    Used by the home dashboard cards so logos render even when NetBox
    has not run ``collectstatic`` for the plugin (issue #355). SVGs are
    URL-encoded to keep the output small; raster images are base64-encoded.
    """
    try:
        payload = _read_static(relative_path)
    except (FileNotFoundError, ValueError):
        return ""

    mime, _ = mimetypes.guess_type(relative_path)
    if mime is None:
        mime = "application/octet-stream"

    if mime == "image/svg+xml":
        from urllib.parse import quote

        encoded = quote(payload.decode("utf-8"), safe="")
        return f"data:{mime};utf8,{encoded}"

    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@register.simple_tag
def inline_static_script(relative_path: str) -> str:
    """Return the contents of a JS file as a ``<script>`` tag body.

    Loads dashboard JavaScript inline so the home page hydrates even when
    ``collectstatic`` has not been run after a plugin upgrade (issue #355).
    The caller is expected to wrap the output in ``<script>...</script>``.
    """
    try:
        payload = _read_static(relative_path)
    except (FileNotFoundError, ValueError):
        return ""
    # Safe because payload is read from bundled plugin static files, not user input.
    return mark_safe(payload.decode("utf-8"))  # nosec


@register.filter
def sync_type_label(slug: str) -> str:
    """Convert sync type slug to user-friendly label."""
    labels = {
        "all": "All",
        "devices": "Devices",
        "storage": "Storage",
        "virtual-machines": "VMs",
        "vm-disks": "VM Disks",
        "vm-interfaces": "VM Interfaces",
        "vm-backups": "VM Backups",
        "vm-snapshots": "VM Snapshots",
        "network-interfaces": "Net Ifaces",
        "ip-addresses": "IP Addresses",
        "backup-routines": "Backup Routines",
        "replications": "Replications",
    }
    return labels.get(slug, slug)
