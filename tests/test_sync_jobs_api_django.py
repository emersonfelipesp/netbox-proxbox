"""Real-database behaviour of the Proxbox sync-jobs endpoint.

The whole point of this endpoint is that the filtering happens in **SQL**, over
a jsonb column, with semantics that are easy to state and easy to get subtly
wrong: an open endpoint scope means "every endpoint", ``all`` covers every sync
type, and an empty VM list is not a wildcard. None of that can be proven against
the mocked suite — jsonb containment, key-absence and JSON-null are database
behaviours, and a stub would only echo back whatever the filter code believes.

So each test states the rule **in Python, from the documented semantics**, and
compares that expectation against what the database actually returns. The rule
is the oracle; the ``FilterSet`` is what is under test. Deriving the expectation
by calling the filter would prove only that the filter equals itself.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from core.models import Job  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.http import QueryDict  # noqa: E402
from django.test import TestCase  # noqa: E402

from netbox_proxbox.api.serializers.sync_jobs import (  # noqa: E402
    ProxboxSyncJobListSerializer,
    ProxboxSyncJobSerializer,
)
from netbox_proxbox.api.sync_jobs import (  # noqa: E402
    ProxboxSyncJobFilterSet,
    ProxboxSyncJobViewSet,
)
from netbox_proxbox.jobs import is_proxbox_sync_job  # noqa: E402


def _params(**overrides: object) -> dict:
    """Build a ``proxbox_sync`` payload; only the named keys are present."""
    return {"proxbox_sync": {"params": dict(overrides)}}


# label -> (name, queue_name, data). The labels are what the assertions talk
# about, so a failure names the row rather than an index.
_ROWS: dict[str, tuple[str, str, object]] = {
    # Endpoint scope, in all four states the plugin can write.
    "named-5-11": (
        "Proxbox Sync: Full update",
        "default",
        _params(proxmox_endpoint_ids=["5", "11"], sync_types=["all"]),
    ),
    "named-7": (
        "Proxbox Sync: Full update",
        "default",
        _params(proxmox_endpoint_ids=["7"], sync_types=["storage", "sdn"]),
    ),
    "open-empty-list": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=[], sync_types=["all"]),
    ),
    "open-key-absent": ("Proxbox Sync", "default", _params(sync_types=["all"])),
    "open-json-null": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=None, sync_types=["all"]),
    ),
    # Sync-type scope.
    "types-storage-only": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=["5"], sync_types=["storage"]),
    ),
    "types-absent": ("Proxbox Sync", "default", _params(proxmox_endpoint_ids=["5"])),
    "types-legacy-singular": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=["5"], sync_type="storage"),
    ),
    # VM-targeted run.
    "vm-199": (
        "Proxbox Sync: Virtual machine 199",
        "default",
        _params(
            proxmox_endpoint_ids=["5"],
            netbox_vm_ids=["199"],
            sync_types=["virtual-machines"],
        ),
    ),
    "vm-none": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=["5"], netbox_vm_ids=[], sync_types=["all"]),
    ),
    # Identifiers.
    "run-id-abc": (
        "Proxbox Sync",
        "default",
        _params(proxmox_endpoint_ids=["5"], sync_types=["all"], run_id="abc-123"),
    ),
    "batch-cluster": (
        "Proxbox Sync",
        "default",
        _params(
            proxmox_endpoint_ids=["5"],
            sync_types=["all"],
            batch_object_type="virtualization.cluster",
        ),
    ),
    # A Proxbox row identified by NAME alone, carrying no `data` at all — the
    # shape every job predating the params block has. It recorded no scope, so
    # every scope filter must treat it as open.
    "name-only-no-data": ("Proxbox Sync", "default", None),
    # Not Proxbox at all — these must never appear in any result.
    "foreign-report": ("Report Run", "default", None),
    "foreign-gpon": ("Sync GPON ONTs", "default", {"gpon_sync": {}}),
    "foreign-near-miss": ("Proxbox Sync Extra", "default", None),
}

_FAILED_ROWS = {"named-7"}  # gets status=errored
_ERROR_TEXT_ROWS = {"named-5-11"}  # completed, but records an error


def _row_params(label: str) -> dict:
    data = _ROWS[label][2]
    if not isinstance(data, dict):
        return {}
    block = data.get("proxbox_sync")
    if not isinstance(block, dict):
        return {}
    params = block.get("params")
    return params if isinstance(params, dict) else {}


class ProxboxSyncJobEndpointTests(TestCase):
    """SQL filtering over ``job.data``, checked against the documented rules."""

    @classmethod
    def setUpTestData(cls) -> None:
        object_type = ContentType.objects.get_for_model(Job)
        cls.jobs: dict[str, Job] = {}
        for label, (name, queue_name, data) in _ROWS.items():
            cls.jobs[label] = Job.objects.create(
                object_type=object_type,
                job_id=uuid.uuid4(),
                name=name,
                status="errored" if label in _FAILED_ROWS else "completed",
                queue_name=queue_name,
                data=data,
                error="Stage 'sdn' failed" if label in _ERROR_TEXT_ROWS else "",
            )

    # -- helpers ---------------------------------------------------------

    def _proxbox_labels(self) -> set[str]:
        """Labels the plugin's own predicate calls Proxbox sync jobs.

        The predicate reads **attributes**, so it has to be asked about the
        saved ``Job`` rows — handing it dicts silently answers ``False`` for
        every row and turns this oracle into an empty set, which would let a
        broken filter pass by agreeing with nothing.
        """
        return {label for label, job in self.jobs.items() if is_proxbox_sync_job(job)}

    def _filter(self, **query: object) -> set[str]:
        """Run the filterset over the base queryset, returning row labels.

        Parameters go through a ``QueryDict`` rather than a plain dict because
        that is what a real request supplies: NetBox maps `CharField` to
        `MultiValueCharFilter`, whose `MultipleChoiceField` reads values with
        `getlist`. A plain dict has no `getlist`, so a bare string arrives where
        a list is expected, the form is invalid, and the filterset quietly
        returns nothing — a test harness that fails for a reason the endpoint
        would never hit.
        """
        data = QueryDict(mutable=True)
        for key, value in query.items():
            if isinstance(value, bool):
                data[key] = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                for item in value:
                    data.appendlist(key, str(item))
            else:
                data[key] = str(value)

        by_pk = {job.pk: label for label, job in self.jobs.items()}
        queryset = ProxboxSyncJobViewSet.queryset.all()
        filterset = ProxboxSyncJobFilterSet(data, queryset=queryset)
        assert filterset.is_valid(), filterset.errors
        return {by_pk[job.pk] for job in filterset.qs if job.pk in by_pk}

    # -- the base queryset ------------------------------------------------

    def test_base_queryset_is_exactly_what_the_predicate_accepts(self) -> None:
        """The endpoint must show every Proxbox job and no other plugin's.

        The Python predicate is the oracle here, exactly as in the existing
        ``proxbox_sync_job_q`` parity test — this asserts the view actually
        wires that ``Q`` in, rather than re-deriving the rule.
        """
        self.assertEqual(self._filter(), self._proxbox_labels())
        self.assertNotIn("foreign-report", self._filter())
        self.assertNotIn("foreign-gpon", self._filter())
        self.assertNotIn("foreign-near-miss", self._filter())

    # -- endpoint / cluster / node scope ----------------------------------

    def test_endpoint_filter_matches_named_and_open_scopes(self) -> None:
        """Rule: a run matches endpoint N if it named N, or named none at all.

        Expectation is computed from that sentence over the row definitions.
        """
        wanted = 5
        expected = {
            label
            for label in self._proxbox_labels()
            if str(wanted) in (_row_params(label).get("proxmox_endpoint_ids") or [])
            or not _row_params(label).get("proxmox_endpoint_ids")
        }

        self.assertEqual(self._filter(proxmox_endpoint_id=[wanted]), expected)
        # All three open states are in that expectation, and none may be lost.
        self.assertLessEqual(
            {"open-empty-list", "open-key-absent", "open-json-null"}, expected
        )

    def test_endpoint_filter_excludes_a_run_scoped_elsewhere(self) -> None:
        matched = self._filter(proxmox_endpoint_id=[5])
        self.assertNotIn("named-7", matched)
        self.assertIn("named-5-11", matched)

    def test_endpoint_ids_are_matched_as_strings_not_integers(self) -> None:
        """The plugin stores every id as a string, so ``@> '[5]'`` never hits.

        This is the defect a numeric containment test would ship silently: the
        filter would simply return only the open-scope rows and look plausible.
        """
        self.assertIn("named-5-11", self._filter(proxmox_endpoint_id=[5]))
        self.assertIn("named-7", self._filter(proxmox_endpoint_id=[7]))

    def test_endpoint_filter_accepts_several_endpoints(self) -> None:
        self.assertLessEqual(
            {"named-5-11", "named-7"}, self._filter(proxmox_endpoint_id=[5, 7])
        )

    # -- sync types --------------------------------------------------------

    def test_sync_type_filter_treats_all_and_absent_as_covering_everything(
        self,
    ) -> None:
        """Rule: a run matches type T if it recorded T, recorded ``all``, or
        recorded no types (whose documented default is ``all``)."""
        wanted = "storage"
        expected = set()
        for label in self._proxbox_labels():
            params = _row_params(label)
            types = params.get("sync_types")
            if types is None and params.get("sync_type") is not None:
                types = [params["sync_type"]]
            if not types or "all" in types or wanted in types:
                expected.add(label)

        self.assertEqual(self._filter(sync_type=[wanted]), expected)

    def test_sync_type_filter_excludes_a_run_that_did_not_include_it(self) -> None:
        matched = self._filter(sync_type=["ip-addresses"])
        self.assertNotIn("types-storage-only", matched)
        self.assertNotIn("named-7", matched)
        self.assertIn("named-5-11", matched)  # recorded ["all"]

    def test_legacy_singular_sync_type_key_is_honoured(self) -> None:
        self.assertIn("types-legacy-singular", self._filter(sync_type=["storage"]))
        self.assertNotIn("types-legacy-singular", self._filter(sync_type=["sdn"]))

    # -- virtual machines --------------------------------------------------

    def test_vm_filter_matches_only_runs_that_named_the_vm(self) -> None:
        """An empty VM list is the absence of a VM scope, not a wildcard."""
        matched = self._filter(netbox_vm_id=[199])
        self.assertEqual(matched, {"vm-199"})
        self.assertNotIn("vm-none", matched)
        self.assertNotIn("open-key-absent", matched)

    # -- identifiers -------------------------------------------------------

    def test_run_id_and_batch_object_type_are_exact(self) -> None:
        self.assertEqual(self._filter(run_id=["abc-123"]), {"run-id-abc"})
        self.assertEqual(self._filter(run_id=["abc"]), set())
        self.assertEqual(
            self._filter(batch_object_type=["virtualization.cluster"]),
            {"batch-cluster"},
        )

    # -- errored -----------------------------------------------------------

    def test_errored_includes_a_completed_run_that_recorded_an_error(self) -> None:
        """A sync can finish ``completed`` with a stage error recorded.

        That row is exactly what an operator triaging a failure wants, and a
        status-only filter hides it.
        """
        matched = self._filter(errored=True)
        self.assertIn("named-7", matched)  # status=errored
        self.assertIn("named-5-11", matched)  # completed, but error text present
        self.assertNotIn("open-empty-list", matched)

    def test_errored_false_is_the_complement(self) -> None:
        healthy = self._filter(errored=False)
        self.assertNotIn("named-7", healthy)
        self.assertNotIn("named-5-11", healthy)
        self.assertIn("open-empty-list", healthy)

    # -- inherited core filters -------------------------------------------

    def test_core_job_filters_still_work(self) -> None:
        """Subclassing core's FilterSet must not cost the core filters."""
        self.assertLessEqual({"named-7"}, self._filter(status=["errored"]))
        self.assertNotIn("named-7", self._filter(status=["completed"]))
        self.assertEqual(
            self._filter(name=["Proxbox Sync: Virtual machine 199"]), {"vm-199"}
        )

    # -- a scope that resolves to nothing ---------------------------------

    def test_a_cluster_that_matches_no_endpoint_returns_nothing(self) -> None:
        """A narrow question must not be answered with every row.

        Returning the unfiltered queryset when a cluster resolves to no
        endpoint would turn "which runs touched this cluster?" into "here is
        everything", which reads as a successful answer.
        """
        self.assertEqual(self._filter(cluster_id=[999_999]), set())
        self.assertEqual(self._filter(node_id=[999_999]), set())


class ProxboxSyncJobSerializerTests(TestCase):
    """List responses drop ``log_entries``; detail keeps them."""

    def test_list_serializer_omits_log_entries_and_keeps_everything_else(self) -> None:
        full = set(ProxboxSyncJobSerializer.Meta.fields)
        listed = set(ProxboxSyncJobListSerializer.Meta.fields)

        self.assertNotIn("log_entries", listed)
        self.assertEqual(full - listed, {"log_entries"})
        # The fields that make a job identifiable must survive the trim.
        self.assertLessEqual({"id", "name", "status", "data", "error"}, listed)

    def test_detail_serializer_is_the_complete_core_representation(self) -> None:
        from core.api.serializers_.jobs import JobSerializer

        self.assertEqual(
            list(ProxboxSyncJobSerializer.Meta.fields), list(JobSerializer.Meta.fields)
        )


class ProxboxSyncJobSerializerSelectionTests(TestCase):
    """``include_log_entries`` opts the heavy field back into a list response."""

    def _serializer_for(self, action: str, **params: str):
        view = ProxboxSyncJobViewSet()
        view.action = action

        class _Request:
            query_params = params

        view.request = _Request()
        return view.get_serializer_class()

    def test_list_defaults_to_the_log_free_serializer(self) -> None:
        self.assertIs(self._serializer_for("list"), ProxboxSyncJobListSerializer)

    def test_list_can_opt_back_in(self) -> None:
        for truthy in ("true", "True", "1", "yes"):
            self.assertIs(
                self._serializer_for("list", include_log_entries=truthy),
                ProxboxSyncJobSerializer,
            )

    def test_a_falsey_value_does_not_opt_in(self) -> None:
        for falsey in ("false", "0", "no", ""):
            self.assertIs(
                self._serializer_for("list", include_log_entries=falsey),
                ProxboxSyncJobListSerializer,
            )

    def test_detail_always_includes_log_entries(self) -> None:
        self.assertIs(self._serializer_for("retrieve"), ProxboxSyncJobSerializer)


class ProxboxSyncJobSchemaGenerationTests(TestCase):
    """The view must answer without a bound request.

    drf-spectacular instantiates the view with no ``request`` and asks it for a
    serializer while generating ``/api/schema/``. Reaching straight for
    ``self.request.query_params`` raises ``AttributeError`` there and takes the
    whole instance's schema endpoint down — a failure nowhere near this plugin,
    caused by it.
    """

    def test_serializer_class_resolves_without_a_request(self) -> None:
        view = ProxboxSyncJobViewSet()
        view.action = "list"
        self.assertIs(view.get_serializer_class(), ProxboxSyncJobListSerializer)

    def test_serializer_class_resolves_with_no_action_either(self) -> None:
        self.assertIs(
            ProxboxSyncJobViewSet().get_serializer_class(), ProxboxSyncJobSerializer
        )

    def test_object_permissions_apply_through_a_restricted_queryset(self) -> None:
        """The endpoint must not widen visibility beyond core's own job API.

        The queryset is built with a ``Q`` rather than ``.all()``, so this pins
        that it is still a ``RestrictedQuerySet`` — the thing NetBox's viewset
        calls ``.restrict()`` on to enforce ``core.view_job``.
        """
        from core.api.views import JobViewSet

        self.assertTrue(hasattr(ProxboxSyncJobViewSet.queryset, "restrict"))
        self.assertIs(ProxboxSyncJobViewSet.__mro__[1], JobViewSet.__mro__[1])

    def test_the_endpoint_is_read_only(self) -> None:
        """Read-only comes from the routed actions, not ``http_method_names``.

        A DRF ViewSet inherits the full ``http_method_names`` from Django's
        ``View`` whatever its mixins are, so asserting on that set proves
        nothing — it is the *absence* of create/update/destroy handlers that
        makes the router bind only GET and answer everything else with 405.
        Asserting on the base class proves nothing either: NetBox composes
        ``NetBoxReadOnlyModelViewSet`` from mixins rather than subclassing DRF's
        ``ReadOnlyModelViewSet``.
        """
        self.assertTrue(hasattr(ProxboxSyncJobViewSet, "list"))
        self.assertTrue(hasattr(ProxboxSyncJobViewSet, "retrieve"))
        for handler in ("create", "update", "partial_update", "destroy"):
            self.assertFalse(
                hasattr(ProxboxSyncJobViewSet, handler),
                f"{handler} would make the router bind a write method",
            )


class ProxboxSyncJobBareRowTests(TestCase):
    """A job with no ``data`` at all still has to behave.

    Rows predating the params block are identified by name alone and carry
    `data = NULL`. Every scope filter reads through
    `data__proxbox_sync__params__…`, so if the SQL-NULL case is not covered
    these rows silently vanish from every filtered query while still appearing
    unfiltered — the worst shape, because the listing looks like it works.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        object_type = ContentType.objects.get_for_model(Job)
        cls.bare = Job.objects.create(
            object_type=object_type,
            job_id=uuid.uuid4(),
            name="Proxbox Sync",
            status="completed",
            queue_name="default",
            data=None,
            error="",
        )

    def _matches(self, **query: object) -> bool:
        data = QueryDict(mutable=True)
        for key, value in query.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    data.appendlist(key, str(item))
            else:
                data[key] = str(value)
        queryset = ProxboxSyncJobViewSet.queryset.all()
        filterset = ProxboxSyncJobFilterSet(data, queryset=queryset)
        assert filterset.is_valid(), filterset.errors
        return filterset.qs.filter(pk=self.bare.pk).exists()

    def test_a_bare_row_is_listed_at_all(self) -> None:
        self.assertTrue(self._matches())

    def test_a_bare_row_counts_as_every_endpoint(self) -> None:
        self.assertTrue(self._matches(proxmox_endpoint_id=[5]))

    def test_a_bare_row_counts_as_every_sync_type(self) -> None:
        self.assertTrue(self._matches(sync_type=["storage"]))

    def test_a_bare_row_is_not_a_vm_match(self) -> None:
        self.assertFalse(self._matches(netbox_vm_id=[199]))

    def test_a_bare_row_is_not_errored(self) -> None:
        self.assertFalse(self._matches(errored=True))
