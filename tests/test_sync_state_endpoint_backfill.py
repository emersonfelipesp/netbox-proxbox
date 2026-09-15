"""Behavior tests for corroborated sync-state endpoint binding."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import FrozenInstanceError
import importlib.util
from pathlib import Path
import sys
import types

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


class _QuerySet:
    def __init__(self, manager, filters: dict[str, object]) -> None:
        self.manager = manager
        self.filters = filters

    def _matching_rows(self) -> list[dict[str, object]]:
        rows = self.manager.rows
        if "endpoint__isnull" in self.filters:
            expected = bool(self.filters["endpoint__isnull"])
            rows = [row for row in rows if (row["endpoint_id"] is None) is expected]
        if "proxmox_endpoint_raw_id" in self.filters:
            raw_id = str(self.filters["proxmox_endpoint_raw_id"])
            rows = [
                row for row in rows if str(row["proxmox_endpoint_raw_id"]) == raw_id
            ]
        if "pk__in" in self.filters:
            pks = set(self.filters["pk__in"])
            rows = [row for row in rows if row["pk"] in pks]
        return rows

    def order_by(self, field: str):
        assert field == "pk"
        return self

    def select_for_update(self):
        assert self.manager.atomic_depth
        self.manager.lock_calls.append(dict(self.filters))
        return self

    def values(self, *fields: str) -> list[dict[str, object]]:
        return [
            {field: row[field] for field in fields}
            for row in sorted(self._matching_rows(), key=lambda item: item["pk"])
        ]

    def update(self, **values: object) -> int:
        assert self.manager.atomic_depth
        self.manager.update_calls.append((dict(self.filters), dict(values)))
        rows = self._matching_rows()
        for row in rows:
            row.update(values)
        return len(rows)


class _Manager:
    def __init__(self, rows: list[dict[str, object]], atomic_depth: list[bool]) -> None:
        self.rows = rows
        self.atomic_depth = atomic_depth
        self.filter_calls: list[dict[str, object]] = []
        self.lock_calls: list[dict[str, object]] = []
        self.update_calls: list[tuple[dict[str, object], dict[str, object]]] = []

    def filter(self, **filters: object) -> _QuerySet:
        self.filter_calls.append(dict(filters))
        return _QuerySet(self, filters)


class _RelationQuerySet:
    def __init__(self, manager, filters: dict[str, object]) -> None:
        self.manager = manager
        self.filters = filters

    def _matching_rows(self) -> list[dict[str, object]]:
        rows = self.manager.rows
        if "pk__in" in self.filters:
            pks = set(self.filters["pk__in"])
            rows = [row for row in rows if row["pk"] in pks]
        return sorted(rows, key=lambda row: row["pk"])

    def order_by(self, field: str):
        assert field == "pk"
        return self

    def select_for_update(self):
        assert self.manager.atomic_depth
        if self.manager.before_lock is not None:
            callback, self.manager.before_lock = self.manager.before_lock, None
            callback()
        self.manager.lock_calls.append(dict(self.filters))
        return self

    def values_list(self, *fields: str):
        return [tuple(row[field] for field in fields) for row in self._matching_rows()]


class _RelationManager:
    def __init__(self, rows: list[dict[str, object]], atomic_depth: list[bool]) -> None:
        self.rows = rows
        self.atomic_depth = atomic_depth
        self.before_lock = None
        self.lock_calls: list[dict[str, object]] = []

    def filter(self, **filters: object) -> _RelationQuerySet:
        assert set(filters) == {"pk__in"}
        return _RelationQuerySet(self, filters)


@pytest.fixture
def backfill_module(monkeypatch):
    """Load the real service against behavior-faithful ORM fakes."""
    atomic_depth: list[bool] = []

    @contextmanager
    def atomic():
        atomic_depth.append(True)
        try:
            yield
        finally:
            atomic_depth.pop()

    django_db = types.ModuleType("django.db")
    django_db.transaction = types.SimpleNamespace(atomic=atomic)
    monkeypatch.setitem(sys.modules, "django.db", django_db)

    rows = [
        {
            "pk": 1,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": 101,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "",
        },
        {
            "pk": 2,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": None,
            "proxmox_node_id": 201,
            "proxmox_cluster_name": "",
        },
        {
            "pk": 3,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "cluster-a",
        },
        {
            "pk": 4,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": 102,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "cluster-other",
        },
        {
            "pk": 5,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "missing-cluster",
        },
        {
            "pk": 6,
            "endpoint_id": 9,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": 101,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "",
        },
        {
            "pk": 7,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 15,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "missing-cluster",
        },
    ]

    class ProxboxVirtualMachineSyncState:
        objects = _Manager(rows, atomic_depth)

    sync_state = types.ModuleType("netbox_proxbox.models.sync_state")
    sync_state.ProxboxVirtualMachineSyncState = ProxboxVirtualMachineSyncState
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.sync_state", sync_state)

    class ProxmoxCluster:
        objects = _RelationManager(
            [
                {"pk": 101, "name": "cluster-a", "endpoint_id": 5},
                {"pk": 102, "name": "cluster-other", "endpoint_id": 6},
            ],
            atomic_depth,
        )

    cluster_module = types.ModuleType("netbox_proxbox.models.proxmox_cluster")
    cluster_module.ProxmoxCluster = ProxmoxCluster
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.models.proxmox_cluster", cluster_module
    )

    class ProxmoxNode:
        objects = _RelationManager(
            [
                {"pk": 201, "name": "node-a", "endpoint_id": 5},
                {"pk": 202, "name": "node-other", "endpoint_id": 6},
            ],
            atomic_depth,
        )

    node_module = types.ModuleType("netbox_proxbox.models.proxmox_node")
    node_module.ProxmoxNode = ProxmoxNode
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.proxmox_node", node_module)

    module_name = "netbox_proxbox.services.sync_state_endpoint_backfill"
    path = REPO_ROOT / "netbox_proxbox" / "services" / "sync_state_endpoint_backfill.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return types.SimpleNamespace(
        module=module,
        vm=ProxboxVirtualMachineSyncState,
        cluster=ProxmoxCluster,
        node=ProxmoxNode,
        atomic_depth=atomic_depth,
    )


@pytest.mark.parametrize(
    ("row_pk", "evidence"),
    [(1, "cluster"), (2, "node")],
)
def test_each_supported_row_corroboration_binds(backfill_module, row_pk, evidence):
    del evidence

    summary = backfill_module.module.backfill_sync_state_endpoints({"5": "14"})

    row = next(row for row in backfill_module.vm.objects.rows if row["pk"] == row_pk)
    assert row["endpoint_id"] == "5"
    assert summary.rows_bound_by_model == {"ProxboxVirtualMachineSyncState": 2}


def test_contradicted_and_uncorroborated_rows_are_reported(backfill_module):
    service = backfill_module.module

    summary = service.backfill_sync_state_endpoints({"5": "14"})

    assert [row["endpoint_id"] for row in backfill_module.vm.objects.rows] == [
        "5",
        "5",
        None,
        None,
        None,
        9,
        None,
    ]
    assert summary.total_rows_bound == 2
    assert summary.total_unverified == 3
    assert summary.unverified == {
        "14=5": {
            "backend_id": "14",
            "plugin_endpoint_pk": "5",
            "count": 3,
            "sample_pks": [3, 4, 5],
            "reason": service._unverified_reason("5"),
            "reasons": {
                "no_relation_evidence": {
                    "count": 2,
                    "sample_pks": [3, 5],
                    "sample_rows": [
                        {"pk": 3, "proxmox_cluster_name": "cluster-a"},
                        {"pk": 5, "proxmox_cluster_name": "missing-cluster"},
                    ],
                },
                "not_corroborated": {
                    "count": 1,
                    "sample_pks": [4],
                    "sample_rows": [{"pk": 4, "proxmox_cluster_name": "cluster-other"}],
                },
            },
        }
    }
    assert "automatic_corroboration=locked_relations_only" in summary.one_line()
    assert "unverified_rows_left_unbound=3" in summary.one_line()
    assert backfill_module.vm.objects.update_calls == [
        (
            {
                "endpoint__isnull": True,
                "proxmox_endpoint_raw_id": "14",
                "pk__in": [1, 2],
            },
            {"endpoint_id": "5"},
        )
    ]


def test_name_only_row_is_unverified_and_binds_only_with_review_token(
    backfill_module,
):
    service = backfill_module.module
    summary = service.backfill_sync_state_endpoints({"5": "14"})
    named_row = next(row for row in backfill_module.vm.objects.rows if row["pk"] == 3)

    assert named_row["endpoint_id"] is None
    assert summary.total_rows_bound == 2
    assert summary.unverified["14=5"]["reasons"]["no_relation_evidence"] == {
        "count": 2,
        "sample_pks": [3, 5],
        "sample_rows": [
            {"pk": 3, "proxmox_cluster_name": "cluster-a"},
            {"pk": 5, "proxmox_cluster_name": "missing-cluster"},
        ],
    }

    preview = service.preview_sync_state_endpoint_backfill(
        {"5": "14"}, confirmed_bindings={"14": "5"}
    )
    token = preview.confirmed_bindings["14=5"]["review_token"]
    confirmed = service.backfill_sync_state_endpoints(
        {"5": "14"},
        confirmed_bindings={"14": "5"},
        confirmation_review_tokens={"14": token},
    )

    assert named_row["endpoint_id"] == "5"
    assert confirmed.confirmed_bindings["14=5"]["row_pks"] == [3, 4, 5]


@pytest.mark.parametrize(
    ("cluster_id", "node_id"),
    [(101, 202), (102, 201)],
    ids=("cluster-matches-node-contradicts", "node-matches-cluster-contradicts"),
)
def test_every_present_relation_must_match_the_mapped_endpoint(
    backfill_module,
    cluster_id,
    node_id,
):
    row = {
        "pk": 8,
        "endpoint_id": None,
        "proxmox_endpoint_raw_id": 14,
        "proxmox_cluster_id": cluster_id,
        "proxmox_node_id": node_id,
        "proxmox_cluster_name": "",
    }
    backfill_module.vm.objects.rows.append(row)

    summary = backfill_module.module.backfill_sync_state_endpoints({"5": "14"})

    assert row["endpoint_id"] is None
    assert summary.unverified["14=5"]["reasons"]["relations_disagree"] == {
        "count": 1,
        "sample_pks": [8],
        "sample_rows": [{"pk": 8, "proxmox_cluster_name": ""}],
    }


def test_apply_locks_and_revalidates_related_ownership_before_update(backfill_module):
    row = {
        "pk": 8,
        "endpoint_id": None,
        "proxmox_endpoint_raw_id": 14,
        "proxmox_cluster_id": 103,
        "proxmox_node_id": None,
        "proxmox_cluster_name": "",
    }
    cluster = {"pk": 103, "name": "cluster-moving", "endpoint_id": 5}
    backfill_module.vm.objects.rows.append(row)
    backfill_module.cluster.objects.rows.append(cluster)
    backfill_module.cluster.objects.before_lock = lambda: cluster.update(endpoint_id=6)

    summary = backfill_module.module.backfill_sync_state_endpoints({"5": "14"})

    assert row["endpoint_id"] is None
    assert summary.unverified["14=5"]["sample_pks"] == [3, 4, 5, 8]
    assert backfill_module.vm.objects.lock_calls == [
        {"endpoint__isnull": True, "proxmox_endpoint_raw_id": "14"}
    ]
    assert {"pk__in": {101, 102, 103}} in backfill_module.cluster.objects.lock_calls
    assert {"pk__in": {201}} in backfill_module.node.objects.lock_calls
    assert backfill_module.atomic_depth == []


def test_operator_confirmation_binds_only_the_confirmed_pair(backfill_module):
    service = backfill_module.module
    preview = service.preview_sync_state_endpoint_backfill(
        {"5": "14", "7": "15"},
        confirmed_bindings={"14": "5"},
    )
    token = preview.confirmed_bindings["14=5"]["review_token"]

    summary = service.backfill_sync_state_endpoints(
        {"5": "14", "7": "15"},
        confirmed_bindings={"14": "5"},
        confirmation_review_tokens={"14": token},
    )

    assert [row["endpoint_id"] for row in backfill_module.vm.objects.rows] == [
        "5",
        "5",
        "5",
        "5",
        "5",
        9,
        None,
    ]
    assert summary.confirmed_bindings["14=5"]["row_pks"] == [3, 4, 5]
    assert summary.confirmed_bindings["14=5"]["review_token"] == token
    assert summary.unverified["15=7"]["sample_pks"] == [7]
    assert summary.total_rows_bound == 5


def test_dry_run_lists_every_confirmed_row_without_calling_update(backfill_module):
    summary = backfill_module.module.preview_sync_state_endpoint_backfill(
        {"5": "14"},
        confirmed_bindings={"14": "5"},
    )

    assert summary.rows_bound_by_model == {"ProxboxVirtualMachineSyncState": 5}
    assert summary.confirmed_bindings["14=5"]["row_pks"] == [3, 4, 5]
    assert summary.confirmed_bindings["14=5"]["review_token"].startswith("v1.")
    assert backfill_module.vm.objects.update_calls == []
    assert all(
        row["endpoint_id"] is None
        for row in backfill_module.vm.objects.rows
        if row["pk"] in {1, 2, 3, 4, 5}
    )


def test_review_token_is_deterministic_for_mapping_and_exact_unverified_set(
    backfill_module,
):
    service = backfill_module.module

    first = service.preview_sync_state_endpoint_backfill(
        {"7": "15", "5": "14"}, confirmed_bindings={"14": "5"}
    )
    second = service.preview_sync_state_endpoint_backfill(
        {"5": "14", "7": "15"}, confirmed_bindings={"14": "5"}
    )

    assert (
        first.confirmed_bindings["14=5"]["review_token"]
        == second.confirmed_bindings["14=5"]["review_token"]
    )


def test_apply_refuses_added_and_removed_unverified_pks(backfill_module):
    service = backfill_module.module
    preview = service.preview_sync_state_endpoint_backfill(
        {"5": "14"}, confirmed_bindings={"14": "5"}
    )
    token = preview.confirmed_bindings["14=5"]["review_token"]
    removed = next(row for row in backfill_module.vm.objects.rows if row["pk"] == 4)
    removed["endpoint_id"] = 99
    backfill_module.vm.objects.rows.append(
        {
            "pk": 8,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "missing-new-cluster",
        }
    )

    with pytest.raises(
        service.ConfirmationReviewError,
        match=r"added_pks=\[8\]; removed_pks=\[4\]",
    ):
        service.backfill_sync_state_endpoints(
            {"5": "14"},
            confirmed_bindings={"14": "5"},
            confirmation_review_tokens={"14": token},
        )

    assert backfill_module.vm.objects.update_calls == []


def test_apply_refuses_a_review_token_for_a_changed_mapping(backfill_module):
    service = backfill_module.module
    preview = service.preview_sync_state_endpoint_backfill(
        {"5": "14", "7": "15"}, confirmed_bindings={"14": "5"}
    )
    token = preview.confirmed_bindings["14=5"]["review_token"]

    with pytest.raises(
        service.ConfirmationReviewError, match="mapping no longer matches"
    ):
        service.backfill_sync_state_endpoints(
            {"5": "14", "7": "16"},
            confirmed_bindings={"14": "5"},
            confirmation_review_tokens={"14": token},
        )

    assert backfill_module.vm.objects.update_calls == []


def test_apply_confirmation_requires_a_review_token(backfill_module):
    service = backfill_module.module

    with pytest.raises(service.ConfirmationReviewError, match="requires the dry-run"):
        service.backfill_sync_state_endpoints(
            {"5": "14"}, confirmed_bindings={"14": "5"}
        )

    assert backfill_module.vm.objects.update_calls == []


def test_ambiguous_backend_id_is_skipped(backfill_module):
    summary = backfill_module.module.backfill_sync_state_endpoints(
        {"5": "14", "6": "14"},
        confirmed_bindings={"14": "5"},
    )

    assert summary.total_rows_bound == 0
    assert summary.skipped_backend_ids == {
        "14": "claimed by multiple ProxmoxEndpoint primary keys: 5, 6"
    }
    assert backfill_module.vm.objects.update_calls == []


def test_unverified_sample_is_bounded(backfill_module):
    rows = backfill_module.vm.objects.rows
    template = dict(rows[4])
    rows.extend(dict(template, pk=pk) for pk in range(8, 30))

    summary = backfill_module.module.preview_sync_state_endpoint_backfill({"5": "14"})

    bucket = summary.unverified["14=5"]
    assert bucket["count"] == 25
    assert bucket["sample_pks"] == [3, 4, 5, *range(8, 25)]


def test_summary_is_frozen(backfill_module):
    summary = backfill_module.module.BackfillSummary({}, {})

    with pytest.raises(FrozenInstanceError):
        summary.rows_bound_by_model = {"changed": 1}
