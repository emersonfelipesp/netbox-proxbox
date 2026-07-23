"""Behavior tests for ``services.sync_firewall.sync_firewall``.

Exercises the error-exit paths and the happy-path upsert flow without
requiring a running NetBox environment.  The module is loaded via importlib
with stubbed ``django``, ``netbox_proxbox.models``, and
``netbox_proxbox.services.backend_proxy`` so all Django ORM calls are
intercepted by in-memory fakes.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

CLUSTER_NAME = "pve-cluster"

MINIMAL_SUMMARY = [
    {
        "cluster_name": CLUSTER_NAME,
        "rules": [
            {
                "pos": 0,
                "type": "in",
                "action": "ACCEPT",
                "enable": 1,
                "comment": "Allow SSH",
                "digest": "abc123",
            }
        ],
        "security_groups": [
            {
                "name": "web-servers",
                "comment": "HTTP/HTTPS group",
                "rules": [
                    {
                        "pos": 0,
                        "type": "in",
                        "action": "ACCEPT",
                        "macro": "SSH",
                        "enable": 1,
                    }
                ],
            }
        ],
        "ip_sets": [
            {
                "name": "management",
                "comment": "Mgmt IPs",
                "entries": [
                    {"cidr": "10.0.0.0/8", "nomatch": False, "comment": "RFC1918"},
                    {"cidr": "192.168.0.0/16", "nomatch": False},
                ],
            }
        ],
        "aliases": [{"name": "gw", "cidr": "10.0.0.1", "comment": "Default gateway"}],
        "options": {
            "enable": 1,
            "policy_in": "DROP",
            "policy_out": "ACCEPT",
            "nosmurfs": 1,
        },
    }
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_fw_module(monkeypatch):
    """Load sync_firewall.py with all Django/plugin dependencies stubbed."""
    # ---- netbox_proxbox package skeleton ----
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    # ---- choices ----
    choices = types.ModuleType("netbox_proxbox.choices")
    choices.FirewallSyncStatusChoices = SimpleNamespace(ACTIVE="active", STALE="stale")
    choices.FirewallZoneChoices = SimpleNamespace(
        DATACENTER="datacenter",
        NODE="node",
        VM_QEMU="vm_qemu",
        VM_LXC="vm_lxc",
        SECURITY_GROUP="security_group",
    )
    choices.FirewallScopeChoices = SimpleNamespace(
        DATACENTER="datacenter",
        VM_QEMU="vm_qemu",
        VM_LXC="vm_lxc",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    # ---- minimal ORM fakes ----
    class _DoesNotExist(Exception):
        pass

    class _MockManager:
        """Minimal ORM manager that tracks update_or_create calls."""

        def __init__(self):
            self._created_count = 0
            self._updated_count = 0
            self._stale_marked = 0
            self._deleted = 0
            self._pk_counter = [0]

        def filter(self, **_kw):
            return self

        def exclude(self, **_kw):
            return self

        def values_list(self, *_a, **_kw):
            return []

        def select_related(self, *_a):
            return self

        def first(self):
            return None

        def update(self, **_kw):
            self._stale_marked += 1
            return 1

        def delete(self):
            self._deleted += 1
            return (0, {})

        def update_or_create(self, defaults=None, **_lookup):
            self._pk_counter[0] += 1
            pk = self._pk_counter[0]
            obj = SimpleNamespace(pk=pk)
            created = True
            if created:
                self._created_count += 1
            return obj, created

    class _FakeModel:
        DoesNotExist = _DoesNotExist

        def __init__(self):
            self.objects = _MockManager()

    _endpoint_obj = SimpleNamespace(pk=1, __str__=lambda s: CLUSTER_NAME)

    class _ProxmoxEndpoint:
        DoesNotExist = _DoesNotExist

        class objects:
            @staticmethod
            def filter(**_kw):
                class _qs:
                    @staticmethod
                    def first():
                        return _endpoint_obj

                return _qs()

            @staticmethod
            def values_list(*_a, **_kw):
                return [1]

    class _ProxmoxCluster:
        DoesNotExist = _DoesNotExist

        class objects:
            @staticmethod
            def filter(**_kw):
                class _qs:
                    @staticmethod
                    def select_related(*_a):
                        return _qs

                    @staticmethod
                    def first():
                        return SimpleNamespace(endpoint=_endpoint_obj, endpoint_id=1)

                return _qs()

    # Per-model managers (shared instances so tests can inspect counts)
    _sg_mgr = _MockManager()
    _rule_mgr = _MockManager()
    _ipset_mgr = _MockManager()
    _entry_mgr = _MockManager()
    _alias_mgr = _MockManager()
    _opts_mgr = _MockManager()

    class _SG:
        DoesNotExist = _DoesNotExist
        objects = _sg_mgr

    class _Rule:
        DoesNotExist = _DoesNotExist
        objects = _rule_mgr

    class _IPSet:
        DoesNotExist = _DoesNotExist
        objects = _ipset_mgr

    class _IPSetEntry:
        DoesNotExist = _DoesNotExist
        objects = _entry_mgr

    class _Alias:
        DoesNotExist = _DoesNotExist
        objects = _alias_mgr

    class _Opts:
        DoesNotExist = _DoesNotExist
        objects = _opts_mgr

    class _ProxmoxNode:
        DoesNotExist = _DoesNotExist
        objects = _MockManager()

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxEndpoint = _ProxmoxEndpoint
    models.ProxmoxFirewallSecurityGroup = _SG
    models.ProxmoxFirewallRule = _Rule
    models.ProxmoxFirewallIPSet = _IPSet
    models.ProxmoxFirewallIPSetEntry = _IPSetEntry
    models.ProxmoxFirewallAlias = _Alias
    models.ProxmoxFirewallOptions = _Opts
    models.ProxmoxNode = _ProxmoxNode
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    # ---- services.backend_proxy ----
    services_pkg = types.ModuleType("netbox_proxbox.services")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)
    backend_proxy = types.ModuleType("netbox_proxbox.services.backend_proxy")
    backend_proxy.get_fastapi_request_context = lambda: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_proxy", backend_proxy
    )
    endpoint_scope = types.ModuleType("netbox_proxbox.services.endpoint_scope")
    endpoint_scope.enabled_backend_endpoint_scope = lambda **_kw: (
        {"source": "database", "proxmox_endpoint_ids": "1"},
        {1: 1},
        None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.endpoint_scope", endpoint_scope
    )

    # ---- django.db ----
    django_pkg = types.ModuleType("django")
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    db_mod = types.ModuleType("django.db")

    class _Atomic:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    db_mod.transaction = SimpleNamespace(atomic=lambda: _Atomic())
    monkeypatch.setitem(sys.modules, "django.db", db_mod)

    # ---- load the module under test ----
    sys.modules.pop("netbox_proxbox.services.sync_firewall", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.sync_firewall",
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_firewall.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.sync_firewall"] = module
    spec.loader.exec_module(module)

    # Expose managers so tests can inspect them
    module._sg_mgr = _sg_mgr
    module._rule_mgr = _rule_mgr
    module._ipset_mgr = _ipset_mgr
    module._entry_mgr = _entry_mgr
    module._alias_mgr = _alias_mgr
    module._opts_mgr = _opts_mgr
    module._endpoint_obj = _endpoint_obj

    return module


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


def test_no_fastapi_url_and_no_context_returns_error(sync_fw_module):
    """When no FastAPI context and no url arg, return error without HTTP call."""
    sync_fw_module.get_fastapi_request_context = lambda endpoint_id=None: None
    with patch("requests.get") as mock_get:
        result = sync_fw_module.sync_firewall()
    assert result.success is False
    assert "FastAPI" in (result.error or "")
    mock_get.assert_not_called()


def test_fastapi_endpoint_id_is_forwarded_to_the_context_resolver(sync_fw_module):
    """The caller's chosen backend must be the one this pass resolves.

    With two enabled ``FastAPIEndpoint`` rows the job preflight certifies the one
    it selected, so a service pass that re-resolves without the id can certify
    backend A and then sync against backend B.
    """
    seen: list[int | None] = []

    def _ctx(endpoint_id=None):
        seen.append(endpoint_id)
        return None

    sync_fw_module.get_fastapi_request_context = _ctx
    with patch("requests.get") as mock_get:
        sync_fw_module.sync_firewall(fastapi_endpoint_id=7)
    assert seen == [7]
    mock_get.assert_not_called()


def test_endpoint_ids_are_forwarded_to_the_endpoint_scope(sync_fw_module):
    """The job's endpoint selection must narrow this pass, not evaporate.

    A job launched against one endpoint used to sync every enabled endpoint's
    firewall objects anyway, because this pass built its own all-enabled scope
    and never saw the selection. The scope helper reads an *omitted*
    ``endpoint_ids`` as "all enabled", so dropping the kwarg here silently
    widens the run — the assertion is on the exact forwarded value, ``None``
    included.
    """
    seen: list[object] = []

    def _scope(**kwargs):
        seen.append(kwargs.get("endpoint_ids", "<missing>"))
        # No scope resolves: sync_firewall returns successfully without HTTP.
        return None, {}, None

    sync_fw_module.enabled_backend_endpoint_scope = _scope
    with patch("requests.get") as mock_get:
        narrowed = sync_fw_module.sync_firewall(
            fastapi_url="http://backend:8000", endpoint_ids=[5]
        )
        unselected = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")
    assert seen == [[5], None]
    assert narrowed.success is True and unselected.success is True
    mock_get.assert_not_called()


def test_http_error_fetching_summary_returns_error(sync_fw_module):
    """A network-level error on the summary call is captured, not raised."""
    import requests as _req

    err = _req.exceptions.ConnectionError("backend offline")
    with patch("requests.get", side_effect=err):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")
    assert result.success is False
    assert "HTTP error fetching firewall summary" in (result.error or "")


def test_non_list_response_returns_error(sync_fw_module):
    """If the backend returns a dict instead of a list, report an error."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"unexpected": "dict"}
    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")
    assert result.success is False
    assert "Unexpected response type" in (result.error or "")


def test_unresolvable_cluster_name_is_skipped(sync_fw_module, monkeypatch):
    """A summary entry with an unknown cluster_name is skipped without error."""
    # Override endpoint resolution to always return None
    monkeypatch.setattr(
        sync_fw_module,
        "_resolve_endpoint_by_cluster_name",
        lambda _name: None,
    )
    summary = [
        {
            "cluster_name": "unknown-cluster",
            "rules": [],
            "security_groups": [],
            "ip_sets": [],
            "aliases": [],
            "options": None,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = summary
    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")
    # No endpoints processed, but the call itself succeeded (no fatal error)
    assert result.error is None
    assert result.endpoints_processed == 0


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_happy_path_calls_upsert_for_all_object_types(sync_fw_module, monkeypatch):
    """With valid summary data, upsert helpers are invoked for all object types."""
    monkeypatch.setattr(
        sync_fw_module,
        "_resolve_endpoint_by_cluster_name",
        lambda _name: sync_fw_module._endpoint_obj,
    )

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = MINIMAL_SUMMARY

    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")

    assert result.success is True
    assert result.endpoints_processed == 1
    assert result.per_endpoint[0]["endpoint_id"] == 1
    assert "runtime_seconds" in result.per_endpoint[0]
    assert result.per_endpoint[0]["runtime_seconds"] >= 0
    # 1 security group
    assert result.security_groups_created == 1
    # 1 datacenter rule + 1 security group rule
    assert result.rules_created == 2
    # 1 IP set
    assert result.ipsets_created == 1
    # 2 IP set entries
    assert result.ipset_entries_created == 2
    # 1 alias
    assert result.aliases_created == 1
    # 1 options record
    assert result.options_created == 1


def test_skip_zone_vnet_rules_are_ignored(sync_fw_module, monkeypatch):
    """Rules in 'vnet' zone must be silently ignored."""
    monkeypatch.setattr(
        sync_fw_module,
        "_resolve_endpoint_by_cluster_name",
        lambda _name: sync_fw_module._endpoint_obj,
    )
    summary = [
        {
            "cluster_name": CLUSTER_NAME,
            "rules": [
                {
                    "pos": 0,
                    "type": "in",
                    "action": "ACCEPT",
                    "enable": 1,
                    "zone": "vnet",
                }
            ],
            "security_groups": [],
            "ip_sets": [],
            "aliases": [],
            "options": None,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = summary

    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")

    assert result.success is True
    assert result.rules_created == 0


def test_empty_summary_succeeds_with_zero_counts(sync_fw_module, monkeypatch):
    """An empty summary list is valid — no objects synced, success=True."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = []

    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")

    assert result.success is True
    assert result.endpoints_processed == 0
    assert result.rules_created == 0


def test_options_without_enable_does_not_crash(sync_fw_module, monkeypatch):
    """Firewall options with no 'enable' key should not raise."""
    monkeypatch.setattr(
        sync_fw_module,
        "_resolve_endpoint_by_cluster_name",
        lambda _name: sync_fw_module._endpoint_obj,
    )
    summary = [
        {
            "cluster_name": CLUSTER_NAME,
            "rules": [],
            "security_groups": [],
            "ip_sets": [],
            "aliases": [],
            "options": {"policy_in": "DROP", "policy_out": "ACCEPT"},
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = summary

    with patch("requests.get", return_value=mock_resp):
        result = sync_fw_module.sync_firewall(fastapi_url="http://backend:8000")

    assert result.success is True
    assert result.options_created == 1
