"""Form for scheduling a recurring ProxBox sync job."""

from django import forms
from django.utils.translation import gettext_lazy as _

from core.choices import JobIntervalChoices
from utilities.datetime import local_now
from utilities.forms.widgets import DateTimePicker, NumberWithOptions

from netbox_proxbox.choices import SyncTypeChoices

__all__ = ("ScheduleSyncForm",)


class ScheduleSyncForm(forms.Form):
    sync_type = forms.ChoiceField(
        choices=SyncTypeChoices,
        initial=SyncTypeChoices.ALL,
        label=_("Sync Type"),
        help_text=_("Which sync operation to run."),
    )
    schedule_at = forms.DateTimeField(
        required=False,
        widget=DateTimePicker(),
        label=_("Schedule at"),
        help_text=_("Leave blank to run immediately."),
    )
    interval = forms.IntegerField(
        required=False,
        min_value=1,
        label=_("Recurs every"),
        widget=NumberWithOptions(options=JobIntervalChoices),
        help_text=_("Recurrence interval in minutes. Leave blank for a one-time execution."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        now = local_now().strftime("%Y-%m-%d %H:%M:%S %Z")
        self.fields["schedule_at"].help_text += _(
            " (current time: <strong>{now}</strong>)"
        ).format(now=now)

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        schedule_at = cleaned_data.get("schedule_at")
        if schedule_at and schedule_at < local_now():
            raise forms.ValidationError(_("Scheduled time must be in the future."))
        # If only interval is provided, default schedule_at to now
        if cleaned_data.get("interval") and not schedule_at:
            cleaned_data["schedule_at"] = local_now()
        return cleaned_data
