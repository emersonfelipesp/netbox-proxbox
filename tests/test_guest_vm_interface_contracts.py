"""Source contracts for dual VM interface sync plugin models and wiring."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_guest_vm_interface_model_contract() -> None:
    content = _read("netbox_proxbox/models/guest_vm_interface.py")

    assert "class GuestVMInterface(NetBoxModel)" in content
    assert 'to="virtualization.VirtualMachine"' in content
    assert 'related_name="proxbox_guest_interfaces"' in content
    assert 'to="virtualization.VMInterface"' in content
    # One-to-one core VMInterface <-> GuestVMInterface mapping, SET_NULL so
    # guest OS inventory survives core-interface churn.
    assert "vm_interface = models.OneToOneField(" in content
    assert 'related_name="guest_interface"' in content
    assert "on_delete=models.SET_NULL" in content
    assert "null=True" in content
    assert "blank=True" in content
    assert "name = models.CharField(max_length=128)" in content
    assert "mac_address = models.CharField(" in content
    assert "enabled = models.BooleanField(default=True)" in content
    assert "mtu = models.PositiveIntegerField(null=True, blank=True)" in content
    assert "UniqueConstraint" in content
    assert '"virtual_machine", "name"' in content
    assert 'reverse("plugins:netbox_proxbox:guestvminterface"' in content


def test_guest_vm_interface_address_model_contract() -> None:
    content = _read("netbox_proxbox/models/guest_vm_interface.py")

    assert "class GuestVMInterfaceAddress(NetBoxModel)" in content
    assert 'to="netbox_proxbox.GuestVMInterface"' in content
    assert 'related_name="addresses"' in content
    assert 'to="ipam.IPAddress"' in content
    assert "on_delete=models.PROTECT" in content
    assert 'related_name="proxbox_guest_interface_addresses"' in content
    assert '"guest_interface", "ip_address"' in content
    assert '"plugins:netbox_proxbox:guestvminterfaceaddress"' in content
    # Shared-IP invariant: the linked IP must be the same object on the mapped
    # core interface (or at least a VM interface on the same VM), never an IP
    # owned by a foreign VM, a dcim.Interface, or any non-VMInterface object.
    assert "def clean(self) -> None:" in content
    assert "from virtualization.models import VMInterface" in content
    assert "raise ValidationError(" in content
    assert "if assigned is None:" in content
    assert "not isinstance(assigned, VMInterface)" in content
    # GuestVMInterface.clean() rejects mapping to a core interface on another VM.
    assert "Mapped core VM interface must belong to the same" in content


def test_guest_vm_interface_models_are_exported() -> None:
    content = _read("netbox_proxbox/models/__init__.py")
    assert "GuestVMInterface" in content
    assert "GuestVMInterfaceAddress" in content
    assert '"GuestVMInterface"' in content
    assert '"GuestVMInterfaceAddress"' in content


def test_guest_vm_interface_migration_is_additive() -> None:
    content = _read("netbox_proxbox/migrations/0059_guest_vm_interface.py")

    assert '"0058_encrypt_primary_endpoint_secrets"' in content
    assert "create_model_idempotent" in content
    assert "GuestVMInterface" in content
    assert "GuestVMInterfaceAddress" in content
    assert "add_field_idempotent" in content
    assert "vm_interface_sync_strategy" in content
    assert "guest_os_model" in content
    assert "legacy_rename" in content
    assert "django.db.models.deletion.PROTECT" in content
    # One-to-one core interface link with SET_NULL (survives core churn).
    assert "models.OneToOneField(" in content
    assert "django.db.models.deletion.SET_NULL" in content
    # Backward-compat: existing installs are backfilled to legacy_rename so an
    # upgrade never silently flips interface-sync behavior. The backfill is
    # gated on ProxmoxEndpoint existence so fresh installs (whose settings
    # singleton was created by 0058's get_or_create) keep guest_os_model.
    assert "_backfill_existing_installs_to_legacy" in content
    assert 'update(vm_interface_sync_strategy="legacy_rename")' in content
    assert "migrations.RunPython(" in content
    assert "ProxmoxEndpoint" in content
    assert "if not ProxmoxEndpoint.objects.exists():" in content


def test_guest_vm_interface_strategy_default_adoption_migration_contract() -> None:
    content = _read("netbox_proxbox/migrations/0060_default_guest_os_model.py")

    assert '"0059_guest_vm_interface"' in content
    assert "legacy_rename" in content
    assert "guest_os_model" in content
    assert "RunPython" in content
    assert "apps.get_model" in content
    assert ".filter(" in content
    assert ".update(" in content
    assert "migrations.RunPython.noop" in content


def test_guest_vm_interface_api_contract() -> None:
    serializers = _read("netbox_proxbox/api/serializers/guest_vm_interface.py")
    views = _read("netbox_proxbox/api/views.py")
    urls = _read("netbox_proxbox/api/urls.py")
    filtersets = _read("netbox_proxbox/filtersets.py")

    assert "class GuestVMInterfaceSerializer" in serializers
    assert "class GuestVMInterfaceAddressSerializer" in serializers
    assert "NestedVirtualMachineSerializer" in serializers
    assert "NestedVMInterfaceSerializer" in serializers
    assert "NestedIPAddressSerializer" in serializers
    assert "brief_fields" in serializers
    assert "class GuestVMInterfaceViewSet" in views
    assert "class GuestVMInterfaceAddressViewSet" in views
    assert "GuestVMInterfaceFilterSet" in views
    assert "GuestVMInterfaceAddressFilterSet" in views
    assert '"guest-vm-interfaces"' in urls
    assert 'basename="guestvminterface"' in urls
    assert '"guest-vm-interface-addresses"' in urls
    assert 'basename="guestvminterfaceaddress"' in urls
    assert "class GuestVMInterfaceFilterSet" in filtersets
    assert "class GuestVMInterfaceAddressFilterSet" in filtersets
    assert "ip_address" in filtersets
    # Reconcile-scoping contract: the proxbox-api writer looks up existing rows
    # server-side by ``*_id`` params (and trusts the filtered result), so these
    # ID filters MUST exist or a reconcile for one VM could match a same-named
    # guest interface on a different VM. ``name`` must be an exact match for the
    # same reason (free-text search uses ``search()``/``q``).
    assert "virtual_machine_id = django_filters" in filtersets
    assert "vm_interface_id = django_filters" in filtersets
    assert "guest_interface_id = django_filters" in filtersets
    assert "ip_address_id = django_filters" in filtersets
    assert "name = django_filters.CharFilter()" in filtersets


def test_guest_vm_interface_ui_contract() -> None:
    assert (REPO_ROOT / "netbox_proxbox/tables/guest_vm_interface.py").exists()
    assert (REPO_ROOT / "netbox_proxbox/forms/guest_vm_interface.py").exists()
    assert (REPO_ROOT / "netbox_proxbox/views/guest_vm_interface.py").exists()

    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    views_init = _read("netbox_proxbox/views/__init__.py")

    assert "guestvminterface" in urls
    assert "guestvminterfaceaddress" in urls
    assert "guest_vm_interfaces_item" in navigation
    assert "Guest VM Interfaces" in navigation
    assert "GuestVMInterfaceListView" in views_init
    assert "GuestVMInterfaceAddressListView" in views_init


def test_vm_interface_sync_strategy_settings_contract() -> None:
    choices = _read("netbox_proxbox/choices.py")
    model = _read("netbox_proxbox/models/plugin_settings.py")
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    sync_params = _read("netbox_proxbox/sync_params.py")
    sync_stages = _read("netbox_proxbox/sync_stages.py")
    jobs = _read("netbox_proxbox/jobs.py")

    assert "class VMInterfaceSyncStrategyChoices" in choices
    assert "GUEST_OS_MODEL" in choices
    assert "LEGACY_RENAME" in choices
    assert "vm_interface_sync_strategy = models.CharField" in model
    assert "default=VMInterfaceSyncStrategyChoices.GUEST_OS_MODEL" in model
    assert "DEPRECATED (used only under the legacy_rename strategy):" in model
    assert "vm_interface_sync_strategy = forms.ChoiceField" in form
    assert "DEPRECATED (used only under the legacy_rename strategy):" in form
    assert '"vm_interface_sync_strategy"' in serializer
    assert "form.vm_interface_sync_strategy" in template
    assert "def _vm_interface_sync_strategy_setting" in sync_params
    assert 'base_query["vm_interface_sync_strategy"]' in sync_stages
    assert "_vm_interface_sync_strategy_setting" in jobs
