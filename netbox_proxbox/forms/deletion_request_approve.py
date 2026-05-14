"""Approval form for Proxmox deletion requests."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.models import DeletionRequest

__all__ = ("DeletionRequestApproveForm",)


class DeletionRequestApproveForm(forms.Form):
    """Require typed VMID confirmation before approving a deletion request."""

    vmid = forms.IntegerField(
        required=True,
        label=_("Confirm VMID"),
        help_text=_("Type the VMID from this deletion request to approve execution."),
    )

    def __init__(
        self,
        *args: Any,
        instance: DeletionRequest,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.instance = instance

    def clean_vmid(self) -> int:
        vmid = self.cleaned_data["vmid"]
        if vmid != self.instance.vmid:
            raise forms.ValidationError(
                _("Typed VMID does not match this deletion request.")
            )
        return vmid
