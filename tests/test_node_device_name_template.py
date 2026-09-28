"""Validation contracts for configurable Proxmox node Device names."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "validators.py"


@pytest.fixture
def validator_module(monkeypatch: pytest.MonkeyPatch) -> object:
    django = types.ModuleType("django")
    core = types.ModuleType("django.core")
    exceptions = types.ModuleType("django.core.exceptions")
    utils = types.ModuleType("django.utils")
    translation = types.ModuleType("django.utils.translation")

    class ValidationError(Exception):
        def __init__(self, message, *args, params=None, **kwargs):
            text = str(message)
            if params:
                text %= params
            super().__init__(text)

    exceptions.ValidationError = ValidationError
    translation.gettext_lazy = lambda value: value
    for name, module in {
        "django": django,
        "django.core": core,
        "django.core.exceptions": exceptions,
        "django.utils": utils,
        "django.utils.translation": translation,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("_node_name_validator", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validator(validator_module: object) -> object:
    return validator_module.validate_node_device_name_template


class _InventoryQuery:
    def __init__(self, rows: list[tuple[str, ...]]) -> None:
        self.rows = rows
        self.filters = []
        self.fields = ()

    def filter(self, **kwargs: object) -> _InventoryQuery:
        self.filters.append(kwargs)
        return self

    def values_list(
        self, *fields: str, flat: bool = False
    ) -> list[tuple[str, ...]] | list[str]:
        self.fields = fields
        if flat:
            return [row[0] for row in self.rows]
        return self.rows


def _install_inventory(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[tuple[str, ...]],
    *,
    endpoint_rows: list[tuple[str, ...]] | None = None,
    global_template: str = "{node}",
) -> tuple[_InventoryQuery, _InventoryQuery]:
    node_query = _InventoryQuery(rows)
    endpoint_query = _InventoryQuery(endpoint_rows or [])
    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxNode = types.SimpleNamespace(objects=node_query)
    models.ProxmoxEndpoint = types.SimpleNamespace(objects=endpoint_query)
    models.ProxboxPluginSettings = types.SimpleNamespace(
        get_solo=lambda: types.SimpleNamespace(
            node_device_name_template=global_template
        )
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)
    return node_query, endpoint_query


@pytest.mark.parametrize(
    "template",
    (
        "{node}.{unknown}",
        "{cluster}.example.com",
        "{node:>10}",
        "{node!r}",
        "{node.name}",
        "{node[0]}",
        "{node}_bad",
        "{node}." + ("a" * 64),
    ),
)
def test_validator_rejects_unsafe_templates(validator, template: str) -> None:
    with pytest.raises(Exception, match="node|placeholder|DNS|label"):
        validator(template)


def test_validator_accepts_documented_placeholders(validator) -> None:
    validator("{node}.{cluster}.{cluster_slug}.{endpoint}")


def test_cluster_slug_matches_backend_normalization(validator_module) -> None:
    assert (
        validator_module.render_node_device_name(
            "{node}.{cluster_slug}",
            node="node1",
            cluster=" Cluster A / East ",
            endpoint="pve",
        )
        == "node1.cluster-a-east"
    )


def test_endpoint_inventory_rejects_long_real_cluster(
    validator_module, monkeypatch
) -> None:
    query, _ = _install_inventory(monkeypatch, [("node1", "c" * 60)])

    with pytest.raises(Exception, match="node1.*c{60}.*66 characters"):
        validator_module.validate_endpoint_node_device_name_template(
            "{node}.{cluster}", endpoint_id=7, endpoint_name="pve"
        )

    assert query.filters == [{"endpoint_id": 7}]
    assert query.fields == ("name", "proxmox_cluster__name")


def test_global_inventory_rejects_long_cluster_for_inheriting_endpoint(
    validator_module, monkeypatch
) -> None:
    query, endpoint_query = _install_inventory(
        monkeypatch,
        [("node1", "c" * 60, "pve")],
        endpoint_rows=[("pve",)],
    )

    with pytest.raises(Exception, match="node1.*c{60}.*66 characters"):
        validator_module.validate_global_node_device_name_template("{node}.{cluster}")

    assert query.filters == [{"endpoint__node_device_name_template": ""}]
    assert query.fields == (
        "name",
        "proxmox_cluster__name",
        "endpoint__name",
    )
    assert endpoint_query.filters == [{"node_device_name_template": ""}]
    assert endpoint_query.fields == ("name",)


def test_inventory_accepts_render_at_device_name_limit(
    validator_module, monkeypatch
) -> None:
    _install_inventory(monkeypatch, [("abc", "c" * 60)])

    validator_module.validate_endpoint_node_device_name_template(
        "{node}.{cluster}", endpoint_id=7, endpoint_name="pve"
    )


def test_endpoint_without_inventory_renders_sentinel_with_actual_endpoint_name(
    validator_module, monkeypatch
) -> None:
    query, _ = _install_inventory(monkeypatch, [])

    with pytest.raises(Exception, match="65 characters"):
        validator_module.validate_endpoint_node_device_name_template(
            "{node}.{endpoint}", endpoint_id=7, endpoint_name="e" * 60
        )

    assert query.filters == [{"endpoint_id": 7}]


def test_endpoint_create_validates_global_template_with_submitted_name(
    validator_module, monkeypatch
) -> None:
    query, _ = _install_inventory(
        monkeypatch,
        [],
        global_template="{node}.{endpoint}",
    )

    with pytest.raises(Exception, match="65 characters"):
        validator_module.validate_endpoint_node_device_name_template(
            "", endpoint_id=None, endpoint_name="e" * 60
        )

    assert query.filters == []


def test_endpoint_rename_validates_inherited_template_with_new_name(
    validator_module, monkeypatch
) -> None:
    _install_inventory(
        monkeypatch,
        [("node1", "cluster")],
        global_template="{node}.{endpoint}",
    )

    with pytest.raises(Exception, match="node.*65 characters"):
        validator_module.validate_endpoint_node_device_name_template(
            "", endpoint_id=7, endpoint_name="e" * 60
        )


def test_global_template_rejects_inheriting_endpoint_without_nodes(
    validator_module, monkeypatch
) -> None:
    node_query, endpoint_query = _install_inventory(
        monkeypatch,
        [],
        endpoint_rows=[("e" * 60,)],
    )

    with pytest.raises(Exception, match="65 characters"):
        validator_module.validate_global_node_device_name_template("{node}.{endpoint}")

    assert node_query.filters == [{"endpoint__node_device_name_template": ""}]
    assert endpoint_query.filters == [{"node_device_name_template": ""}]
