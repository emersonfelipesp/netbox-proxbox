"""Rejection form for Proxmox deletion requests."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

__all__ = ("DeletionRequestRejectForm",)


class DeletionRequestRejectForm(forms.Form):
    """Collect the rejection reason stored on a DeletionRequest."""

    reject_reason = forms.CharField(
        required=True,
        max_length=255,
        label=_("Reject reason"),
        widget=forms.Textarea(attrs={"rows": 4}),
    )
