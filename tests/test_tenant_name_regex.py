"""Tests for the optional, multi-pattern, per-endpoint tenant regex resolver.

The feature is disabled by default. These tests pin:

- The global/endpoint inherit-vs-override semantics for both the toggle and
  the rule list (the endpoint list **replaces** the global list when set).
- The first-match-wins rule with operator-set tenant assignments never
  overwritten.
- The form-level JSON validator: bad regex, missing slug, duplicate pattern,
  non-list JSON.

Tests use isolated module stubs (no live NetBox/Django imports) — same shape
as ``test_models_overwrites.py``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# sync_params.effective_tenant_regex_for_endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_params_module(monkeypatch):
    """Load sync_params.py with stubbed model + dependency imports."""
    state: dict[str, object] = {
        "global_enabled": False,
        "global_rules": [],
        "global_tag_enabled": False,
        "global_cluster_enabled": False,
        "endpoints_by_pk": {},
    }

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                enable_tenant_name_regex=state["global_enabled"],
                tenant_name_regex_rules=state["global_rules"],
                enable_tenant_tag_assignment=state["global_tag_enabled"],
                enable_tenant_from_cluster=state["global_cluster_enabled"],
            )

    class _Manager:
        def filter(self, **kwargs):
            self._pk = kwargs.get("pk")
            return self

        def first(self):
            return state["endpoints_by_pk"].get(self._pk)

    class _ProxmoxEndpoint:
        objects = _Manager()

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = ()
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        ALL="all", VIRTUAL_MACHINES="virtual-machines"
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    sync_types_mod = types.ModuleType("netbox_proxbox.sync_types")
    import re

    sync_types_mod._TARGETED_VM_JOB_NAME_RE = re.compile(r"^Sync VM (\d+)")
    sync_types_mod._TARGETED_VM_SYNC_TYPES = ("virtual-machines",)
    sync_types_mod.normalize_sync_types = lambda x: list(x or [])
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sync_types", sync_types_mod)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    sys.modules.pop("netbox_proxbox.sync_params", None)
    path = REPO_ROOT / "netbox_proxbox" / "sync_params.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.sync_params", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.sync_params"] = module
    spec.loader.exec_module(module)
    module._stubs = state  # type: ignore[attr-defined]
    return module


def _endpoint(*, enable=None, rules=None, tag_enable=None, cluster_enable=None):
    return SimpleNamespace(
        enable_tenant_name_regex=enable,
        tenant_name_regex_rules=rules,
        enable_tenant_tag_assignment=tag_enable,
        enable_tenant_from_cluster=cluster_enable,
    )


def test_disabled_by_default(sync_params_module):
    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(None)
    assert enabled is False
    assert rules == []


def test_global_enabled_endpoint_inherits(sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^acme-", "tenant_slug": "acme"}
    ]
    sync_params_module._stubs["endpoints_by_pk"] = {3: _endpoint()}

    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(3)

    assert enabled is True
    assert rules == [{"pattern": "^acme-", "tenant_slug": "acme"}]


def test_endpoint_disable_overrides_global_enable(sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [{"pattern": "^x-", "tenant_slug": "x"}]
    sync_params_module._stubs["endpoints_by_pk"] = {3: _endpoint(enable=False)}

    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(3)

    assert enabled is False
    # rules list is still inherited but the toggle is what gates resolution.
    assert rules == [{"pattern": "^x-", "tenant_slug": "x"}]


def test_endpoint_rules_replace_global_list(sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^global-", "tenant_slug": "global-tenant"},
    ]
    sync_params_module._stubs["endpoints_by_pk"] = {
        9: _endpoint(rules=[{"pattern": "^ep-", "tenant_slug": "ep-tenant"}])
    }

    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(9)

    assert enabled is True
    assert rules == [{"pattern": "^ep-", "tenant_slug": "ep-tenant"}]


def test_endpoint_empty_list_explicitly_replaces(sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^global-", "tenant_slug": "global-tenant"},
    ]
    sync_params_module._stubs["endpoints_by_pk"] = {9: _endpoint(rules=[])}

    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(9)

    assert enabled is True
    assert rules == []


def test_endpoint_missing_returns_global(sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [{"pattern": "^g-", "tenant_slug": "g"}]
    sync_params_module._stubs["endpoints_by_pk"] = {}

    enabled, rules = sync_params_module.effective_tenant_regex_for_endpoint(42)

    assert enabled is True
    assert rules == [{"pattern": "^g-", "tenant_slug": "g"}]


def test_tenant_tag_assignment_inherits_global(sync_params_module):
    sync_params_module._stubs["global_tag_enabled"] = True
    sync_params_module._stubs["endpoints_by_pk"] = {7: _endpoint()}

    enabled = sync_params_module.effective_tenant_tag_assignment_for_endpoint(7)

    assert enabled is True


def test_tenant_tag_assignment_endpoint_override(sync_params_module):
    sync_params_module._stubs["global_tag_enabled"] = True
    sync_params_module._stubs["endpoints_by_pk"] = {7: _endpoint(tag_enable=False)}

    enabled = sync_params_module.effective_tenant_tag_assignment_for_endpoint(7)

    assert enabled is False


def test_tenant_from_cluster_inherits_global(sync_params_module):
    sync_params_module._stubs["global_cluster_enabled"] = True
    sync_params_module._stubs["endpoints_by_pk"] = {7: _endpoint()}

    enabled = sync_params_module.effective_tenant_from_cluster_for_endpoint(7)

    assert enabled is True


def test_tenant_from_cluster_endpoint_override(sync_params_module):
    sync_params_module._stubs["global_cluster_enabled"] = True
    sync_params_module._stubs["endpoints_by_pk"] = {7: _endpoint(cluster_enable=False)}

    enabled = sync_params_module.effective_tenant_from_cluster_for_endpoint(7)

    assert enabled is False


# ---------------------------------------------------------------------------
# services.tenant_assignment.maybe_assign_tenant_from_regex
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_assignment_module(monkeypatch, sync_params_module):
    """Load tenant_assignment.py with a stubbed tenancy.Tenant model."""
    tenants: dict[str, object] = {}
    tenant_groups: dict[str, object] = {}

    class _Tenant:
        def __init__(self, slug, name=None, group=None):
            self.slug = slug
            self.name = name or slug
            self.group = group
            self.pk = id(self)

    class _TenantManager:
        @staticmethod
        def filter(**kwargs):
            slug = kwargs.get("slug")
            return SimpleNamespace(
                first=lambda: tenants.get(slug),
                exists=lambda: slug in tenants,
            )

        @staticmethod
        def get_or_create(slug, defaults=None):
            if slug in tenants:
                return tenants[slug], False
            defaults = defaults or {}
            tenant = _Tenant(
                slug=slug,
                name=defaults.get("name"),
                group=defaults.get("group"),
            )
            tenants[slug] = tenant
            return tenant, True

    class _TenantGroup:
        def __init__(self, slug, name=None):
            self.slug = slug
            self.name = name or slug
            self.pk = id(self)

    class _TenantGroupManager:
        @staticmethod
        def get_or_create(slug, defaults=None):
            if slug in tenant_groups:
                return tenant_groups[slug], False
            defaults = defaults or {}
            group = _TenantGroup(slug=slug, name=defaults.get("name"))
            tenant_groups[slug] = group
            return group, True

    tenancy_models = types.ModuleType("tenancy.models")
    tenancy_models.Tenant = SimpleNamespace(objects=_TenantManager)
    tenancy_models.TenantGroup = SimpleNamespace(objects=_TenantGroupManager)
    tenancy_pkg = types.ModuleType("tenancy")
    tenancy_pkg.models = tenancy_models
    monkeypatch.setitem(sys.modules, "tenancy", tenancy_pkg)
    monkeypatch.setitem(sys.modules, "tenancy.models", tenancy_models)

    extras_models = types.ModuleType("extras.models")

    class _Tag:
        def __init__(self, slug):
            self.slug = slug

    extras_models.Tag = _Tag
    extras_pkg = types.ModuleType("extras")
    extras_pkg.models = extras_models
    monkeypatch.setitem(sys.modules, "extras", extras_pkg)
    monkeypatch.setitem(sys.modules, "extras.models", extras_models)

    # Provide ProxmoxCluster used by _endpoint_id_for_vm.
    models_mod = sys.modules["netbox_proxbox.models"]

    class _ClusterManager:
        @staticmethod
        def filter(**kwargs):
            return SimpleNamespace(first=lambda: None)

    models_mod.ProxmoxCluster = SimpleNamespace(objects=_ClusterManager)

    sys.modules.pop("netbox_proxbox.services", None)
    sys.modules.pop("netbox_proxbox.services.tenant_assignment", None)
    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    path = REPO_ROOT / "netbox_proxbox" / "services" / "tenant_assignment.py"
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.tenant_assignment", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.services.tenant_assignment"] = module
    spec.loader.exec_module(module)
    module._tenants = tenants  # type: ignore[attr-defined]
    module._tenant_groups = tenant_groups  # type: ignore[attr-defined]
    module._Tag = _Tag  # type: ignore[attr-defined]
    return module


class _TagList:
    def __init__(self, slugs):
        self._tags = [SimpleNamespace(slug=slug) for slug in slugs]

    def all(self):
        return list(self._tags)


class _FakeVM:
    def __init__(self, name, tenant_id=None, tags=None, cluster=None, vm_type="qemu"):
        self.name = name
        self.tenant = None
        self.tenant_id = tenant_id
        self.tags = _TagList(tags or [])
        self.cluster = cluster
        self.custom_field_data = {"proxmox_vm_type": vm_type}
        self.saved_with: list[list[str]] = []

    def save(self, update_fields=None):
        self.saved_with.append(list(update_fields or []))
        if "tenant" in self.saved_with[-1] and self.tenant is not None:
            self.tenant_id = getattr(self.tenant, "pk", None)


def test_assign_no_op_when_disabled(tenant_assignment_module, sync_params_module):
    sync_params_module._stubs["global_enabled"] = False
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-acme-", "tenant_slug": "acme"}
    ]
    tenant_assignment_module._tenants["acme"] = object()
    vm = _FakeVM("cust-acme-001")

    assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []


def test_first_match_wins(tenant_assignment_module, sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-acme-", "tenant_slug": "acme"},
        {"pattern": "^cust-", "tenant_slug": "generic"},
    ]
    acme = SimpleNamespace(slug="acme", pk=1)
    generic = SimpleNamespace(slug="generic", pk=2)
    tenant_assignment_module._tenants["acme"] = acme
    tenant_assignment_module._tenants["generic"] = generic

    vm = _FakeVM("cust-acme-prod-01")
    assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
        vm, endpoint_id=None
    )

    assert assigned is True
    assert vm.tenant is acme
    assert vm.saved_with == [["tenant"]]


def test_operator_set_tenant_preserved(tenant_assignment_module, sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-", "tenant_slug": "generic"}
    ]
    tenant_assignment_module._tenants["generic"] = SimpleNamespace(slug="generic")

    vm = _FakeVM("cust-bigco-001", tenant_id=99)
    assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []


def test_unknown_slug_logs_and_stops(
    tenant_assignment_module, sync_params_module, caplog
):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-acme-", "tenant_slug": "acme"},
        {"pattern": "^cust-", "tenant_slug": "generic"},
    ]
    # acme tenant is missing entirely; generic is present.
    tenant_assignment_module._tenants["generic"] = SimpleNamespace(slug="generic")

    vm = _FakeVM("cust-acme-prod-01")
    import logging

    with caplog.at_level(logging.WARNING):
        assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
            vm, endpoint_id=None
        )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []
    assert any("acme" in rec.getMessage() for rec in caplog.records)


def test_no_match_leaves_vm_alone(tenant_assignment_module, sync_params_module):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-acme-", "tenant_slug": "acme"}
    ]
    tenant_assignment_module._tenants["acme"] = SimpleNamespace(slug="acme")

    vm = _FakeVM("infra-monitoring-01")
    assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None


def test_tag_assignment_no_marker_no_op(tenant_assignment_module, sync_params_module):
    sync_params_module._stubs["global_tag_enabled"] = True
    vm = _FakeVM("cust-confitec-001", tags=["tenant-confitec"])

    assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []


def test_tag_assignment_creates_and_assigns_tenant(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_tag_enabled"] = True
    vm = _FakeVM(
        "cust-confitec-001",
        tags=["cloud-customer", "tenant-confitec"],
    )

    assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
        vm, endpoint_id=None
    )

    assert assigned is True
    assert vm.tenant.slug == "confitec"
    assert vm.tenant.name == "Confitec"
    assert vm.tenant.group.slug == "cloud-customers"
    assert vm.tenant.group.name == "Cloud Customers"
    assert tenant_assignment_module._tenants["confitec"] is vm.tenant
    assert vm.saved_with == [["tenant"]]


def test_tag_assignment_existing_tenant_preserved(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_tag_enabled"] = True
    vm = _FakeVM(
        "cust-confitec-001",
        tenant_id=99,
        tags=["cloud-customer", "tenant-confitec"],
    )

    assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []
    assert tenant_assignment_module._tenants == {}


def test_tag_assignment_ambiguous_tags_no_op_with_warning(
    tenant_assignment_module, sync_params_module, caplog
):
    sync_params_module._stubs["global_tag_enabled"] = True
    vm = _FakeVM(
        "cust-confitec-001",
        tags=["cloud-customer", "tenant-confitec", "tenant-acme"],
    )
    import logging

    with caplog.at_level(logging.WARNING):
        assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
            vm, endpoint_id=None
        )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []
    assert tenant_assignment_module._tenants == {}
    assert any("ambiguous" in rec.getMessage() for rec in caplog.records)


def test_tag_assignment_disabled_setting_no_op(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_tag_enabled"] = False
    vm = _FakeVM(
        "cust-confitec-001",
        tags=["cloud-customer", "tenant-confitec"],
    )

    assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.saved_with == []
    assert tenant_assignment_module._tenants == {}


def _cluster(name="tenant-cluster", tenant=None):
    return SimpleNamespace(
        name=name,
        tenant=tenant,
        tenant_id=getattr(tenant, "pk", None),
    )


def test_tenant_from_cluster_assigns_when_empty_and_enabled(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_cluster_enabled"] = True
    tenant = SimpleNamespace(slug="reseller", pk=42)
    vm = _FakeVM("reseller-vm-001", cluster=_cluster(tenant=tenant))

    assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert assigned is True
    assert vm.tenant is tenant
    assert vm.tenant_id == 42
    assert vm.saved_with == [["tenant"]]


def test_tenant_from_cluster_never_overwrites_existing_tenant(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_cluster_enabled"] = True
    cluster_tenant = SimpleNamespace(slug="cluster-tenant", pk=42)
    vm = _FakeVM(
        "operator-owned-vm",
        tenant_id=99,
        cluster=_cluster(tenant=cluster_tenant),
    )

    assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.tenant_id == 99
    assert vm.saved_with == []


@pytest.mark.parametrize(
    "cluster",
    [
        None,
        SimpleNamespace(name="empty-cluster", tenant=None, tenant_id=None),
        SimpleNamespace(name="stale-cluster", tenant=None, tenant_id=42),
    ],
)
def test_tenant_from_cluster_no_op_without_cluster_tenant(
    tenant_assignment_module, sync_params_module, cluster
):
    sync_params_module._stubs["global_cluster_enabled"] = True
    vm = _FakeVM("unassigned-vm", cluster=cluster)

    assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.tenant_id is None
    assert vm.saved_with == []


def test_tenant_from_cluster_no_op_when_disabled(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_cluster_enabled"] = False
    cluster_tenant = SimpleNamespace(slug="cluster-tenant", pk=42)
    vm = _FakeVM("disabled-fallback-vm", cluster=_cluster(tenant=cluster_tenant))

    assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert assigned is False
    assert vm.tenant is None
    assert vm.tenant_id is None
    assert vm.saved_with == []


@pytest.mark.parametrize("vm_type", ["qemu", "lxc"])
def test_tenant_from_cluster_assigns_qemu_and_lxc_representations(
    tenant_assignment_module, sync_params_module, vm_type
):
    sync_params_module._stubs["global_cluster_enabled"] = True
    tenant = SimpleNamespace(slug=f"{vm_type}-tenant", pk=100)
    vm = _FakeVM(
        f"{vm_type}-vm",
        cluster=_cluster(name=f"{vm_type}-cluster", tenant=tenant),
        vm_type=vm_type,
    )

    assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert assigned is True
    assert vm.tenant is tenant
    assert vm.saved_with == [["tenant"]]


def test_cluster_fallback_does_not_override_regex_assignment(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_enabled"] = True
    sync_params_module._stubs["global_rules"] = [
        {"pattern": "^cust-acme-", "tenant_slug": "regex-tenant"}
    ]
    sync_params_module._stubs["global_cluster_enabled"] = True
    regex_tenant = SimpleNamespace(slug="regex-tenant", pk=1)
    cluster_tenant = SimpleNamespace(slug="cluster-tenant", pk=2)
    tenant_assignment_module._tenants["regex-tenant"] = regex_tenant
    vm = _FakeVM(
        "cust-acme-prod-01",
        cluster=_cluster(tenant=cluster_tenant),
    )

    regex_assigned = tenant_assignment_module.maybe_assign_tenant_from_regex(
        vm, endpoint_id=None
    )
    cluster_assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert regex_assigned is True
    assert cluster_assigned is False
    assert vm.tenant is regex_tenant
    assert vm.tenant_id == 1
    assert vm.saved_with == [["tenant"]]


def test_cluster_fallback_does_not_override_tag_assignment(
    tenant_assignment_module, sync_params_module
):
    sync_params_module._stubs["global_tag_enabled"] = True
    sync_params_module._stubs["global_cluster_enabled"] = True
    cluster_tenant = SimpleNamespace(slug="cluster-tenant", pk=2)
    vm = _FakeVM(
        "cust-confitec-prod-01",
        tags=["cloud-customer", "tenant-confitec"],
        cluster=_cluster(tenant=cluster_tenant),
    )

    tag_assigned = tenant_assignment_module.maybe_assign_tenant_from_tags(
        vm, endpoint_id=None
    )
    cluster_assigned = tenant_assignment_module.maybe_assign_tenant_from_cluster(
        vm, endpoint_id=None
    )

    assert tag_assigned is True
    assert cluster_assigned is False
    assert vm.tenant.slug == "confitec"
    assert vm.tenant_id == vm.tenant.pk
    assert vm.saved_with == [["tenant"]]


# ---------------------------------------------------------------------------
# forms.settings._parse_tenant_regex_rules
# ---------------------------------------------------------------------------


@pytest.fixture
def parser_module(monkeypatch):
    """Load just the parser helper from forms/settings.py.

    The full forms module pulls in Django; we extract and exec only the
    helper function with stubbed ``tenancy.models.Tenant`` and ``django.forms``.
    """
    tenants: set[str] = set()

    class _TenantManager:
        @staticmethod
        def filter(slug):
            return SimpleNamespace(exists=lambda: slug in tenants)

    # The helper imports tenancy.Tenant lazily inside the function, so we set
    # it on a module-level Tenant attribute access; mimic Django manager API.
    class _Tenant:
        class objects:
            @staticmethod
            def filter(slug):
                return SimpleNamespace(exists=lambda: slug in tenants)

    tenancy_models = types.ModuleType("tenancy.models")
    tenancy_models.Tenant = _Tenant
    tenancy_pkg = types.ModuleType("tenancy")
    tenancy_pkg.models = tenancy_models
    monkeypatch.setitem(sys.modules, "tenancy", tenancy_pkg)
    monkeypatch.setitem(sys.modules, "tenancy.models", tenancy_models)

    # Stub django.forms.ValidationError minimally.
    django_pkg = types.ModuleType("django")
    forms_mod = types.ModuleType("django.forms")

    class _ValidationError(Exception):
        def __init__(self, messages):
            self.messages = messages if isinstance(messages, list) else [messages]
            super().__init__(messages)

    forms_mod.ValidationError = _ValidationError

    class _Textarea:
        def __init__(self, *a, **kw):
            pass

    forms_mod.Textarea = _Textarea

    class _Field:
        def __init__(self, *a, **kw):
            pass

    forms_mod.CharField = _Field
    forms_mod.BooleanField = _Field
    forms_mod.IntegerField = _Field
    forms_mod.DecimalField = _Field
    forms_mod.ChoiceField = _Field
    forms_mod.PasswordInput = _Field
    forms_mod.NullBooleanField = _Field
    forms_mod.NullBooleanSelect = _Field

    class _Form:
        pass

    forms_mod.Form = _Form
    django_pkg.forms = forms_mod
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    monkeypatch.setitem(sys.modules, "django.forms", forms_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncModeChoices = SimpleNamespace(
        CHOICES=(
            ("always", "Always", "green"),
            ("bootstrap_only", "Bootstrap only", "blue"),
            ("disabled", "Disabled", "red"),
        )
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    # Stub the relative imports that forms/settings.py performs.
    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = ()
    constants_mod.SYNC_MODE_FIELDS = ()
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    # Stub dcim.models so `from dcim.models import DeviceRole` succeeds —
    # forms/settings.py now exposes a default_role_qemu/lxc ModelChoiceField
    # backed by dcim.DeviceRole (added by the hardware-discovery feature
    # merged from develop).
    dcim_pkg = types.ModuleType("dcim")
    dcim_models_mod = types.ModuleType("dcim.models")

    class _DeviceRole:
        class _objects:
            @staticmethod
            def filter(*a, **kw):
                return _DeviceRole._objects

            @staticmethod
            def all():
                return []

            @staticmethod
            def order_by(*a, **kw):
                return []

        objects = _objects

    dcim_models_mod.DeviceRole = _DeviceRole
    monkeypatch.setitem(sys.modules, "dcim", dcim_pkg)
    monkeypatch.setitem(sys.modules, "dcim.models", dcim_models_mod)

    # Stub utilities.forms.fields.DynamicModelChoiceField (the NetBox helper
    # used by the new default_role_* form fields).
    utilities_pkg = types.ModuleType("utilities")
    utilities_forms_pkg = types.ModuleType("utilities.forms")
    utilities_forms_fields_mod = types.ModuleType("utilities.forms.fields")

    class _DynamicModelChoiceField:
        def __init__(self, *a, **kw):
            pass

    utilities_forms_fields_mod.DynamicModelChoiceField = _DynamicModelChoiceField
    monkeypatch.setitem(sys.modules, "utilities", utilities_pkg)
    monkeypatch.setitem(sys.modules, "utilities.forms", utilities_forms_pkg)
    monkeypatch.setitem(
        sys.modules, "utilities.forms.fields", utilities_forms_fields_mod
    )

    plugin_settings_mod = types.ModuleType("netbox_proxbox.models.plugin_settings")
    plugin_settings_mod.DEFAULT_BACKEND_LOG_FILE_PATH = "/var/log/proxbox.log"
    plugin_settings_mod.BRANCH_ON_CONFLICT_CHOICES = [
        ("fail", "fail"),
        ("acknowledge", "acknowledge"),
    ]
    plugin_settings_mod.RECONCILIATION_ENGINE_CHOICES = [
        ("python", "Python (default)"),
        ("compare", "Compare Python and Rust"),
        ("rust", "Rust + PyO3"),
    ]
    plugin_settings_mod.NETBOX_TO_PROXMOX_TYPED_PHRASE = "allow-edit-and-add-actions"
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.models.plugin_settings",
        plugin_settings_mod,
    )

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)
    models_pkg = types.ModuleType("netbox_proxbox.models")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_pkg)
    forms_pkg = types.ModuleType("netbox_proxbox.forms")
    forms_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "forms")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.forms", forms_pkg)

    sys.modules.pop("netbox_proxbox.forms.settings", None)
    path = REPO_ROOT / "netbox_proxbox" / "forms" / "settings.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.forms.settings", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.forms.settings"] = module
    spec.loader.exec_module(module)
    module._tenants = tenants  # type: ignore[attr-defined]
    module._ValidationError = _ValidationError  # type: ignore[attr-defined]
    return module


def test_parser_empty_string_allow_none_returns_none(parser_module):
    result = parser_module._parse_tenant_regex_rules("", allow_none=True)
    assert result is None


def test_parser_empty_string_disallow_none_returns_empty(parser_module):
    result = parser_module._parse_tenant_regex_rules("", allow_none=False)
    assert result == []


def test_parser_explicit_empty_list_with_allow_none_returns_empty(parser_module):
    result = parser_module._parse_tenant_regex_rules("[]", allow_none=True)
    assert result == []


def test_parser_invalid_json(parser_module):
    with pytest.raises(parser_module._ValidationError):
        parser_module._parse_tenant_regex_rules("not json", allow_none=False)


def test_parser_non_list_json(parser_module):
    with pytest.raises(parser_module._ValidationError):
        parser_module._parse_tenant_regex_rules("{}", allow_none=False)


def test_parser_bad_regex(parser_module):
    parser_module._tenants.add("acme")
    with pytest.raises(parser_module._ValidationError) as excinfo:
        parser_module._parse_tenant_regex_rules(
            '[{"pattern": "(", "tenant_slug": "acme"}]', allow_none=False
        )
    assert any("invalid regex" in m for m in excinfo.value.messages)


def test_parser_missing_tenant(parser_module):
    with pytest.raises(parser_module._ValidationError) as excinfo:
        parser_module._parse_tenant_regex_rules(
            '[{"pattern": "^x-", "tenant_slug": "ghost"}]', allow_none=False
        )
    assert any("ghost" in m for m in excinfo.value.messages)


def test_parser_duplicate_pattern(parser_module):
    parser_module._tenants.add("acme")
    parser_module._tenants.add("bigco")
    with pytest.raises(parser_module._ValidationError) as excinfo:
        parser_module._parse_tenant_regex_rules(
            '[{"pattern": "^x-", "tenant_slug": "acme"},'
            ' {"pattern": "^x-", "tenant_slug": "bigco"}]',
            allow_none=False,
        )
    assert any("duplicate" in m for m in excinfo.value.messages)


def test_parser_happy_path_with_label(parser_module):
    parser_module._tenants.add("acme")
    result = parser_module._parse_tenant_regex_rules(
        '[{"pattern": "^acme-", "tenant_slug": "acme", "label": "Acme"}]',
        allow_none=False,
    )
    assert result == [{"pattern": "^acme-", "tenant_slug": "acme", "label": "Acme"}]
