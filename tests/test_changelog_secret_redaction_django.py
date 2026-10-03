"""Native NetBox snapshot and ObjectChange redaction without database I/O."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.netbox_test_paths import netbox_source_roots

ROOT = Path(__file__).resolve().parents[1]
_REQUIRED = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)
try:
    import django
except ModuleNotFoundError:
    if _REQUIRED:
        raise
    pytest.skip("Real Django/NetBox is unavailable.", allow_module_level=True)
if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide real Django.", allow_module_level=True
    )
for path in netbox_source_roots(ROOT):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
try:
    django.setup()
except Exception:
    if _REQUIRED:
        raise
    pytest.skip("The native NetBox harness is unavailable.", allow_module_level=True)

from django.apps import apps  # noqa: E402
from django.contrib.contenttypes.models import ContentType, ContentTypeManager  # noqa: E402
from django.core.serializers.python import Serializer  # noqa: E402
from core.choices import ObjectChangeActionChoices  # noqa: E402
from core.models import ObjectChange  # noqa: E402
from netbox_proxbox.models.changelog_redaction import (  # noqa: E402
    SENSITIVE_OBJECTCHANGE_FIELDS,
    MASKED_SECRET,
)


@pytest.fixture
def native_no_db(monkeypatch) -> None:
    # Stub only relation I/O. Native concrete-field serialization, snapshot(),
    # to_objectchange(), and ObjectChange JSON values remain real NetBox code.
    monkeypatch.setattr(Serializer, "handle_m2m_field", lambda self, obj, field: None)
    import netbox.models.features as features

    monkeypatch.setattr(
        features,
        "get_config",
        lambda: SimpleNamespace(CHANGELOG_SKIP_EMPTY_CHANGES=False),
    )
    monkeypatch.setattr(
        ContentTypeManager,
        "get_for_model",
        lambda self, model, **kwargs: ContentType(
            pk=1, app_label="netbox_proxbox", model=model._meta.model_name
        ),
    )


def _native_instance(model_name) -> object:
    model = apps.get_model("netbox_proxbox", model_name)
    instance = model(pk=101)
    instance._tags = [SimpleNamespace(name="test")]
    if model_name == "nodesshcredential":
        instance.node = apps.get_model("netbox_proxbox", "ProxmoxNode")(
            pk=102,
            name="node",
            endpoint=apps.get_model("netbox_proxbox", "ProxmoxEndpoint")(
                pk=103, name="endpoint"
            ),
        )
    elif model_name == "firecrackerhost":
        instance.pool = apps.get_model("netbox_proxbox", "FirecrackerHostPool")(
            pk=102, name="pool"
        )
    elif model_name == "proxmoxvmcloudinit":
        instance.virtual_machine = apps.get_model("virtualization", "VirtualMachine")(
            pk=102, name="vm"
        )
    elif model_name == "proxmoxmetricsinfluxdb":
        instance.proxmox_cluster = apps.get_model("netbox_proxbox", "ProxmoxCluster")(
            pk=102,
            name="cluster",
            endpoint=apps.get_model("netbox_proxbox", "ProxmoxEndpoint")(
                pk=103, name="endpoint"
            ),
        )
    return instance


@pytest.mark.parametrize("model_name", list(SENSITIVE_OBJECTCHANGE_FIELDS))
@pytest.mark.parametrize(
    "action",
    [
        ObjectChangeActionChoices.ACTION_CREATE,
        ObjectChangeActionChoices.ACTION_UPDATE,
        ObjectChangeActionChoices.ACTION_DELETE,
    ],
)
def test_native_objectchange_never_contains_material(
    native_no_db, model_name, action
) -> None:
    instance = _native_instance(model_name)
    sensitive = SENSITIVE_OBJECTCHANGE_FIELDS[model_name]
    concrete = {field.name for field in instance._meta.concrete_fields}
    stored = sensitive & concrete
    marker = "synthetic-recoverable-material-marker"
    for field in stored:
        # UUID validation is irrelevant to a read-only snapshot; use a real UUID
        # string so Django's serializer exercises its native JSON conversion.
        value = (
            "01234567-89ab-cdef-0123-456789abcdef"
            if field.endswith("_uuid")
            else marker
        )
        setattr(instance, field, value)
    instance.snapshot()
    change = instance.to_objectchange(action)
    assert isinstance(change, ObjectChange)
    snapshots = [change.prechange_data]
    if action != ObjectChangeActionChoices.ACTION_DELETE:
        snapshots.append(change.postchange_data)
    for snapshot in snapshots:
        assert all(snapshot[field] == MASKED_SECRET for field in stored)
        text = json.dumps(snapshot, default=str)
        assert marker not in text
        assert "01234567-89ab-cdef-0123-456789abcdef" not in text


def test_native_snapshot_preserves_metadata_and_exclusions(native_no_db) -> None:
    endpoint = _native_instance("proxmoxendpoint")
    endpoint.name = "Reviewed inventory"
    endpoint.password_enc = "synthetic-ciphertext"
    snapshot = endpoint.serialize_object(exclude=["password_enc", "last_updated"])
    assert snapshot["name"] == "Reviewed inventory"
    assert "password_enc" not in snapshot
    assert "last_updated" not in snapshot
