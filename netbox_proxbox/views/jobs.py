"""A Proxbox-only view of the core ``Job`` list.

The **Sync Jobs** menu entry used to point straight at NetBox's ``core:job_list``,
which lists every job in the instance -- reports, scripts, and every other
plugin's background work -- leaving operators to pick the Proxbox rows out by
eye. This narrows that page to Proxbox sync jobs and nothing else.

It deliberately *subclasses* core's ``JobListView`` instead of rebuilding one:
the filterset, filter form, table, and export action are the ones operators
already know, and inheriting them means a NetBox release that adds a Job filter
adds it here too.
"""

from __future__ import annotations

import django_tables2 as tables
from core.models import Job
from core.tables import JobTable
from core.views import JobListView
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from netbox.object_actions import BulkExport

from netbox_proxbox.bug_report import is_reportable_status
from netbox_proxbox.jobs import proxbox_sync_job_q

__all__ = (
    "ProxboxJobListView",
    "ProxboxJobTable",
)


class ProxboxJobTable(JobTable):
    """Core's job table plus a bug-report affordance on unhealthy rows."""

    bug_report = tables.Column(
        verbose_name=_("Bug Report"),
        empty_values=(),
        orderable=False,
    )

    class Meta(JobTable.Meta):
        model = Job
        fields = (*JobTable.Meta.fields, "bug_report")
        # ``status`` is already one of core's defaults; only the new column is added.
        default_columns = (*JobTable.Meta.default_columns, "bug_report")

    def render_bug_report(self, record):
        """Link errored/failed/unknown rows to the job page that hosts the modal.

        The modal itself is deliberately *not* rendered per row. Building its
        context needs ``data`` and ``log_entries``; ``data`` is deferred by the
        queryset precisely so a long list does not drag every job's payload out
        of the database, and a page of 50 rows would emit 50 modals and 50
        inline scripts. The detail page already carries the full modal, so the
        list only has to get the operator there.
        """
        if not is_reportable_status(record.status):
            return "—"
        return format_html(
            '<a href="{}" class="btn btn-sm btn-outline-danger" '
            'title="{}"><i class="mdi mdi-bug" aria-hidden="true"></i> {}</a>',
            record.get_absolute_url(),
            _("Open this job and copy an anonymized bug report"),
            _("Bug report"),
        )

    def value_bug_report(self, record):
        """Plain-text counterpart used by CSV/export.

        ``Table.as_values()`` falls back to ``render_<name>`` when no
        ``value_<name>`` exists, which would write the rendered ``<a>`` element
        into a spreadsheet cell. Export wants the fact, not the button.
        """
        return "reportable" if is_reportable_status(record.status) else ""


class ProxboxJobListView(JobListView):
    """The core job list, filtered down to Proxbox sync jobs.

    ``defer("data")`` composes with the ``data__has_key`` lookup in the filter:
    deferral only affects the ``SELECT`` column list, while the lookup is a
    ``WHERE`` clause, so the JSON payload is still queryable without being
    fetched for every row.
    """

    queryset = Job.objects.defer("data").filter(proxbox_sync_job_q())
    table = ProxboxJobTable
    # Export only. Core's list offers bulk delete, but its success redirect
    # returns to ``core:job_list`` -- deleting from this page would bounce the
    # operator out to the unfiltered list they came here to avoid.
    actions = (BulkExport,)
