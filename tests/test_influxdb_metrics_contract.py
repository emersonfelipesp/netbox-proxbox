"""Static contracts for Proxmox InfluxDB metrics metadata."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = ROOT.parent / "netbox" / "netbox"

for candidate in (ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

_DB_TEST_SKIP_REASON = None

try:
    import django
except ModuleNotFoundError:
    django = None
    _DB_TEST_SKIP_REASON = "Django/NetBox test dependencies are not installed."

if django is not None:
    os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
    try:
        django.setup()
    except Exception as exc:  # pragma: no cover - depends on external test services
        _DB_TEST_SKIP_REASON = f"NetBox test environment is not available: {exc}"

if _DB_TEST_SKIP_REASON is None:
    from django.core.exceptions import ValidationError  # noqa: E402
    from django.test import TestCase  # noqa: E402
    from django.urls import reverse  # noqa: E402

    from netbox_proxbox.api.serializers.proxmox_metrics import (  # noqa: E402
        ProxmoxMetricsInfluxDBSerializer,
    )
    from netbox_proxbox.choices import ProxmoxModeChoices  # noqa: E402
    from netbox_proxbox.models import (  # noqa: E402
        ProxmoxCluster,
        ProxmoxEndpoint,
        ProxmoxMetricsInfluxDB,
    )
else:
    TestCase = object


VALID_SECRET_REF = "nms-secret:123e4567-e89b-12d3-a456-426614174000"
INVALID_SECRET_REF = "nms-secret:------------------------------------"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_influxdb_metrics_model_uses_secret_references_not_plaintext_tokens() -> None:
    source = _read("netbox_proxbox/models/proxmox_metrics.py")

    assert "class ProxmoxMetricsInfluxDB(NetBoxModel)" in source
    assert "endpoint = models.ForeignKey" in source
    assert "proxmox_cluster = models.ForeignKey" in source
    assert "influx_url = models.URLField" in source
    assert "query_token_secret_ref" in source
    assert "writer_token_secret_ref" in source
    assert "NMS_SECRET_REF_RE" in source
    assert "nms-secret:" in source
    assert "token_encrypted" not in source
    assert "password" not in source.lower()


def test_influxdb_metrics_secret_ref_regex_uses_strict_uuid_shape() -> None:
    model = _read("netbox_proxbox/models/proxmox_metrics.py")
    migration = _read("netbox_proxbox/migrations/0070_proxmox_metrics_influxdb.py")

    for source in (model, migration):
        assert "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-" in source
        assert "[0-9a-fA-F]{12}" in source
        assert "[0-9a-fA-F-]{36}" not in source


def test_influxdb_metrics_api_route_and_serializer_are_registered() -> None:
    urls = _read("netbox_proxbox/api/urls.py")
    views = _read("netbox_proxbox/api/views.py")
    serializers = _read("netbox_proxbox/api/serializers/__init__.py")
    serializer = _read("netbox_proxbox/api/serializers/proxmox_metrics.py")

    assert '"metrics-influxdb"' in urls
    assert "ProxmoxMetricsInfluxDBViewSet" in urls
    assert "class ProxmoxMetricsInfluxDBViewSet(NetBoxModelViewSet)" in views
    assert "ProxmoxMetricsInfluxDBSerializer" in serializers
    assert "class ProxmoxMetricsInfluxDBSerializer(NetBoxModelSerializer)" in serializer
    for field in (
        "influx_url",
        "org",
        "bucket",
        "query_token_secret_ref",
        "writer_token_secret_ref",
        "verify_tls",
        "enabled",
    ):
        assert f'"{field}"' in serializer


def test_influxdb_metrics_filterset_and_migration_are_wired() -> None:
    filtersets = _read("netbox_proxbox/filtersets.py")
    migration = _read("netbox_proxbox/migrations/0070_proxmox_metrics_influxdb.py")
    models_init = _read("netbox_proxbox/models/__init__.py")

    assert "ProxmoxMetricsInfluxDBFilterSet" in filtersets
    assert "model = ProxmoxMetricsInfluxDB" in filtersets
    assert "ProxmoxMetricsInfluxDB" in models_init
    assert "create_model_idempotent" in migration
    assert '"0069_sync_state_relation_fk_cleanup"' in migration
    assert "netbox_proxbox_metrics_influxdb_unique_cluster_name" in migration
    assert not (
        ROOT / "netbox_proxbox/migrations/0067_proxmox_metrics_influxdb.py"
    ).exists()


def test_influxdb_metrics_ui_surface_is_registered() -> None:
    urls = _read("netbox_proxbox/urls.py")
    views_init = _read("netbox_proxbox/views/__init__.py")
    views = _read("netbox_proxbox/views/proxmox_metrics.py")
    forms_init = _read("netbox_proxbox/forms/__init__.py")
    form = _read("netbox_proxbox/forms/proxmox_metrics.py")
    tables_init = _read("netbox_proxbox/tables/__init__.py")
    table = _read("netbox_proxbox/tables/proxmox_metrics.py")

    assert '"proxmoxmetricsinfluxdb"' in urls
    assert "ProxmoxMetricsInfluxDBView" in views_init
    assert "@register_model_view(ProxmoxMetricsInfluxDB)" in views
    assert '@register_model_view(ProxmoxMetricsInfluxDB, "list"' in views
    assert '@register_model_view(ProxmoxMetricsInfluxDB, "add"' in views
    assert '@register_model_view(ProxmoxMetricsInfluxDB, "edit"' in views
    assert '@register_model_view(ProxmoxMetricsInfluxDB, "delete"' in views
    assert "ProxmoxMetricsInfluxDBForm" in forms_init
    assert "class ProxmoxMetricsInfluxDBForm(NetBoxModelForm)" in form
    assert "class ProxmoxMetricsInfluxDBFilterForm(NetBoxModelFilterSetForm)" in form
    assert "ProxmoxMetricsInfluxDBTable" in tables_init
    assert "class ProxmoxMetricsInfluxDBTable(NetBoxTable)" in table


@pytest.mark.skipif(_DB_TEST_SKIP_REASON is not None, reason=_DB_TEST_SKIP_REASON)
class TestProxmoxMetricsInfluxDBModel(TestCase):
    """DB-backed validation for Proxmox InfluxDB metrics metadata."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(
            name="metrics-pve",
            domain="pve-metrics.example.test",
            port=8006,
            mode=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
            username="root@pam",
            verify_ssl=False,
        )
        cls.cluster = ProxmoxCluster.objects.create(
            endpoint=cls.endpoint,
            name="metrics-cluster",
            cluster_id="metrics-cluster-id",
        )
        cls.other_endpoint = ProxmoxEndpoint.objects.create(
            name="metrics-pve-other",
            domain="pve-metrics-other.example.test",
            port=8006,
            mode=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
            username="root@pam",
            verify_ssl=False,
        )
        cls.other_cluster = ProxmoxCluster.objects.create(
            endpoint=cls.other_endpoint,
            name="metrics-cluster-other",
            cluster_id="metrics-cluster-other-id",
        )

    def _row(self, **overrides):
        payload = {
            "name": "primary",
            "endpoint": self.endpoint,
            "proxmox_cluster": self.cluster,
            "influx_url": "https://influxdb.example.test:8086",
            "org": "nmulticloud",
            "bucket": "proxmox",
            "query_token_secret_ref": VALID_SECRET_REF,
            "writer_token_secret_ref": "",
            "verify_tls": True,
            "enabled": True,
        }
        payload.update(overrides)
        return ProxmoxMetricsInfluxDB(**payload)

    def _serializer_payload(self, **overrides) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": "primary",
            "endpoint": self.endpoint.pk,
            "proxmox_cluster": self.cluster.pk,
            "influx_url": "https://influxdb.example.test:8086",
            "org": "nmulticloud",
            "bucket": "proxmox",
            "measurement_prefix": "",
            "query_token_secret_ref": VALID_SECRET_REF,
            "writer_token_secret_ref": "",
            "verify_tls": True,
            "enabled": True,
            "comments": "",
        }
        payload.update(overrides)
        return payload

    def test_full_clean_rejects_invalid_secret_ref(self) -> None:
        row = self._row(query_token_secret_ref=INVALID_SECRET_REF)

        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()

        self.assertIn("query_token_secret_ref", ctx.exception.message_dict)

    def test_full_clean_accepts_valid_secret_ref(self) -> None:
        row = self._row(query_token_secret_ref=VALID_SECRET_REF)

        row.full_clean()

    def test_full_clean_rejects_url_userinfo_query_and_fragment(self) -> None:
        for url in (
            "https://user:token@influxdb.example.test:8086",
            "https://influxdb.example.test:8086?token=secret",
            "https://influxdb.example.test:8086/#secret",
        ):
            with self.subTest(url=url):
                row = self._row(influx_url=url)
                with self.assertRaises(ValidationError) as ctx:
                    row.full_clean()
                self.assertIn("influx_url", ctx.exception.message_dict)

    def test_full_clean_accepts_base_url(self) -> None:
        row = self._row(influx_url="https://influxdb.example.test:8086")

        row.full_clean()

    def test_serializer_rejects_invalid_secret_ref(self) -> None:
        serializer = ProxmoxMetricsInfluxDBSerializer(
            data=self._serializer_payload(query_token_secret_ref=INVALID_SECRET_REF)
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("query_token_secret_ref", serializer.errors)

    def test_serializer_accepts_valid_secret_ref(self) -> None:
        serializer = ProxmoxMetricsInfluxDBSerializer(
            data=self._serializer_payload(query_token_secret_ref=VALID_SECRET_REF)
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_clean_rejects_endpoint_cluster_mismatch(self) -> None:
        row = self._row(proxmox_cluster=self.other_cluster)

        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()

        self.assertIn("proxmox_cluster", ctx.exception.message_dict)

    def test_get_absolute_url_resolves_detail_route(self) -> None:
        row = ProxmoxMetricsInfluxDB.objects.create(
            name="primary",
            endpoint=self.endpoint,
            proxmox_cluster=self.cluster,
            influx_url="https://influxdb.example.test:8086",
            org="nmulticloud",
            bucket="proxmox",
            query_token_secret_ref=VALID_SECRET_REF,
        )

        expected_url = reverse(
            "plugins:netbox_proxbox:proxmoxmetricsinfluxdb", args=[row.pk]
        )
        self.assertEqual(row.get_absolute_url(), expected_url)
        self.assertTrue(row.get_absolute_url())
