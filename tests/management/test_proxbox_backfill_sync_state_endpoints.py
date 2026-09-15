"""Tests for the sync-state endpoint backfill management command."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from unittest.mock import MagicMock

import pytest

from django.core.management.base import CommandError


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def backfill_command(monkeypatch):
    """Load the command and real backfill service against focused ORM fakes."""
    active: list[object] = []
    atomic_depth: list[bool] = []
    update_calls: list[dict[str, object]] = []

    @contextmanager
    def atomic():
        atomic_depth.append(True)
        try:
            yield
        finally:
            atomic_depth.pop()

    django_db = types.ModuleType("django.db")
    django_db.transaction = SimpleNamespace(atomic=atomic)
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
    ]

    class _QuerySet:
        def __init__(self, filters):
            self.filters = filters

        def _matching_rows(self):
            matching = rows
            if "endpoint__isnull" in self.filters:
                expected = bool(self.filters["endpoint__isnull"])
                matching = [
                    row for row in matching if (row["endpoint_id"] is None) is expected
                ]
            if "proxmox_endpoint_raw_id" in self.filters:
                raw_id = str(self.filters["proxmox_endpoint_raw_id"])
                matching = [
                    row
                    for row in matching
                    if str(row["proxmox_endpoint_raw_id"]) == raw_id
                ]
            if "pk__in" in self.filters:
                pks = set(self.filters["pk__in"])
                matching = [row for row in matching if row["pk"] in pks]
            return matching

        def order_by(self, field):
            assert field == "pk"
            return self

        def select_for_update(self):
            assert atomic_depth
            return self

        def values(self, *fields):
            return [
                {field: row[field] for field in fields}
                for row in sorted(self._matching_rows(), key=lambda item: item["pk"])
            ]

        def update(self, **values):
            assert atomic_depth
            if branch.state is branch.BranchingDecisionState.ENABLED:
                assert active == [branch.branch]
            update_calls.append(dict(values))
            matching = self._matching_rows()
            for row in matching:
                row.update(values)
            return len(matching)

    class _Manager:
        def filter(self, **filters):
            return _QuerySet(filters)

    class ProxboxVirtualMachineSyncState:
        objects = _Manager()

    sync_state = types.ModuleType("netbox_proxbox.models.sync_state")
    sync_state.ProxboxVirtualMachineSyncState = ProxboxVirtualMachineSyncState
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.sync_state", sync_state)

    class _RelationQuerySet:
        def __init__(self, relation_rows, filters):
            self.relation_rows = relation_rows
            self.filters = filters

        def order_by(self, field):
            assert field == "pk"
            return self

        def select_for_update(self):
            assert atomic_depth
            return self

        def values_list(self, *fields):
            matching = self.relation_rows
            if "pk__in" in self.filters:
                pks = set(self.filters["pk__in"])
                matching = [row for row in matching if row["pk"] in pks]
            return [
                tuple(row[field] for field in fields)
                for row in sorted(matching, key=lambda row: row["pk"])
            ]

    class _RelationManager:
        def __init__(self, relation_rows):
            self.relation_rows = relation_rows

        def filter(self, **filters):
            assert set(filters) == {"pk__in"}
            return _RelationQuerySet(self.relation_rows, filters)

    class ProxmoxCluster:
        objects = _RelationManager([{"pk": 101, "name": "cluster-a", "endpoint_id": 5}])

    proxmox_cluster = types.ModuleType("netbox_proxbox.models.proxmox_cluster")
    proxmox_cluster.ProxmoxCluster = ProxmoxCluster
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.models.proxmox_cluster", proxmox_cluster
    )

    class ProxmoxNode:
        objects = _RelationManager([{"pk": 201, "name": "node-a", "endpoint_id": 5}])

    proxmox_node = types.ModuleType("netbox_proxbox.models.proxmox_node")
    proxmox_node.ProxmoxNode = ProxmoxNode
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.proxmox_node", proxmox_node)

    service_name = "netbox_proxbox.services.sync_state_endpoint_backfill"
    service_path = (
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_state_endpoint_backfill.py"
    )
    service_spec = importlib.util.spec_from_file_location(service_name, service_path)
    assert service_spec is not None and service_spec.loader is not None
    service = importlib.util.module_from_spec(service_spec)
    monkeypatch.setitem(sys.modules, service_name, service)
    service_spec.loader.exec_module(service)

    endpoint = SimpleNamespace(pk=5, enabled=True)

    class _EndpointManager:
        @staticmethod
        def filter(**filters):
            assert filters == {"enabled": True}
            return [endpoint]

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxEndpoint = SimpleNamespace(objects=_EndpointManager())
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    context_calls: list[dict[str, object]] = []
    backend_context = types.ModuleType("netbox_proxbox.services.backend_context")

    def get_fastapi_request_context(**kwargs):
        context_calls.append(kwargs)
        return SimpleNamespace(
            http_url="https://proxbox-api.internal",
            headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
        )

    backend_context.get_fastapi_request_context = get_fastapi_request_context
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )

    resolver_calls: list[tuple[object, dict[str, object]]] = []
    backend_sync = types.ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.result = ({5: 14}, None)

    def resolve_backend_endpoint_ids(endpoints, **kwargs):
        resolver_calls.append((endpoints, kwargs))
        return backend_sync.result

    backend_sync.resolve_backend_endpoint_ids = resolve_backend_endpoint_ids
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)

    branch = types.ModuleType("netbox_proxbox.services.branch_lifecycle")

    class BranchingDecisionState:
        DISABLED = object()
        ENABLED = object()

    branch.BranchingDecisionState = BranchingDecisionState
    branch.BranchingUnavailableError = type(
        "BranchingUnavailableError", (RuntimeError,), {}
    )
    branch.state = BranchingDecisionState.DISABLED
    branch.error = None
    branch.guard_calls = 0
    branch.branch = SimpleNamespace(pk=479, name="isolated-479", schema_id="schema-479")
    branch.create_calls = []
    branch.merge_calls = []

    def require_branch_isolation_or_raise():
        branch.guard_calls += 1
        if branch.error is not None:
            raise branch.BranchingUnavailableError(branch.error)
        return SimpleNamespace(
            state=branch.state,
            settings={"prefix": "proxbox-sync", "on_conflict": "fail"},
        )

    def create_and_provision_branch(**kwargs):
        branch.create_calls.append(kwargs)
        return branch.branch

    @contextmanager
    def activate_sync_branch(candidate):
        active.append(candidate)
        try:
            yield
        finally:
            assert active.pop() is candidate

    def merge_branch(**kwargs):
        branch.merge_calls.append(kwargs)
        return True, "Branch isolated-479 merged.", None

    branch.require_branch_isolation_or_raise = require_branch_isolation_or_raise
    branch.create_and_provision_branch = create_and_provision_branch
    branch.activate_sync_branch = activate_sync_branch
    branch.merge_branch = merge_branch
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services.branch_lifecycle", branch)

    command_name = (
        "netbox_proxbox.management.commands.proxbox_backfill_sync_state_endpoints"
    )
    command_path = (
        REPO_ROOT
        / "netbox_proxbox"
        / "management"
        / "commands"
        / "proxbox_backfill_sync_state_endpoints.py"
    )
    command_spec = importlib.util.spec_from_file_location(command_name, command_path)
    assert command_spec is not None and command_spec.loader is not None
    command_module = importlib.util.module_from_spec(command_spec)
    monkeypatch.setitem(sys.modules, command_name, command_module)
    command_spec.loader.exec_module(command_module)

    command = command_module.Command()
    command.stdout = MagicMock()
    command.style = SimpleNamespace(SUCCESS=lambda value: value)
    return SimpleNamespace(
        command=command,
        rows=rows,
        update_calls=update_calls,
        context_calls=context_calls,
        resolver_calls=resolver_calls,
        backend_sync=backend_sync,
        branch=branch,
        active=active,
        atomic_depth=atomic_depth,
    )


def test_dry_run_counts_without_updating(backfill_command):
    backfill_command.command.handle(dry_run=True, fastapi_endpoint=7)

    assert backfill_command.update_calls == []
    assert [row["endpoint_id"] for row in backfill_command.rows] == [None, None]
    assert backfill_command.context_calls == [{"endpoint_id": 7}]
    endpoints, kwargs = backfill_command.resolver_calls[0]
    assert [endpoint.pk for endpoint in endpoints] == [5]
    assert kwargs == {
        "base_url": "https://proxbox-api.internal",
        "auth_headers": {"X-Proxbox-API-Key": "redacted-test-value"},
        "backend_verify_ssl": True,
    }
    output = backfill_command.command.stdout.write.call_args.args[0]
    assert output.startswith("Dry run — Sync-state endpoint backfill:")
    assert '"ProxboxVirtualMachineSyncState": 2' in output


def test_real_run_updates_matching_rows(backfill_command):
    backfill_command.command.handle(dry_run=False, fastapi_endpoint=None)

    assert backfill_command.update_calls == [{"endpoint_id": "5"}]
    assert [row["endpoint_id"] for row in backfill_command.rows] == ["5", "5"]
    assert backfill_command.branch.create_calls == []
    assert backfill_command.branch.merge_calls == []


def test_name_only_row_is_unverified_and_requires_review_token(backfill_command):
    row = backfill_command.rows[0]
    row["proxmox_cluster_id"] = None
    row["proxmox_cluster_name"] = "cluster-a"

    backfill_command.command.handle(dry_run=False, fastapi_endpoint=None)

    assert [candidate["endpoint_id"] for candidate in backfill_command.rows] == [
        None,
        "5",
    ]
    output = backfill_command.command.stdout.write.call_args.args[0]
    assert '"no_relation_evidence": {"count": 1' in output
    assert '"proxmox_cluster_name": "cluster-a"' in output

    backfill_command.command.handle(
        dry_run=True,
        fastapi_endpoint=None,
        confirm_binding=["14=5"],
    )
    token = _review_token_from_output(
        backfill_command.command.stdout.write.call_args.args[0]
    )
    backfill_command.command.handle(
        dry_run=False,
        fastapi_endpoint=None,
        confirm_binding=[f"14=5:{token}"],
    )

    assert row["endpoint_id"] == "5"
    output = backfill_command.command.stdout.write.call_args.args[0]
    assert '"row_pks": [1]' in output


def _arrange_two_unverified_pairs(backfill_command):
    for row in backfill_command.rows:
        row["proxmox_cluster_id"] = None
        row["proxmox_node_id"] = None
    backfill_command.rows.append(
        {
            "pk": 3,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 15,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "",
        }
    )
    backfill_command.backend_sync.result = ({5: 14, 7: 15}, None)


def _review_token_from_output(output: str) -> str:
    match = re.search(r'"review_token": "([^"]+)"', output)
    assert match is not None
    return match.group(1)


def test_confirmation_binds_only_the_asserted_pair(backfill_command):
    _arrange_two_unverified_pairs(backfill_command)
    backfill_command.command.handle(
        dry_run=True,
        fastapi_endpoint=None,
        confirm_binding=["14=5"],
    )
    token = _review_token_from_output(
        backfill_command.command.stdout.write.call_args.args[0]
    )

    backfill_command.command.handle(
        dry_run=False,
        fastapi_endpoint=None,
        confirm_binding=[f"14=5:{token}"],
    )

    assert [row["endpoint_id"] for row in backfill_command.rows] == ["5", "5", None]
    output = backfill_command.command.stdout.write.call_args.args[0]
    assert 'confirmed_bindings={"14=5":' in output
    assert '"row_pks": [1, 2]' in output
    assert f'"review_token": "{token}"' in output
    assert 'unverified={"15=7":' in output


def test_dry_run_lists_exact_confirmed_rows_without_updating(backfill_command):
    _arrange_two_unverified_pairs(backfill_command)

    backfill_command.command.handle(
        dry_run=True,
        fastapi_endpoint=None,
        confirm_binding=["14=5"],
    )

    assert backfill_command.update_calls == []
    assert [row["endpoint_id"] for row in backfill_command.rows] == [None, None, None]
    output = backfill_command.command.stdout.write.call_args.args[0]
    assert output.startswith("Dry run — Sync-state endpoint backfill:")
    assert 'confirmed_bindings={"14=5":' in output
    assert '"row_pks": [1, 2]' in output
    assert '"review_token": "v1.' in output


def test_apply_confirmation_requires_the_dry_run_token(backfill_command):
    _arrange_two_unverified_pairs(backfill_command)

    with pytest.raises(CommandError, match="Apply requires the dry-run review token"):
        backfill_command.command.handle(
            dry_run=False,
            fastapi_endpoint=None,
            confirm_binding=["14=5"],
        )

    assert backfill_command.update_calls == []


def test_apply_refuses_when_the_reviewed_unverified_set_changed(backfill_command):
    _arrange_two_unverified_pairs(backfill_command)
    backfill_command.command.handle(
        dry_run=True,
        fastapi_endpoint=None,
        confirm_binding=["14=5"],
    )
    token = _review_token_from_output(
        backfill_command.command.stdout.write.call_args.args[0]
    )
    backfill_command.rows.append(
        {
            "pk": 4,
            "endpoint_id": None,
            "proxmox_endpoint_raw_id": 14,
            "proxmox_cluster_id": None,
            "proxmox_node_id": None,
            "proxmox_cluster_name": "",
        }
    )

    with pytest.raises(CommandError, match=r"added_pks=\[4\]; removed_pks=\[\]"):
        backfill_command.command.handle(
            dry_run=False,
            fastapi_endpoint=None,
            confirm_binding=[f"14=5:{token}"],
        )

    assert backfill_command.update_calls == []


def test_confirmation_must_match_the_current_mapping(backfill_command):
    with pytest.raises(CommandError, match="does not match one unambiguous"):
        backfill_command.command.handle(
            dry_run=True,
            fastapi_endpoint=None,
            confirm_binding=["14=6"],
        )

    assert backfill_command.update_calls == []


def test_branch_guard_fails_before_backend_resolution(backfill_command):
    backfill_command.branch.error = (
        "Proxbox sync refused: branching_enabled=True requires netbox-branching."
    )

    with pytest.raises(CommandError, match="branching_enabled=True"):
        backfill_command.command.handle(dry_run=False, fastapi_endpoint=None)

    assert backfill_command.context_calls == []
    assert backfill_command.resolver_calls == []
    assert backfill_command.update_calls == []


def test_enabled_branch_wraps_update_and_merges(backfill_command):
    branch = backfill_command.branch
    branch.state = branch.BranchingDecisionState.ENABLED

    backfill_command.command.handle(dry_run=False, fastapi_endpoint=None)

    assert backfill_command.update_calls == [{"endpoint_id": "5"}]
    assert backfill_command.active == []
    assert len(branch.create_calls) == 1
    assert branch.create_calls[0]["name"].startswith("proxbox-sync-endpoint-backfill-")
    assert branch.merge_calls == [
        {"branch": branch.branch, "user": None, "on_conflict": "fail"}
    ]


def test_nothing_resolved_exits_nonzero_without_updating(backfill_command):
    backfill_command.backend_sync.result = ({}, None)

    with pytest.raises(CommandError, match="No enabled ProxmoxEndpoint"):
        backfill_command.command.handle(dry_run=False, fastapi_endpoint=None)

    assert backfill_command.update_calls == []
