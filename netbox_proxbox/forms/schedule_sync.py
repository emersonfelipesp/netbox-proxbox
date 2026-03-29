"""Form for scheduling a recurring ProxBox sync job."""

from django import forms
from django.utils.translation import gettext_lazy as _

from utilities.datetime import local_now
from utilities.forms.widgets import DateTimePicker, Select2MultipleChoice

from netbox_proxbox.choices import ScheduleIntervalUnitChoices, SyncTypeChoices
from netbox_proxbox.models import NetBoxEndpoint, ProxmoxEndpoint

__all__ = ("ScheduleSyncForm",)


class ScheduleSyncForm(forms.Form):
    sync_type = forms.ChoiceField(
        choices=SyncTypeChoices,
        initial=SyncTypeChoices.ALL,
        label=_("Sync Type"),
        help_text=_("Which sync operation to run."),
    )
    proxmox_endpoints = forms.ModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
        label=_("Proxmox Endpoints"),
        help_text=_(
            "Select specific Proxmox endpoints to sync. Leave empty to sync all."
        ),
        widget=Select2MultipleChoice,
    )
    netbox_endpoints = forms.ModelMultipleChoiceField(
        queryset=NetBoxEndpoint.objects.all(),
        required=False,
        label=_("NetBox Endpoints"),
        help_text=_(
            "Select specific NetBox endpoints to sync to. Leave empty to sync all."
        ),
        widget=Select2MultipleChoice,
    )
    schedule_at = forms.DateTimeField(
        required=False,
        widget=DateTimePicker(),
        label=_("Schedule at"),
        help_text=_("Leave blank to run immediately."),
    )
    interval_value = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label=_("Recurs every"),
        help_text=_("Interval value."),
    )
    interval_unit = forms.ChoiceField(
        choices=ScheduleIntervalUnitChoices,
        initial=ScheduleIntervalUnitChoices.HOURS,
        label=_("Interval unit"),
        help_text=_("Unit of time for the recurrence interval."),
    )

    def __init__(self, *args, **kwargs):
        self.initial_interval = kwargs.pop("initial_interval", None)
        super().__init__(*args, **kwargs)
        now = local_now().strftime("%Y-%m-%d %H:%M:%S %Z")
        self.fields["schedule_at"].help_text += _(
            " (current time: <strong>{now}</strong>)"
        ).format(now=now)

        if self.initial_interval:
            value, unit = ScheduleIntervalUnitChoices.from_minutes(
                self.initial_interval
            )
            self.fields["interval_value"].Initial = value
            self.fields["interval_unit"].Initial = unit

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        schedule_at = cleaned_data.get("schedule_at")
        if schedule_at and schedule_at < local_now():
            raise forms.ValidationError(_("Scheduled time must be in the future."))

        interval_value = cleaned_data.get("interval_value")
        interval_unit = cleaned_data.get("interval_unit")

        if interval_value and interval_unit:
            interval_minutes = ScheduleIntervalUnitChoices.to_minutes(
                interval_value, interval_unit
            )
            cleaned_data["interval"] = interval_minutes

        if cleaned_data.get("interval") and not schedule_at:
            cleaned_data["schedule_at"] = local_now()

        proxmox_endpoints = cleaned_data.get("proxmox_endpoints", [])
        netbox_endpoints = cleaned_data.get("netbox_endpoints", [])

        cleaned_data["proxmox_endpoint_ids"] = (
            [str(ep.pk) for ep in proxmox_endpoints] if proxmox_endpoints else []
        )
        cleaned_data["netbox_endpoint_ids"] = (
            [str(ep.pk) for ep in netbox_endpoints] if netbox_endpoints else []
        )

        return cleaned_data
