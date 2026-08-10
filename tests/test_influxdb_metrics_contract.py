"""Static contracts for Proxmox InfluxDB metrics metadata."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from urllib.parse import urlsplit

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


def _load_proxmox_metrics_model(monkeypatch: pytest.MonkeyPatch):
    """Load the real model module against the fast suite's minimal stubs."""
    exceptions = types.ModuleType("django.core.exceptions")
    exceptions.ValidationError = type("ValidationError", (Exception,), {})

    validators = types.ModuleType("django.core.validators")

    class RegexValidator:
        def __init__(self, *args, **kwargs):
            pass

    class URLValidator:
        def __init__(self, *, schemes):
            self.schemes = schemes

        def __call__(self, value):
            parsed_url = urlsplit(value)
            if (
                parsed_url.scheme not in self.schemes
                or not parsed_url.netloc
                or any(character.isspace() for character in value)
            ):
                raise exceptions.ValidationError()

    validators.RegexValidator = RegexValidator
    validators.URLValidator = URLValidator

    models = types.ModuleType("django.db.models")

    class Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Q:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __or__(self, other):
            return (self, "OR", other)

    for field_name in (
        "BooleanField",
        "CharField",
        "ForeignKey",
        "TextField",
        "URLField",
        "UniqueConstraint",
        "CheckConstraint",
    ):
        setattr(models, field_name, Field)
    models.Q = Q
    models.CASCADE = object()

    db = types.ModuleType("django.db")
    db.models = models

    urls = types.ModuleType("django.urls")
    urls.NoReverseMatch = type("NoReverseMatch", (Exception,), {})
    urls.reverse = lambda *args, **kwargs: "/dummy/"

    translation = types.ModuleType("django.utils.translation")
    translation.gettext_lazy = lambda value: value

    netbox_models = types.ModuleType("netbox.models")

    class NetBoxModel:
        def clean(self) -> None:
            pass

        def serialize_object(self, exclude=None):
            excluded = set(exclude or ())
            return {
                field_name: getattr(self, field_name, None)
                for field_name in (
                    "influx_url",
                    "query_token_secret_ref",
                    "writer_token_secret_ref",
                )
                if field_name not in excluded
            }

    netbox_models.NetBoxModel = NetBoxModel

    for name, module in {
        "django.core.exceptions": exceptions,
        "django.core.validators": validators,
        "django.db": db,
        "django.db.models": models,
        "django.urls": urls,
        "django.utils.translation": translation,
        "netbox.models": netbox_models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "_test_proxmox_metrics_model"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "netbox_proxbox/models/proxmox_metrics.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _load_proxmox_metrics_serializer(
    monkeypatch: pytest.MonkeyPatch,
    model_module,
):
    """Load the real serializer against a minimal DRF/NetBox harness."""
    netbox_api_serializers = types.ModuleType("netbox.api.serializers")

    class NetBoxModelSerializer:
        def to_representation(self, instance):
            return {
                field_name: getattr(instance, field_name, None)
                for field_name in self.Meta.fields
            }

    netbox_api_serializers.NetBoxModelSerializer = NetBoxModelSerializer

    rest_framework = types.ModuleType("rest_framework")
    serializers = types.ModuleType("rest_framework.serializers")

    class HyperlinkedIdentityField:
        def __init__(self, *args, **kwargs):
            pass

    serializers.HyperlinkedIdentityField = HyperlinkedIdentityField
    rest_framework.serializers = serializers

    cluster_serializers = types.ModuleType("netbox_proxbox.api.serializers.cluster")

    class NestedSerializer:
        def __init__(self, *args, **kwargs):
            pass

    cluster_serializers.NestedProxmoxClusterSerializer = NestedSerializer
    cluster_serializers.NestedProxmoxEndpointSerializer = NestedSerializer

    proxbox_models = types.ModuleType("netbox_proxbox.models")
    proxbox_models.ProxmoxMetricsInfluxDB = model_module.ProxmoxMetricsInfluxDB

    for name, module in {
        "netbox.api.serializers": netbox_api_serializers,
        "rest_framework": rest_framework,
        "rest_framework.serializers": serializers,
        "netbox_proxbox.api.serializers.cluster": cluster_serializers,
        "netbox_proxbox.models": proxbox_models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "_test_proxmox_metrics_serializer"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "netbox_proxbox/api/serializers/proxmox_metrics.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _load_proxmox_metrics_table(
    monkeypatch: pytest.MonkeyPatch,
    model_module,
):
    """Load the real table against a minimal django-tables2/NetBox harness."""
    django_tables2 = types.ModuleType("django_tables2")

    class Column:
        def __init__(self, *args, **kwargs):
            pass

    django_tables2.Column = Column

    netbox_tables = types.ModuleType("netbox.tables")

    class NetBoxTable:
        class Meta:
            pass

    netbox_tables.NetBoxTable = NetBoxTable

    netbox_table_columns = types.ModuleType("netbox.tables.columns")
    netbox_table_columns.BooleanColumn = Column

    proxbox_models = types.ModuleType("netbox_proxbox.models")
    proxbox_models.ProxmoxMetricsInfluxDB = model_module.ProxmoxMetricsInfluxDB

    for name, module in {
        "django_tables2": django_tables2,
        "netbox.tables": netbox_tables,
        "netbox.tables.columns": netbox_table_columns,
        "netbox_proxbox.models": proxbox_models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "_test_proxmox_metrics_table"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "netbox_proxbox/tables/proxmox_metrics.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("influx-token-plaintext", "********"),
        (" \t ", "********"),
        ("nms-secret:123e4567", "********"),
        ("nms-secret:123e4567-e89b-12d3-a456-42661417400g", "********"),
        (f" {VALID_SECRET_REF} ", "********"),
        (VALID_SECRET_REF, VALID_SECRET_REF),
    ],
)
def test_masked_secret_ref_enforces_exact_reference_grammar(
    monkeypatch: pytest.MonkeyPatch,
    stored_value: str | None,
    expected: str,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)

    rendered = model_module.masked_secret_ref(stored_value)

    assert rendered == expected
    if expected == model_module.MASKED_SECRET_REF:
        assert rendered != stored_value


def test_metrics_display_properties_never_return_plaintext_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.query_token_secret_ref = "query-token-must-not-render"
    row.writer_token_secret_ref = "writer-token-must-not-render"

    assert row.query_token_secret_ref_display == model_module.MASKED_SECRET_REF
    assert row.writer_token_secret_ref_display == model_module.MASKED_SECRET_REF


def test_metrics_changelog_serialization_masks_all_nonconforming_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = "https://user:secret@influxdb.example.test:8086"
    row.query_token_secret_ref = "query-token-must-not-reach-objectchange"
    row.writer_token_secret_ref = "writer-token-must-not-reach-objectchange"

    serialized = row.serialize_object()

    assert serialized == {
        "influx_url": model_module.MASKED_INFLUX_URL,
        "query_token_secret_ref": model_module.MASKED_SECRET_REF,
        "writer_token_secret_ref": model_module.MASKED_SECRET_REF,
    }


def test_metrics_changelog_serialization_preserves_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = "unsafe"
    row.query_token_secret_ref = "unsafe"
    row.writer_token_secret_ref = "unsafe"

    serialized = row.serialize_object(exclude=("influx_url",))

    assert "influx_url" not in serialized
    assert serialized["query_token_secret_ref"] == model_module.MASKED_SECRET_REF
    assert serialized["writer_token_secret_ref"] == model_module.MASKED_SECRET_REF


@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [
        ("influx-token-plaintext", "********"),
        (VALID_SECRET_REF, VALID_SECRET_REF),
        ("", ""),
    ],
)
def test_metrics_serializer_uses_fail_closed_secret_ref_displays(
    monkeypatch: pytest.MonkeyPatch,
    stored_value: str,
    expected: str,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    serializer_module = _load_proxmox_metrics_serializer(monkeypatch, model_module)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = "https://influxdb.example.test:8086"
    row.query_token_secret_ref = stored_value
    row.writer_token_secret_ref = stored_value

    rendered = serializer_module.ProxmoxMetricsInfluxDBSerializer().to_representation(
        row
    )

    assert rendered["query_token_secret_ref"] == expected
    assert rendered["writer_token_secret_ref"] == expected


@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [
        ("https://influxdb.example.test:8086", "https://influxdb.example.test:8086"),
        ("http://192.0.2.10:8086/metrics", "http://192.0.2.10:8086/metrics"),
        ("not-an-influxdb-url", "********"),
        ("https://influxdb.example.test:8086?", "********"),
        ("https://influxdb.example.test:8086#", "********"),
        ("", "********"),
    ],
)
def test_influx_url_display_only_returns_valid_http_urls(
    monkeypatch: pytest.MonkeyPatch,
    stored_value: str,
    expected: str,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = stored_value

    assert row.influx_url_display == expected


def test_metrics_serializer_uses_fail_closed_influx_url_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    serializer_module = _load_proxmox_metrics_serializer(monkeypatch, model_module)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = "raw-non-url-must-not-render"
    row.query_token_secret_ref = VALID_SECRET_REF
    row.writer_token_secret_ref = ""

    rendered = serializer_module.ProxmoxMetricsInfluxDBSerializer().to_representation(
        row
    )

    assert rendered["influx_url"] == "********"


@pytest.mark.parametrize(
    "table_method",
    [
        pytest.param("render_influx_url", id="list-render"),
        pytest.param("value_influx_url", id="export-value"),
    ],
)
def test_metrics_table_masks_nonconforming_influx_url_on_every_output_path(
    monkeypatch: pytest.MonkeyPatch,
    table_method: str,
) -> None:
    model_module = _load_proxmox_metrics_model(monkeypatch)
    table_module = _load_proxmox_metrics_table(monkeypatch, model_module)
    row = model_module.ProxmoxMetricsInfluxDB()
    row.influx_url = "raw-non-url-must-not-render"
    table = table_module.ProxmoxMetricsInfluxDBTable()

    rendered = getattr(table, table_method)(row)

    assert rendered == model_module.MASKED_INFLUX_URL
    assert row.influx_url not in rendered


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


def test_influxdb_metrics_enabled_state_is_database_constrained_after_scrub() -> None:
    model = _read("netbox_proxbox/models/proxmox_metrics.py")
    migration_matches = sorted(
        (ROOT / "netbox_proxbox" / "migrations").glob(
            "0*_metrics_influxdb_secret_ref_constraints.py"
        )
    )
    assert len(migration_matches) == 1, migration_matches
    migration = migration_matches[0].read_text(encoding="utf-8")

    for source in (model, migration):
        assert 'models.Q(enabled=False, query_token_secret_ref="")' in source
        assert 'name="netbox_proxbox_metrics_influxdb_query_token_is_ref"' in source
        assert 'name="netbox_proxbox_metrics_influxdb_writer_token_is_ref"' in source
        assert 'name="netbox_proxbox_metrics_influxdb_url_is_safe"' in source
        assert "CREDENTIAL_FREE_HTTP_URL_RE" in source

    operations = migration.split("operations = [", 1)[1]
    scrub_position = operations.index("_scrub_non_conforming_values")
    first_constraint_position = operations.index("migrations.AddConstraint")
    assert scrub_position < first_constraint_position


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


def test_influxdb_metrics_free_text_search_excludes_raw_url() -> None:
    filtersets = _read("netbox_proxbox/filtersets.py")
    metrics_filterset = filtersets.split("class ProxmoxMetricsInfluxDBFilterSet", 1)[
        1
    ].split("@register_filterset", 1)[0]

    assert "influx_url__icontains" not in metrics_filterset
    assert "name__icontains" in metrics_filterset
    assert "org__icontains" in metrics_filterset
    assert "bucket__icontains" in metrics_filterset


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
            "https://influxdb.example.test:8086?",
            "https://influxdb.example.test:8086#",
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
