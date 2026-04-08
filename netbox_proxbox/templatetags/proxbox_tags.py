"""Custom template tags and filters for netbox-proxbox."""

from django import template
from django.utils.html import format_html

register = template.Library()


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
    except (AttributeError, Exception):
        # Fallback: return string representation
        return str(obj)


@register.filter
def div(value: object, arg: object) -> int:
    """Divide value by arg and return integer result."""
    try:
        return int(value) // int(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


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
