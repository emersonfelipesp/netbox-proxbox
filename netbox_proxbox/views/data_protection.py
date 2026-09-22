"""Server-rendered calendars for Proxbox data-protection inventory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from utilities.permissions import get_permission_for_model
from utilities.views import ConditionalLoginRequiredMixin
from virtualization.models import VirtualMachine

from netbox_proxbox.forms.data_protection import DataProtectionFilterForm
from netbox_proxbox.models import (
    BackupRoutine,
    ProxmoxCluster,
    ProxmoxNode,
    Replication,
    VMBackup,
    VMSnapshot,
)
from netbox_proxbox.services.data_protection_calendar import (
    CALENDAR_SOURCE_LIMIT,
    CalendarEvent,
    SourceTruncation,
    build_month_grid,
    build_week_grid,
    calendar_query_string,
    materialize_source_rows,
    shift_anchor,
    visible_range,
)
from netbox_proxbox.services.pve_calendar_event import ParsedSchedule, parse

__all__ = ("DataProtectionCalendarMixin", "DataProtectionView")


# Upper bound for the unified event table under the combined calendar. A
# schedule projected onto every day of a month grid multiplies quickly (fifty
# daily routines already produce about two thousand rows). Source limits are
# enforced independently before this table-only cap.
EVENT_TABLE_LIMIT = 500

# Truncation order for scheduled sources: active, enabled jobs win the event
# budget; stale or disabled ones come last, then a stable pk order.
REPLICATION_ORDER_FIELDS = ("disable", "status", "pk")
ROUTINE_ORDER_FIELDS = ("-enabled", "status", "pk")

KIND_FIELDS = {
    "backup": "backups",
    "snapshot": "snapshots",
    "replication": "replications",
    "routine": "routines",
}


@dataclass(frozen=True, slots=True)
class _EventRecord:
    event: CalendarEvent
    virtual_machine: str
    node: str


LabelBuilder = Callable[[Mapping[str, object]], str]
MutedBuilder = Callable[[Mapping[str, object]], bool]
DetailBuilder = Callable[[Mapping[str, object]], tuple[str, str]]
SourceResult = tuple[list[_EventRecord], int, SourceTruncation]


def _calendar_state(
    request: HttpRequest, fallback_anchor: date | None = None
) -> tuple[str, date]:
    """Read ``cal_view``/``cal_date`` from the query string, tolerating junk.

    ``fallback_anchor`` is used when ``cal_date`` is absent or invalid, so the
    combined page can open on the first day of an explicit date-range filter.
    """
    view = request.GET.get("cal_view", "month")
    view = view if view in {"month", "week"} else "month"
    try:
        anchor = date.fromisoformat(request.GET.get("cal_date", ""))
    except (TypeError, ValueError):
        anchor = fallback_anchor or timezone.localdate()
    return view, _safe_anchor(anchor)


def _safe_anchor(anchor: date) -> date:
    """Keep the anchor away from the first and last representable years.

    A month grid around year 1 or year 9999 needs dates that ``datetime.date``
    cannot represent, so those anchors fall back to today instead of raising.
    """
    if anchor.year in {date.min.year, date.max.year}:
        return timezone.localdate()
    return anchor


def _aware_midnight(day: date) -> datetime:
    value = datetime.combine(day, time.min)
    return timezone.make_aware(value, timezone.get_current_timezone())


def _calendar_title(anchor: date, view: str) -> str:
    if view == "month":
        return anchor.strftime("%B %Y")
    start, end = visible_range(anchor, "week")
    return f"{start:%d %B %Y} – {(end - timedelta(days=1)):%d %B %Y}"


def _calendar_context(
    request: HttpRequest,
    view: str,
    anchor: date,
    events: Iterable[CalendarEvent],
    undated_count: int,
    truncation: SourceTruncation,
) -> dict[str, object]:
    event_list = list(events)
    today = timezone.localdate()
    rows = (
        build_week_grid(anchor, event_list, today)
        if view == "week"
        else build_month_grid(anchor, event_list, today)
    )
    return {
        "view": view,
        "anchor": anchor,
        "title": _calendar_title(anchor, view),
        "rows": rows,
        "weekday_names": (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ),
        "undated_count": undated_count,
        "truncation": truncation,
        "source_limit": CALENDAR_SOURCE_LIMIT,
        "prev_query": calendar_query_string(
            request.GET, view, shift_anchor(anchor, view, -1)
        ),
        "next_query": calendar_query_string(
            request.GET, view, shift_anchor(anchor, view, 1)
        ),
        "today_query": calendar_query_string(request.GET, view, today),
        "month_query": calendar_query_string(request.GET, "month", anchor),
        "week_query": calendar_query_string(request.GET, "week", anchor),
    }


def _local_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Calendar timestamp must be a datetime.")
    return timezone.localtime(value) if timezone.is_aware(value) else value


def _timestamp_records(
    queryset: QuerySet,
    *,
    kind: str,
    timestamp_field: str,
    value_fields: tuple[str, ...],
    label_builder: LabelBuilder,
    detail_builder: DetailBuilder,
    url_name: str,
    start: date,
    end: date,
) -> SourceResult:
    undated = queryset.filter(**{f"{timestamp_field}__isnull": True}).count()
    if start >= end:
        return [], undated, SourceTruncation()
    window = queryset.filter(
        **{
            f"{timestamp_field}__gte": _aware_midnight(start),
            f"{timestamp_field}__lt": _aware_midnight(end),
        }
    )
    values = window.order_by(timestamp_field, "pk").values(
        "pk", timestamp_field, *value_fields
    )
    rows, more_rows = materialize_source_rows(values, CALENDAR_SOURCE_LIMIT)
    records = [
        _timestamp_record(
            row,
            kind=kind,
            timestamp_field=timestamp_field,
            label_builder=label_builder,
            detail_builder=detail_builder,
            url_name=url_name,
        )
        for row in rows
    ]
    return records, undated, SourceTruncation(more_rows=more_rows)


def _timestamp_record(
    row: Mapping[str, object],
    *,
    kind: str,
    timestamp_field: str,
    label_builder: LabelBuilder,
    detail_builder: DetailBuilder,
    url_name: str,
) -> _EventRecord:
    timestamp = _local_timestamp(row[timestamp_field])
    label = label_builder(row)
    vm_name, node_name = detail_builder(row)
    event = CalendarEvent(
        day=timestamp.date(),
        kind=kind,
        label=label,
        url=reverse(url_name, args=[row["pk"]]),
        time_text=timestamp.strftime("%H:%M"),
        muted=False,
        approximate=False,
        sort_key=f"{timestamp:%H:%M:%S.%f}|{kind}|{row['pk']}",
    )
    return _EventRecord(event, vm_name, node_name)


def _date_sequence(start: date, end: date) -> Iterable[date]:
    for offset in range(max(0, (end - start).days)):
        yield start + timedelta(days=offset)


def _fixed_schedule_time(schedule: ParsedSchedule) -> time | None:
    """Return an exact wall-clock time, excluding ranges and repetitions."""
    alias = schedule.raw.strip().casefold()
    if schedule.time_text == alias and alias in {
        "daily",
        "weekly",
        "monthly",
        "yearly",
        "annually",
        "quarterly",
        "semiannually",
    }:
        return time()
    parts = schedule.time_text.split(":")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        return None
    values = [int(part) for part in parts]
    values.extend([0] * (3 - len(values)))
    try:
        return time(*values)
    except ValueError:
        return None


def _endpoint_zone(row: Mapping[str, object]) -> ZoneInfo | None:
    value = str(row.get("endpoint__iana_timezone") or "").strip()
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _converted_occurrence(
    day: date, schedule: ParsedSchedule, zone: ZoneInfo
) -> datetime | None:
    wall_time = _fixed_schedule_time(schedule)
    if wall_time is None:
        return None
    naive = datetime.combine(day, wall_time)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return timezone.localtime(first)


def _projected_days(start: date, end: date, has_zone: bool) -> Iterable[date]:
    padding = timedelta(days=2) if has_zone else timedelta()
    return _date_sequence(start - padding, end + padding)


def _formatted_occurrence_time(occurrence: datetime, schedule: ParsedSchedule) -> str:
    """Format a converted instant without discarding source clock precision."""
    has_seconds = len(schedule.time_text.split(":")) == 3 or occurrence.second != 0
    return occurrence.strftime("%H:%M:%S" if has_seconds else "%H:%M")


def _schedule_records(
    queryset: QuerySet,
    *,
    kind: str,
    schedule_field: str,
    value_fields: tuple[str, ...],
    order_fields: tuple[str, ...],
    label_builder: LabelBuilder,
    muted_builder: MutedBuilder,
    detail_builder: DetailBuilder,
    url_name: str,
    start: date,
    end: date,
) -> SourceResult:
    """Project scheduled objects onto the window under a fixed event budget.

    ``order_fields`` decides which objects win the budget: callers put active,
    enabled schedules first so stale or disabled jobs cannot crowd them out.
    Up to ``CALENDAR_SOURCE_LIMIT`` objects are fetched and projection stops
    once that many events exist; the remainder is reported, not dropped.
    """
    values = queryset.order_by(*order_fields).values(
        "pk", schedule_field, *value_fields
    )
    rows, more_rows = materialize_source_rows(values, CALENDAR_SOURCE_LIMIT)
    records: list[_EventRecord] = []
    omitted_events = 0
    unprojected = 0
    for index, row in enumerate(rows):
        available = CALENDAR_SOURCE_LIMIT - len(records)
        if available <= 0:
            unprojected = len(rows) - index
            break
        projected = _project_schedule_row(
            row,
            kind=kind,
            schedule_field=schedule_field,
            label_builder=label_builder,
            muted_builder=muted_builder,
            detail_builder=detail_builder,
            url_name=url_name,
            start=start,
            end=end,
        )
        records.extend(projected[:available])
        omitted_events += max(0, len(projected) - available)
    truncation = SourceTruncation(
        omitted_events=omitted_events,
        unprojected_objects=unprojected,
        more_rows=more_rows,
    )
    return records, 0, truncation


def _project_schedule_row(
    row: Mapping[str, object],
    *,
    kind: str,
    schedule_field: str,
    label_builder: LabelBuilder,
    muted_builder: MutedBuilder,
    detail_builder: DetailBuilder,
    url_name: str,
    start: date,
    end: date,
) -> list[_EventRecord]:
    schedule = parse(row.get(schedule_field))  # type: ignore[arg-type]
    vm_name, node_name = detail_builder(row)
    zone = _endpoint_zone(row)
    records: list[_EventRecord] = []
    for source_day in _projected_days(start, end, zone is not None):
        if not schedule.matches(source_day):
            continue
        occurrence = _converted_occurrence(source_day, schedule, zone) if zone else None
        event_day = occurrence.date() if occurrence else source_day
        if not start <= event_day < end:
            continue
        time_text = (
            _formatted_occurrence_time(occurrence, schedule)
            if occurrence
            else schedule.time_text
        )
        records.append(
            _EventRecord(
                CalendarEvent(
                    day=event_day,
                    kind=kind,
                    label=label_builder(row),
                    url=reverse(url_name, args=[row["pk"]]),
                    time_text=time_text,
                    muted=muted_builder(row),
                    approximate=schedule.approximate or occurrence is None,
                    sort_key=f"{time_text}|{kind}|{row['pk']}",
                ),
                vm_name,
                node_name,
            )
        )
    return records


def _backup_label(row: Mapping[str, object]) -> str:
    suffix = row.get("volume_id") or "Backup"
    return f"{row.get('virtual_machine__name', '')} — {suffix}"


def _snapshot_label(row: Mapping[str, object]) -> str:
    return f"{row.get('virtual_machine__name', '')} — {row.get('name', '')}"


def _replication_label(row: Mapping[str, object]) -> str:
    return f"{row.get('virtual_machine__name', '')} — {row.get('replication_id', '')}"


def _routine_label(row: Mapping[str, object]) -> str:
    return str(row.get("job_id", ""))


def _backup_details(row: Mapping[str, object]) -> tuple[str, str]:
    return str(row.get("virtual_machine__name", "")), str(
        row.get("virtual_machine__device__name") or ""
    )


def _snapshot_details(row: Mapping[str, object]) -> tuple[str, str]:
    return str(row.get("virtual_machine__name", "")), str(row.get("node") or "")


def _replication_details(row: Mapping[str, object]) -> tuple[str, str]:
    return str(row.get("virtual_machine__name", "")), str(
        row.get("target") or row.get("proxmox_node__name") or ""
    )


def _routine_details(row: Mapping[str, object]) -> tuple[str, str]:
    return "", str(row.get("node__name") or "All nodes")


def _replication_muted(row: Mapping[str, object]) -> bool:
    return bool(row.get("disable")) or row.get("status") == "stale"


def _routine_muted(row: Mapping[str, object]) -> bool:
    return not bool(row.get("enabled")) or row.get("status") == "stale"


class DataProtectionCalendarMixin:
    """Add a calendar derived from an ObjectListView's filtered queryset."""

    calendar_kind = ""
    calendar_timestamp_field: str | None = None
    calendar_schedule_field: str | None = None
    calendar_order_fields: tuple[str, ...] = ("pk",)
    calendar_value_fields: tuple[str, ...] = ()
    calendar_label_builder: LabelBuilder
    calendar_muted_builder: MutedBuilder = staticmethod(lambda row: False)
    calendar_detail_builder: DetailBuilder = staticmethod(lambda row: ("", ""))
    calendar_url_name = ""

    def get_calendar_records(self, start: date, end: date) -> SourceResult:
        """Extract events without using the paginated table."""
        if self.calendar_timestamp_field:
            return _timestamp_records(
                self.queryset,
                kind=self.calendar_kind,
                timestamp_field=self.calendar_timestamp_field,
                value_fields=self.calendar_value_fields,
                label_builder=self.calendar_label_builder,
                detail_builder=self.calendar_detail_builder,
                url_name=self.calendar_url_name,
                start=start,
                end=end,
            )
        return _schedule_records(
            self.queryset,
            kind=self.calendar_kind,
            schedule_field=self.calendar_schedule_field or "schedule",
            value_fields=self.calendar_value_fields,
            order_fields=self.calendar_order_fields,
            label_builder=self.calendar_label_builder,
            muted_builder=self.calendar_muted_builder,
            detail_builder=self.calendar_detail_builder,
            url_name=self.calendar_url_name,
            start=start,
            end=end,
        )

    def get_extra_context(self, request: HttpRequest) -> dict[str, object]:
        """Merge calendar context into the list view's existing context."""
        parent = super().get_extra_context(request)  # type: ignore[misc]
        view, anchor = _calendar_state(request)
        start, end = visible_range(anchor, view)
        records, undated, truncation = self.get_calendar_records(start, end)
        return {
            **parent,
            "calendar": _calendar_context(
                request,
                view,
                anchor,
                (record.event for record in records),
                undated,
                truncation,
            ),
        }


def _selected_kinds(form: DataProtectionFilterForm) -> set[str]:
    if not form.is_bound or not form.data.get("kinds_submitted"):
        return set(KIND_FIELDS)
    return {
        kind
        for kind, field_name in KIND_FIELDS.items()
        if form.cleaned_data.get(field_name)
    }


def _selected_ids(form: DataProtectionFilterForm, field: str) -> set[int]:
    values = form.cleaned_data.get(field)
    return {obj.pk for obj in values} if values is not None else set()


def _filter_vm_queryset(
    queryset: QuerySet,
    form: DataProtectionFilterForm,
    *,
    snapshot: bool = False,
    replication: bool = False,
) -> QuerySet:
    cluster_ids = _selected_ids(form, "cluster")
    node_ids = _selected_ids(form, "node")
    vm_ids = _selected_ids(form, "virtual_machine")
    if cluster_ids:
        native_clusters = ProxmoxCluster.objects.filter(pk__in=cluster_ids).values_list(
            "netbox_cluster_id", flat=True
        )
        queryset = queryset.filter(virtual_machine__cluster_id__in=native_clusters)
    if node_ids:
        queryset = queryset.filter(
            _node_query(node_ids, snapshot=snapshot, replication=replication)
        )
    return queryset.filter(virtual_machine_id__in=vm_ids) if vm_ids else queryset


def _node_query(node_ids: set[int], *, snapshot: bool, replication: bool) -> Q:
    """Match rows for the selected nodes without mixing their identities.

    Every fallback predicate keeps a node's name paired with that node's own
    cluster or endpoint, so selecting ``node1`` on endpoint A and ``node2`` on
    endpoint B never matches ``node1`` rows on endpoint B.
    """
    nodes = ProxmoxNode.objects.filter(pk__in=node_ids).values(
        "pk", "name", "endpoint_id", "proxmox_cluster__netbox_cluster_id"
    )
    query = Q(virtual_machine__device_id__in=_node_device_ids(node_ids))
    for node in nodes:
        query |= _node_fallback_query(node, snapshot=snapshot, replication=replication)
    return query


def _node_device_ids(node_ids: set[int]) -> QuerySet:
    return ProxmoxNode.objects.filter(
        pk__in=node_ids, netbox_device_id__isnull=False
    ).values_list("netbox_device_id", flat=True)


def _node_fallback_query(
    node: Mapping[str, object], *, snapshot: bool, replication: bool
) -> Q:
    query = Q(pk__in=[])
    cluster_id = node.get("proxmox_cluster__netbox_cluster_id")
    if snapshot and cluster_id is not None:
        query |= Q(node=node["name"], virtual_machine__cluster_id=cluster_id)
    if replication:
        query |= Q(proxmox_node_id=node["pk"]) | Q(
            target=node["name"], endpoint_id=node["endpoint_id"]
        )
    return query


def _filter_routines(queryset: QuerySet, form: DataProtectionFilterForm) -> QuerySet:
    cluster_ids = _selected_ids(form, "cluster")
    node_ids = _selected_ids(form, "node")
    vm_ids = _selected_ids(form, "virtual_machine")
    if cluster_ids:
        queryset = queryset.filter(
            Q(node__proxmox_cluster_id__in=cluster_ids)
            | Q(
                node__isnull=True,
                endpoint__proxmox_clusters__id__in=cluster_ids,
            )
        ).distinct()
    if node_ids:
        endpoint_ids = ProxmoxNode.objects.filter(pk__in=node_ids).values_list(
            "endpoint_id", flat=True
        )
        queryset = queryset.filter(
            Q(node_id__in=node_ids) | Q(node__isnull=True, endpoint_id__in=endpoint_ids)
        )
    return queryset.none() if vm_ids else queryset


def _event_bounds(
    form: DataProtectionFilterForm, visible_start: date, visible_end: date
) -> tuple[date, date]:
    selected_start = form.cleaned_data.get("date_from")
    selected_end = form.cleaned_data.get("date_to")
    start = max(visible_start, selected_start) if selected_start else visible_start
    end = visible_end
    if selected_end and selected_end < visible_end:
        end = selected_end + timedelta(days=1)
    return start, end


def _anchor_for_range(
    anchor: date,
    view: str,
    form: DataProtectionFilterForm,
    form_valid: bool,
) -> date:
    """Move a stale navigation anchor into a complete valid date range."""
    if not form_valid:
        return anchor
    selected_start = form.cleaned_data.get("date_from")
    selected_end = form.cleaned_data.get("date_to")
    if not selected_start or not selected_end:
        return anchor
    visible_start, visible_end = visible_range(anchor, view)
    intersects = visible_start <= selected_end and selected_start < visible_end
    return anchor if intersects else selected_start


def _restrict_form_choices(
    form: DataProtectionFilterForm, request: HttpRequest
) -> None:
    form.fields["cluster"].queryset = ProxmoxCluster.objects.restrict(
        request.user, "view"
    )
    form.fields["node"].queryset = ProxmoxNode.objects.restrict(request.user, "view")
    form.fields["virtual_machine"].queryset = VirtualMachine.objects.restrict(
        request.user, "view"
    )


def _may_view(user: object, model: type) -> bool:
    has_perm = getattr(user, "has_perm", None)
    return bool(
        callable(has_perm) and has_perm(get_permission_for_model(model, "view"))
    )


class DataProtectionView(ConditionalLoginRequiredMixin, View):
    """Render the permission-restricted combined data-protection calendar."""

    template_name = "netbox_proxbox/data_protection.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Apply filters, build all permitted events, and render the page."""
        form = DataProtectionFilterForm(request.GET)
        _restrict_form_choices(form, request)
        form_valid = form.is_valid()
        view, anchor = _calendar_state(request, form.cleaned_data.get("date_from"))
        anchor = _safe_anchor(_anchor_for_range(anchor, view, form, form_valid))
        visible_start, visible_end = visible_range(anchor, view)
        start, end = _event_bounds(form, visible_start, visible_end)
        records, undated, truncation = self._records(request, form, start, end)
        ordered = sorted(
            records, key=lambda record: (record.event.day, record.event.sort_key)
        )
        return render(
            request,
            self.template_name,
            {
                "filter_form": form,
                "calendar": _calendar_context(
                    request,
                    view,
                    anchor,
                    (record.event for record in ordered),
                    undated,
                    truncation,
                ),
                "event_rows": ordered[:EVENT_TABLE_LIMIT],
                "event_rows_total": len(ordered),
                "event_rows_limit": EVENT_TABLE_LIMIT,
            },
        )

    def _records(
        self,
        request: HttpRequest,
        form: DataProtectionFilterForm,
        start: date,
        end: date,
    ) -> SourceResult:
        selected = _selected_kinds(form)
        records: list[_EventRecord] = []
        undated = 0
        truncation = SourceTruncation()
        for kind, model, builder in self._sources(request, form, start, end):
            if kind not in selected or not _may_view(request.user, model):
                continue
            source_records, source_undated, source_truncation = builder()
            records.extend(source_records)
            undated += source_undated
            truncation = truncation.merge(source_truncation)
        return records, undated, truncation

    def _sources(
        self,
        request: HttpRequest,
        form: DataProtectionFilterForm,
        start: date,
        end: date,
    ) -> tuple[tuple[str, type, Callable[[], SourceResult]], ...]:
        backups = _filter_vm_queryset(
            VMBackup.objects.restrict(request.user, "view"), form
        )
        snapshots = _filter_vm_queryset(
            VMSnapshot.objects.restrict(request.user, "view"), form, snapshot=True
        )
        replications = _filter_vm_queryset(
            Replication.objects.restrict(request.user, "view"), form, replication=True
        )
        routines = _filter_routines(
            BackupRoutine.objects.restrict(request.user, "view"), form
        )
        return (
            ("backup", VMBackup, lambda: self._backups(backups, start, end)),
            ("snapshot", VMSnapshot, lambda: self._snapshots(snapshots, start, end)),
            (
                "replication",
                Replication,
                lambda: self._replications(replications, start, end),
            ),
            (
                "routine",
                BackupRoutine,
                lambda: self._routines(routines, start, end),
            ),
        )

    @staticmethod
    def _backups(queryset: QuerySet, start: date, end: date) -> SourceResult:
        return _timestamp_records(
            queryset,
            kind="backup",
            timestamp_field="creation_time",
            value_fields=(
                "virtual_machine__name",
                "virtual_machine__device__name",
                "volume_id",
            ),
            label_builder=_backup_label,
            detail_builder=_backup_details,
            url_name="plugins:netbox_proxbox:vmbackup",
            start=start,
            end=end,
        )

    @staticmethod
    def _snapshots(queryset: QuerySet, start: date, end: date) -> SourceResult:
        return _timestamp_records(
            queryset,
            kind="snapshot",
            timestamp_field="snaptime",
            value_fields=("virtual_machine__name", "name", "node"),
            label_builder=_snapshot_label,
            detail_builder=_snapshot_details,
            url_name="plugins:netbox_proxbox:vmsnapshot",
            start=start,
            end=end,
        )

    @staticmethod
    def _replications(queryset: QuerySet, start: date, end: date) -> SourceResult:
        return _schedule_records(
            queryset,
            kind="replication",
            schedule_field="schedule",
            value_fields=(
                "virtual_machine__name",
                "replication_id",
                "target",
                "proxmox_node__name",
                "disable",
                "status",
                "endpoint__iana_timezone",
            ),
            order_fields=REPLICATION_ORDER_FIELDS,
            label_builder=_replication_label,
            muted_builder=_replication_muted,
            detail_builder=_replication_details,
            url_name="plugins:netbox_proxbox:replication",
            start=start,
            end=end,
        )

    @staticmethod
    def _routines(queryset: QuerySet, start: date, end: date) -> SourceResult:
        return _schedule_records(
            queryset,
            kind="routine",
            schedule_field="schedule",
            value_fields=(
                "job_id",
                "node__name",
                "enabled",
                "status",
                "endpoint__iana_timezone",
            ),
            order_fields=ROUTINE_ORDER_FIELDS,
            label_builder=_routine_label,
            muted_builder=_routine_muted,
            detail_builder=_routine_details,
            url_name="plugins:netbox_proxbox:backuproutine",
            start=start,
            end=end,
        )
