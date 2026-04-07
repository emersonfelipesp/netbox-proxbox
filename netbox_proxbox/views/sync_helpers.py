"""Shared helpers for sync enqueue views."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


class _ProxboxSyncViewBase(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Base mixin providing shared permission and mixin stack for sync views."""

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()


def build_job_name(action_label: str = "") -> str:
    """Build a display name for a Proxbox sync job."""
    if action_label:
        return str(format_lazy("{}: {}", _("Proxbox Sync"), action_label))
    return str(_("Proxbox Sync"))


def notify_sync_enqueued(request: HttpRequest, job, message: str) -> None:
    """Add a success message linking to the enqueued job."""
    messages.success(
        request,
        format_html(
            '{} <a href="{}">{}</a>',
            message,
            job.get_absolute_url(),
            _("View job"),
        ),
    )


def notify_sync_error(request: HttpRequest, error: Exception) -> None:
    """Add an error message for a failed sync enqueue."""
    messages.error(
        request,
        format_html(
            "{} <strong>{}</strong>",
            _("Failed to enqueue sync job:"),
            str(error),
        ),
    )
