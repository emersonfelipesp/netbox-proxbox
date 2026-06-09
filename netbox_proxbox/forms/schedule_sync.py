"""Form for scheduling a recurring ProxBox sync job."""

from django import forms
from django.utils.translation import gettext_lazy as _

from utilities.datetime import local_now
from utilities.forms.fields import DynamicModelMultipleChoiceField
from utilities.forms.widgets import DateTimePicker

from netbox_proxbox.choices import ScheduleIntervalUnitChoices, SyncTypeChoices
from netbox_proxbox.forms.widgets import BootstrapCheckboxSelectMultiple
from netbox_proxbox.models import NetBoxEndpoint, ProxmoxEndpoint

__all__ = ("ScheduleSyncForm",)


class ScheduleSyncForm(forms.Form):
    """Collect options for enqueueing a ProxboxSyncJob (immediate or recurring)."""

    job_name = forms.CharField(
        required=False,
        max_length=200,
        label=_("Job name"),
        help_text=_(
            "Optional label for this job in the job list. "
            "Leave blank to use the default name (Proxbox Sync)."
        ),
    )
    sync_types = forms.MultipleChoiceField(
        choices=SyncTypeChoices,
        initial=[SyncTypeChoices.ALL],
        label=_("Sync types"),
        widget=BootstrapCheckboxSelectMultiple,
        help_text=_(
            "Select one or more operations. Stages always run in dependency order "
            "(devices, then storage, then virtual machines, then VM disks, then VM backups, "
            "then VM snapshots). "
            'You cannot combine "All" with other types.'
        ),
    )
    proxmox_endpoints = DynamicModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.filter(enabled=True),
        required=False,
        label=_("Proxmox Endpoints"),
        help_text=_(
            "Select specific enabled Proxmox endpoints to sync. Leave empty to sync all enabled endpoints."
        ),
    )
    netbox_endpoints = DynamicModelMultipleChoiceField(
        queryset=NetBoxEndpoint.objects.all(),
        required=False,
        label=_("NetBox Endpoints"),
        help_text=_(
            "Select specific NetBox endpoints to sync to. Leave empty to sync all."
        ),
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

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Append current-time hint to schedule help; optionally seed interval fields."""
        self.initial_interval = kwargs.pop("initial_interval", None)
        use_bootstrap_sync_checkboxes = kwargs.pop(
            "use_bootstrap_sync_checkboxes", False
        )
        super().__init__(*args, **kwargs)
        if use_bootstrap_sync_checkboxes:
            sync_field = self.fields["sync_types"]
            old_widget = sync_field.widget
            sync_field.widget = BootstrapCheckboxSelectMultiple(
                attrs=old_widget.attrs.copy(),
            )
            # Replacing the widget drops choice tuples; without this, optgroups is empty.
            sync_field.widget.choices = sync_field.choices
        # Singleton NetBox endpoint: pre-select the only row on fresh GET requests.
        if not self.is_bound:
            sole_nb_pks = list(NetBoxEndpoint.objects.values_list("pk", flat=True))
            if len(sole_nb_pks) == 1:
                self.initial.setdefault("netbox_endpoints", sole_nb_pks)
        now = local_now().strftime("%Y-%m-%d %H:%M:%S %Z")
        self.fields["schedule_at"].help_text += _(
            " (current time: <strong>{now}</strong>)"
        ).format(now=now)

        if self.initial_interval:
            value, unit = ScheduleIntervalUnitChoices.from_minutes(
                self.initial_interval
            )
            self.fields["interval_value"].initial = value
            self.fields["interval_unit"].initial = unit

        if not self.is_bound:
            if "sync_types" not in self.initial and "sync_type" in self.initial:
                legacy = self.initial.pop("sync_type")
                self.initial["sync_types"] = (
                    [legacy] if legacy else [SyncTypeChoices.ALL]
                )
            self.initial.setdefault("sync_types", [SyncTypeChoices.ALL])
            if use_bootstrap_sync_checkboxes:
                self.fields["sync_types"].initial = self.initial.get(
                    "sync_types", [SyncTypeChoices.ALL]
                )

    def clean_sync_types(self) -> list[str]:
        """Disallow mixing ``all`` with other slugs; require at least one type."""
        values = list(self.cleaned_data.get("sync_types") or [])
        if not values:
            raise forms.ValidationError(_("Select at least one sync type."))
        if SyncTypeChoices.ALL in values and len(values) > 1:
            all_label = next(
                (c[1] for c in SyncTypeChoices.CHOICES if c[0] == SyncTypeChoices.ALL),
                _("All"),
            )
            raise forms.ValidationError(
                _('Cannot combine "%(all_label)s" with other sync types.')
                % {"all_label": all_label}
            )
        return values

    def clean_job_name(self) -> str:
        """Normalize optional custom job label to stripped text."""
        name = (self.cleaned_data.get("job_name") or "").strip()
        return name or ""

    def clean(self) -> dict[str, object]:
        """Validate schedule time, derive interval minutes, and flatten endpoint id lists."""
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
