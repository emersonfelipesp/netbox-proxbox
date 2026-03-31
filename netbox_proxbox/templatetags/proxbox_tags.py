"""Custom template tags and filters for netbox-proxbox."""

from django import template
from django.utils.html import format_html
from django.urls import reverse

register = template.Library()


@register.filter
def hyperlinked_object(obj):
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
