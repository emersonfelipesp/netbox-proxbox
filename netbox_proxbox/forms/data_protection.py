"""Filters for the combined data-protection calendar."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _
from utilities.forms.fields import DynamicModelMultipleChoiceField
from utilities.forms.widgets import DatePicker
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxCluster, ProxmoxNode

__all__ = ("DataProtectionFilterForm",)


class DataProtectionFilterForm(forms.Form):
    """Filter all four data-protection event sources on one page."""

    cluster = DynamicModelMultipleChoiceField(
        queryset=ProxmoxCluster.objects.all(),
        required=False,
        label=_("Proxmox clusters"),
    )
    node = DynamicModelMultipleChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
        label=_("Proxmox nodes"),
    )
    virtual_machine = DynamicModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
        label=_("Virtual machines"),
    )
    date_from = forms.DateField(
        required=False,
        widget=DatePicker(),
        label=_("Date from"),
    )
    date_to = forms.DateField(
        required=False,
        widget=DatePicker(),
        label=_("Date to"),
    )
    kinds_submitted = forms.CharField(
        required=False,
        initial="1",
        widget=forms.HiddenInput(),
    )
    backups = forms.BooleanField(required=False, initial=True, label=_("Backups"))
    snapshots = forms.BooleanField(required=False, initial=True, label=_("Snapshots"))
    replications = forms.BooleanField(
        required=False, initial=True, label=_("Replications")
    )
    routines = forms.BooleanField(required=False, initial=True, label=_("Routines"))

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Select every kind until a submitted filter form says otherwise."""
        data = args[0] if args else kwargs.get("data")
        if data is not None and not data.get("kinds_submitted"):
            prepared = data.copy()
            for field_name in ("backups", "snapshots", "replications", "routines"):
                prepared[field_name] = "on"
            prepared["kinds_submitted"] = "1"
            if args:
                args = (prepared, *args[1:])
            else:
                kwargs["data"] = prepared
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, object]:
        """Require an ordered date range when both boundaries are present."""
        super().clean()
        cleaned = self.cleaned_data
        start = cleaned.get("date_from")
        end = cleaned.get("date_to")
        if start and end and start > end:
            raise forms.ValidationError(_("Date from must not be after date to."))
        return cleaned
