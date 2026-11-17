"""Behavioral contracts for Proxmox pull and InfluxDB reconciliation."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def metrics_module(monkeypatch: pytest.MonkeyPatch):
    """Load the metrics service without bootstrapping NetBox or Django."""
    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxMetricsInfluxDB = type("ProxmoxMetricsInfluxDB", (), {})
    models.ProxboxPluginSettings = type("ProxboxPluginSettings", (), {})
    context = types.ModuleType("netbox_proxbox.services.backend_context")
    context.get_fastapi_request_context = lambda: None
    encryption = types.ModuleType("netbox_proxbox.utils.encryption")
    encryption.EncryptionError = type("EncryptionError", (Exception,), {})
    utilities = types.ModuleType("netbox_proxbox.utils")
    utilities.encryption = encryption
    validation = types.ModuleType("netbox_proxbox.utils.metrics")
    validation.validate_metrics_time = lambda value, **_kwargs: value
    for name, module in {
        "netbox_proxbox.models": models,
        "netbox_proxbox.services.backend_context": context,
        "netbox_proxbox.utils": utilities,
        "netbox_proxbox.utils.encryption": encryption,
        "netbox_proxbox.utils.metrics": validation,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "_test_metrics_reconciliation_service"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "netbox_proxbox/services/metrics_influx.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_official_proxmox_influx_names_match_pull_identity(metrics_module) -> None:
    influx = metrics_module._canonical_row(
        {
            "object": "qemu",
            "vmid": "101",
            "nodename": "pve-a",
            "_field": "diskread",
            "_time": "2026-09-09T20:00:00Z",
            "_value": 2048,
        },
        "influx",
    )
    pull = metrics_module._canonical_row(
        {
            "object_id": "qemu/101",
            "metric": "disk_read",
            "timestamp": 1_788_984_000,
            "value": 2048.0,
            "metric_type": "counter",
        },
        "pull",
    )

    rows, duplicates, conflicts = metrics_module._reconcile_rows([influx], [pull])

    assert duplicates == 1
    assert conflicts == 0
    assert rows[0]["source"] == "influx"
    assert rows[0]["also_seen_in"] == ["pull"]
    assert (rows[0]["object_id"], rows[0]["metric"], rows[0]["timestamp"]) == (
        "qemu/101",
        "disk_read",
        1_788_984_000,
    )


def test_fractional_influx_timestamps_remain_distinct(metrics_module) -> None:
    base = {
        "object": "qemu",
        "vmid": "101",
        "_field": "cpu",
        "_value": 0.25,
    }
    first = metrics_module._canonical_row(
        {**base, "_time": "2026-09-09T20:00:00.100000000Z"}, "influx"
    )
    second = metrics_module._canonical_row(
        {**base, "_time": "2026-09-09T20:00:00.900000000Z"}, "influx"
    )

    rows, duplicates, conflicts = metrics_module._reconcile_rows([first, second], [])

    assert [row["timestamp"] for row in rows] == [
        1_788_984_000.1,
        1_788_984_000.9,
    ]
    assert duplicates == 0
    assert conflicts == 0


def test_equivalent_fractional_timestamps_deduplicate_across_sources(
    metrics_module,
) -> None:
    influx = metrics_module._canonical_row(
        {
            "object": "qemu",
            "vmid": "101",
            "_field": "cpu",
            "_time": "2026-09-09T20:00:00.100000000Z",
            "_value": 0.25,
        },
        "influx",
    )
    pull = metrics_module._canonical_row(
        {
            "object_id": "qemu/101",
            "metric": "cpu_current",
            "timestamp": 1_788_984_000.1,
            "value": 0.25,
            "metric_type": "gauge",
        },
        "pull",
    )

    rows, duplicates, conflicts = metrics_module._reconcile_rows([influx], [pull])

    assert len(rows) == 1
    assert rows[0]["timestamp"] == 1_788_984_000.1
    assert rows[0]["also_seen_in"] == ["pull"]
    assert duplicates == 1
    assert conflicts == 0


def test_influx_wins_cross_source_conflict_and_records_it(metrics_module) -> None:
    pull = {
        "object_id": "node/pve-a",
        "metric": "cpu_current",
        "timestamp": 100,
        "value": 0.25,
        "metric_type": "gauge",
        "source": "pull",
        "also_seen_in": [],
        "conflict": False,
    }
    influx = {**pull, "value": 0.5, "metric_type": None, "source": "influx"}

    rows, duplicates, conflicts = metrics_module._reconcile_rows([influx], [pull])

    assert duplicates == 0
    assert conflicts == 1
    assert rows == [{**influx, "also_seen_in": ["pull"], "conflict": True}]


def test_repeated_identity_retains_conflict_and_provenance(metrics_module) -> None:
    pull = {
        "object_id": "node/pve-a",
        "metric": "cpu_current",
        "timestamp": 100,
        "value": 0.25,
        "metric_type": "gauge",
        "source": "pull",
        "also_seen_in": [],
        "conflict": False,
    }
    influx = {**pull, "value": 0.5, "metric_type": None, "source": "influx"}

    rows, duplicates, conflicts = metrics_module._reconcile_rows(
        [influx, dict(influx)], [pull]
    )

    assert duplicates == 1
    assert conflicts == 1
    assert rows[0]["conflict"] is True
    assert rows[0]["also_seen_in"] == ["pull"]


def test_pull_payload_uses_the_backend_database_endpoint_and_is_bounded(
    metrics_module,
) -> None:
    mapping = types.SimpleNamespace(endpoint=types.SimpleNamespace(pk=17, name="pve-a"))
    now = datetime(2026, 9, 9, 21, 0, tzinfo=UTC)

    payload = metrics_module._build_pull_payload(
        mapping,
        {
            "time_start": "-1h30m",
            "node": "pve-a",
            "vmid": 101,
            "field": "cpu_current",
            "limit": 250,
        },
        now=now,
        backend_endpoint_id=91,
    )

    assert payload == {
        "source": "database",
        "endpoint_id": 91,
        "start_time": int(now.timestamp()) - 5400,
        "history": True,
        "local_only": False,
        "object_ids": ["node/pve-a", "qemu/101", "lxc/101"],
        "metric_names": ["cpu_current"],
        "max_rows": 250,
        "max_response_bytes": metrics_module.MAX_PROXY_RESPONSE_BYTES,
    }


def test_influx_field_filter_queries_every_official_alias(metrics_module) -> None:
    assert metrics_module._influx_field_aliases("mem_used") == [
        "mem",
        "memused",
        "mem_used",
    ]
    assert metrics_module._influx_field_aliases("diskread") == [
        "diskread",
        "disk_read",
    ]
    mapping = types.SimpleNamespace(endpoint=types.SimpleNamespace(pk=17))
    assert metrics_module._build_pull_payload(
        mapping,
        {"field": "diskread", "time_start": "-1h"},
        now=datetime.now(UTC),
        backend_endpoint_id=91,
    )["metric_names"] == ["disk_read"]


def test_influx_combined_node_and_vm_filters_use_official_tags(metrics_module) -> None:
    filters = {"node": "pve-a", "vmid": 101}

    assert metrics_module._build_query_filters(filters) == [
        {"scope": "tag", "key": "nodename", "value": "pve-a", "operator": "=="},
        {"scope": "tag", "key": "vmid", "value": "101", "operator": "=="},
    ]
    rows = [
        {
            "object_id": "qemu/101",
            "metric": "cpu_current",
            "timestamp": 100,
            "value": 0.5,
        }
    ]
    assert (
        metrics_module._apply_canonical_filters(rows, filters, source="influx") == rows
    )


def test_reconciled_response_survives_one_source_failure(metrics_module) -> None:
    pull_result = {
        "columns": ["object_id", "metric", "timestamp", "value"],
        "rows": [
            {
                "object_id": "node/pve-a",
                "metric": "cpu_current",
                "timestamp": 100,
                "value": 0.25,
                "metric_type": "gauge",
                "source": "pull",
                "also_seen_in": [],
                "conflict": False,
            }
        ],
        "row_count": 1,
        "truncated": False,
        "query_window": {"start": "1970-01-01T00:00:00+00:00", "stop": "now()"},
        "captured_at": "2026-09-09T21:00:00+00:00",
        "response_format": "proxmox_export",
    }
    failure = metrics_module.MetricsProxyError("The InfluxDB source is unavailable.")

    response = metrics_module._combined_response(
        {"pull": pull_result}, {"influx": failure}, limit=500, stop_epoch=None
    )

    assert response["partial"] is True
    assert response["source_status"]["pull"] == {"status": "ok", "row_count": 1}
    assert response["source_status"]["influx"]["status"] == "error"
    assert response["rows"][0]["source"] == "pull"


def test_pull_only_policy_never_loads_an_influx_credential(
    metrics_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = types.SimpleNamespace(
        enabled=True,
        source_mode="pull",
        endpoint=types.SimpleNamespace(pk=17, name="pve-a", enabled=True),
    )
    observed: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        metrics_module,
        "_backend_context",
        lambda: types.SimpleNamespace(
            http_url="https://backend.test", headers={}, verify_ssl=True
        ),
    )
    monkeypatch.setattr(
        metrics_module,
        "_enabled_backend_endpoint_scope",
        lambda **_kwargs: ({}, {17: 91}, None),
    )

    def refuse_token(_mapping: object) -> str:
        raise AssertionError("pull-only mode must not decrypt an InfluxDB token")

    def query_backend(**kwargs: object) -> dict[str, object]:
        observed.append((str(kwargs["path"]), kwargs["payload"]))  # type: ignore[arg-type]
        return {
            "columns": ["object_id", "metric", "timestamp", "value"],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "query_window": {
                "start": "2026-09-09T20:00:00+00:00",
                "stop": "2026-09-09T21:00:00+00:00",
            },
            "captured_at": "2026-09-09T21:00:00+00:00",
            "response_format": "proxmox_export",
        }

    monkeypatch.setattr(metrics_module, "_load_query_token", refuse_token)
    monkeypatch.setattr(metrics_module, "_query_backend", query_backend)

    response = metrics_module.query_metrics(
        mapping, {"time_start": "-1h", "time_stop": "now()", "limit": 50}
    )

    assert response["partial"] is False
    assert response["source_mode"] == "pull"
    assert [path for path, _payload in observed] == ["/proxmox/metrics/pull/query"]
    assert observed[0][1]["source"] == "database"
    assert observed[0][1]["endpoint_id"] == 91


def test_pull_fails_safely_when_backend_endpoint_id_is_unresolved(
    metrics_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = types.SimpleNamespace(endpoint=types.SimpleNamespace(pk=17))
    context = types.SimpleNamespace(
        http_url="https://backend.test", headers={}, verify_ssl=True
    )
    monkeypatch.setattr(
        metrics_module,
        "_enabled_backend_endpoint_scope",
        lambda **_kwargs: (None, {}, None),
    )

    with pytest.raises(metrics_module.MetricsProxyError, match="not registered"):
        metrics_module._query_source(
            "pull",
            mapping,
            {"time_start": "-1h"},
            context=context,
            timeout=(10, 60),
            now=datetime.now(UTC),
        )


def test_reconciled_query_degrades_when_one_source_normalization_fails(
    metrics_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = types.SimpleNamespace(
        enabled=True,
        source_mode="reconciled",
        endpoint=types.SimpleNamespace(pk=17, enabled=True),
    )
    monkeypatch.setattr(
        metrics_module,
        "_backend_context",
        lambda: types.SimpleNamespace(http_url="https://backend.test", headers={}),
    )

    def query_source(
        source: str, *_args: object, **_kwargs: object
    ) -> dict[str, object]:
        common = {
            "truncated": False,
            "captured_at": "2026-09-09T21:00:00+00:00",
            "query_window": {"start": "-1h", "stop": None},
        }
        if source == "influx":
            return {
                **common,
                "rows": [{"_field": "cpu", "_time": "invalid", "_value": 1}],
            }
        return {
            **common,
            "rows": [
                {
                    "object_id": "node/pve-a",
                    "metric": "cpu_current",
                    "timestamp": 100,
                    "value": 0.25,
                    "metric_type": "gauge",
                }
            ],
        }

    monkeypatch.setattr(metrics_module, "_query_source", query_source)

    response = metrics_module.query_metrics(
        mapping,
        {"measurement": "system", "time_start": "-1h", "time_stop": "now()"},
    )

    assert response["partial"] is True
    assert response["source_status"]["influx"]["status"] == "error"
    assert response["rows"][0]["source"] == "pull"


@pytest.mark.parametrize(
    "filters",
    [
        {"tag_key": "host", "tag_value": "guest"},
        {"node": "pve-a", "vmid": 101},
        {"aggregation_every": "5m", "aggregation_function": "mean"},
    ],
)
def test_pull_policy_rejects_filters_it_cannot_honor(metrics_module, filters) -> None:
    with pytest.raises(metrics_module.MetricsProxyError) as caught:
        metrics_module._validate_source_query(("pull",), filters)

    assert caught.value.status_code == 400


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"object": "nodes", "host": "pve-a"}, "node/pve-a"),
        ({"object": "lxc", "vmid": 202}, "lxc/202"),
        (
            {"object": "storages", "nodename": "pve-a", "host": "local-zfs"},
            "storage/pve-a/local-zfs",
        ),
    ],
)
def test_official_influx_tags_have_stable_object_ids(
    metrics_module, row, expected
) -> None:
    assert metrics_module._canonical_object_id(row) == expected


def test_source_policy_migration_preserves_influx_default_and_constraints() -> None:
    source = (
        ROOT / "netbox_proxbox/migrations/0093_proxmox_metrics_source_mode.py"
    ).read_text(encoding="utf-8")

    assert '("netbox_proxbox", "0092_proxmox_metrics_plugin_credentials")' in source
    assert 'default="influx"' in source
    assert 'models.Q(source_mode="pull")' in source
    assert 'name="netbox_proxbox_metrics_influxdb_query_token_configured"' in source
    assert 'name="netbox_proxbox_metrics_influxdb_url_is_safe"' in source
    assert "migrations.RunPython(migrations.RunPython.noop, _prepare_reverse)" in source
    assert 'filter(source_mode="pull", enabled=True).update(enabled=False)' in source
