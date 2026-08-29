"""Read-only REST listing of Proxbox sync jobs, filtered in SQL.

The plugin has no job model. A sync is a core ``core.Job`` row whose ``data``
carries a ``proxbox_sync`` block, and ``/api/core/jobs/`` cannot filter on
``data`` — which is the only reliable way to recognise one, because a run
scheduled with a custom ``job_name`` keeps that name verbatim and no name filter
can find it.

The UI already solves this: :func:`netbox_proxbox.jobs.proxbox_sync_job_q`
pushes the identity predicate into SQL and ``views/jobs.ProxboxJobListView``
narrows core's job list with it. Nothing equivalent existed over REST, so every
API consumer had to fetch core job rows and re-apply the predicate itself. On a
production instance that is roughly 29 sync jobs among 24,000 core jobs, each
row carrying its full ``log_entries`` — about 140 MB of transfer to find a few
dozen rows.

This view is that endpoint. It inherits core's own ``JobFilterSet``, so every
core job filter keeps working and a NetBox release that adds one adds it here
too, and layers on the filters that live inside ``data``.

Three of those filters carry semantics that are **not** obvious from the field
names, and they are deliberately the same ones ``nbx proxbox jobs`` documents —
one question must not get two different answers depending on who asks:

* An **empty endpoint list means "every endpoint"**. That is what the schedule
  API stores when the caller names none, and such a run really did sync them
  all, so it matches any endpoint-, cluster-, or node-scoped query.
* A run recorded as ``sync_types: ["all"]`` — or with no types recorded, whose
  documented default is ``all`` — **covers every requested sync type**.
* An **empty VM list does not** mean "every VM". A run that targeted no
  particular virtual machine is not a match for a VM-scoped query; it is the
  absence of that scope, not a wildcard.
"""

from __future__ import annotations

from typing import Any

import django_filters
from core.filtersets import JobFilterSet
from core.models import Job
from django.db.models import Q, QuerySet
from netbox.api.viewsets import NetBoxReadOnlyModelViewSet
from utilities.filters import MultiValueCharFilter, MultiValueNumberFilter

from netbox_proxbox.api.serializers.sync_jobs import (
    ProxboxSyncJobListSerializer,
    ProxboxSyncJobSerializer,
)
from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import proxbox_sync_job_q

__all__ = (
    "ProxboxSyncJobFilterSet",
    "ProxboxSyncJobViewSet",
)

#: Root of the params block written by ``ProxboxSyncJob.enqueue``.
_PARAMS = "data__proxbox_sync__params"


def _scope_is_open(field: str) -> Q:
    """Match rows whose scope list is absent, JSON null, or explicitly empty.

    All three mean the same thing for endpoint scope — "no endpoint was named,
    so the run covered every one" — but they are three different states in
    jsonb, and a filter that spells only one of them silently drops the others.
    """
    return (
        Q(**{f"{_PARAMS}__{field}__isnull": True})
        | Q(**{f"{_PARAMS}__{field}": None})
        | Q(**{f"{_PARAMS}__{field}": []})
    )


class ProxboxSyncJobFilterSet(JobFilterSet):
    """Core's job filters plus the ones that live inside ``job.data``.

    Subclassing rather than reimplementing means status, name, queue, user,
    object type, id and the four timestamp ranges all keep working exactly as
    they do on ``/api/core/jobs/``, and stay in step with NetBox.
    """

    sync_type = MultiValueCharFilter(
        method="filter_sync_type",
        label="Proxbox sync type slug (a run recorded as 'all' matches any)",
    )
    proxmox_endpoint_id = MultiValueNumberFilter(
        method="filter_proxmox_endpoint",
        label="Proxmox endpoint PK the run covered (an open scope matches any)",
    )
    cluster_id = MultiValueNumberFilter(
        method="filter_cluster",
        label="Proxmox cluster PK, matched through the cluster's endpoint",
    )
    node_id = MultiValueNumberFilter(
        method="filter_node",
        label="Proxmox node PK, matched through the node's endpoint",
    )
    netbox_vm_id = MultiValueNumberFilter(
        method="filter_netbox_vm",
        label="NetBox virtual machine PK the run targeted",
    )
    run_id = MultiValueCharFilter(
        method="filter_run_id",
        label="Proxbox run identifier recorded in the job parameters",
    )
    batch_object_type = MultiValueCharFilter(
        method="filter_batch_object_type",
        label="Batch object type recorded in the job parameters",
    )
    errored = django_filters.BooleanFilter(
        method="filter_errored",
        label="Runs that failed, or that finished while recording an error",
    )

    class Meta(JobFilterSet.Meta):
        model = Job

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _string_list_contains(field: str, values: list[Any]) -> Q:
        """Match a jsonb array of strings holding any of ``values``.

        The plugin serialises every id in these lists as a **string**
        (``_serialize_sync_params`` casts with ``str()``), so a numeric filter
        value has to be cast the same way before the containment test. Matching
        on the integer would compile to ``@> '[5]'`` and never hit ``["5"]``.
        """
        query = Q()
        for value in values:
            query |= Q(**{f"{_PARAMS}__{field}__contains": [str(value)]})
        return query

    def _filter_endpoint_ids(
        self, queryset: QuerySet, endpoint_ids: list[int]
    ) -> QuerySet:
        if not endpoint_ids:
            # The caller named a scope that resolves to no endpoint at all, so
            # nothing can match it. Returning the unfiltered queryset here would
            # answer a narrow question with every row.
            return queryset.none()
        return queryset.filter(
            self._string_list_contains("proxmox_endpoint_ids", endpoint_ids)
            | _scope_is_open("proxmox_endpoint_ids")
        )

    # -- filter methods --------------------------------------------------

    def filter_sync_type(
        self, queryset: QuerySet, name: str, value: list[str]
    ) -> QuerySet:
        """Match runs that included any of the requested stages.

        ``all`` covers everything, and so does a run with no recorded types —
        the plugin's own default. The legacy singular ``sync_type`` key is
        honoured for rows written before ``sync_types`` existed.
        """
        values = [str(item).strip() for item in value if str(item).strip()]
        if not values:
            return queryset
        query = self._string_list_contains("sync_types", values)
        query |= Q(**{f"{_PARAMS}__sync_types__contains": [SyncTypeChoices.ALL]})
        # "No recorded types" only means "all" when the LEGACY singular key is
        # absent too. A row written before ``sync_types`` existed carries just
        # ``sync_type: "storage"`` — treating its missing ``sync_types`` as an
        # open scope made that row match a query for every other stage.
        query |= _scope_is_open("sync_types") & (
            Q(**{f"{_PARAMS}__sync_type__isnull": True})
            | Q(**{f"{_PARAMS}__sync_type": None})
        )
        for item in values:
            query |= Q(**{f"{_PARAMS}__sync_type": item})
        query |= Q(**{f"{_PARAMS}__sync_type": SyncTypeChoices.ALL})
        return queryset.filter(query)

    def filter_proxmox_endpoint(
        self, queryset: QuerySet, name: str, value: list[int]
    ) -> QuerySet:
        return self._filter_endpoint_ids(queryset, [int(item) for item in value])

    def filter_cluster(
        self, queryset: QuerySet, name: str, value: list[int]
    ) -> QuerySet:
        from netbox_proxbox.models import ProxmoxCluster

        endpoint_ids = list(
            ProxmoxCluster.objects.filter(pk__in=list(value))
            .values_list("endpoint_id", flat=True)
            .distinct()
        )
        return self._filter_endpoint_ids(queryset, [pk for pk in endpoint_ids if pk])

    def filter_node(self, queryset: QuerySet, name: str, value: list[int]) -> QuerySet:
        from netbox_proxbox.models import ProxmoxNode

        endpoint_ids = list(
            ProxmoxNode.objects.filter(pk__in=list(value))
            .values_list("endpoint_id", flat=True)
            .distinct()
        )
        return self._filter_endpoint_ids(queryset, [pk for pk in endpoint_ids if pk])

    def filter_netbox_vm(
        self, queryset: QuerySet, name: str, value: list[int]
    ) -> QuerySet:
        """Match runs that targeted one of the given virtual machines.

        Unlike the endpoint scope, an empty VM list is *not* a wildcard: a run
        that targeted no particular VM is not an answer to "which runs touched
        VM 199?".
        """
        if not value:
            return queryset
        return queryset.filter(self._string_list_contains("netbox_vm_ids", list(value)))

    def filter_run_id(
        self, queryset: QuerySet, name: str, value: list[str]
    ) -> QuerySet:
        values = [str(item).strip() for item in value if str(item).strip()]
        if not values:
            return queryset
        query = Q()
        for item in values:
            query |= Q(**{f"{_PARAMS}__run_id": item})
        return queryset.filter(query)

    def filter_batch_object_type(
        self, queryset: QuerySet, name: str, value: list[str]
    ) -> QuerySet:
        values = [str(item).strip() for item in value if str(item).strip()]
        if not values:
            return queryset
        query = Q()
        for item in values:
            query |= Q(**{f"{_PARAMS}__batch_object_type": item})
        return queryset.filter(query)

    def filter_errored(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        """Failure statuses **plus** runs that finished while recording an error.

        A sync can end ``completed`` with a stage error in ``error``, and that
        is precisely the row an operator triaging a failure is looking for, so
        a status-only filter would hide it.
        """
        from core.choices import JobStatusChoices

        failed = Q(
            status__in=[JobStatusChoices.STATUS_ERRORED, JobStatusChoices.STATUS_FAILED]
        )
        recorded = ~Q(error="") & Q(error__isnull=False)
        if value:
            return queryset.filter(failed | recorded)
        return queryset.exclude(failed | recorded)


class ProxboxSyncJobViewSet(NetBoxReadOnlyModelViewSet):
    """Proxbox sync jobs — core job rows this plugin owns, filtered in SQL.

    Read-only by construction: scheduling stays on ``sync/schedule/`` and
    cancelling on ``jobs/{pk}/cancel/``, each with its own permission gate.
    ``NetBoxReadOnlyModelViewSet`` applies NetBox's object permissions, so a
    caller sees exactly the jobs ``core.view_job`` allows them to see.

    ``log_entries`` is omitted from list responses. It is unbounded — a single
    full-sync row on a production instance runs to 130 KB — and a list view
    almost never needs it. Ask for it explicitly with
    ``?include_log_entries=true``; the detail route always includes it.
    """

    queryset = Job.objects.filter(proxbox_sync_job_q())
    serializer_class = ProxboxSyncJobSerializer
    filterset_class = ProxboxSyncJobFilterSet

    def get_serializer_class(self):
        """Return the log-free serializer for list responses unless asked.

        Every attribute here is read defensively. Schema generation instantiates
        the view with no bound ``request`` and asks it for a serializer, so
        reaching straight for ``self.request.query_params`` raises
        ``AttributeError`` and takes the whole instance's ``/api/schema/`` down —
        a failure nowhere near this endpoint, caused by it.
        """
        if getattr(self, "action", None) != "list":
            return ProxboxSyncJobSerializer
        request = getattr(self, "request", None)
        params = getattr(request, "query_params", None) or {}
        requested = str(params.get("include_log_entries", "")).strip().lower()
        if requested in ("1", "true", "yes", "on"):
            return ProxboxSyncJobSerializer
        return ProxboxSyncJobListSerializer
