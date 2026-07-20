"""Create-time cloud-init intent fields on ``ProxmoxVMCloudInit`` (issue #210).

Source contracts pinning the intent extension: model fields + encrypted SSH
accessors + soft ``nms_credential_id`` reference, serializer write-only
``sshkeys_intent`` (encrypted) + read-only ``has_sshkeys``, migration 0064
idempotent field adds, and the form/table/template wiring.

netbox-proxbox stores only a soft integer reference to the netbox-nms
``CloudVMCredential`` PK and **must never import netbox-nms**; the plaintext
``sshkeys`` reflection column stays untouched so proxbox-api reflection sync
keeps round-tripping it.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


MODEL = "netbox_proxbox/models/vm_cloudinit.py"
SERIALIZER = "netbox_proxbox/api/serializers/vm_cloudinit.py"
MIGRATION = "netbox_proxbox/migrations/0064_proxmoxvmcloudinit_intent.py"
FORM = "netbox_proxbox/forms/vm_cloudinit.py"
TABLE = "netbox_proxbox/tables/vm_cloudinit.py"
TEMPLATE = "netbox_proxbox/templates/netbox_proxbox/proxmoxvmcloudinit.html"

INTENT_FIELDS = (
    "is_intent",
    "hostname",
    "search_domain",
    "dns_servers",
    "bridge",
    "vlan_tag",
    "gateway",
    "ip_cidr",
    "ssh_pwauth",
    "enable_agent",
    "nms_credential_id",
)


# --- model --------------------------------------------------------------------


def test_model_declares_all_intent_fields() -> None:
    model = _read(MODEL)
    for field in INTENT_FIELDS:
        assert f"{field} = models." in model, field


def test_model_nms_credential_ref_is_soft_int_not_fk() -> None:
    model = _read(MODEL)
    assert "nms_credential_id = models.PositiveIntegerField(" in model
    # Never a ForeignKey and never a python import of the private plugin.
    assert "netbox_nms" not in model.replace("netbox-nms", "")
    assert "import netbox_nms" not in model


def test_model_has_encrypted_sshkeys_accessors() -> None:
    model = _read(MODEL)
    assert "sshkeys_enc = models.TextField(" in model
    assert "def set_sshkeys(self" in model
    assert "def get_sshkeys(self" in model
    assert "def has_sshkeys(self" in model
    assert "encrypt_primary_secret" in model
    assert "decrypt_primary_secret" in model


def test_model_keeps_plaintext_reflection_sshkeys_column() -> None:
    model = _read(MODEL)
    # The original reflection mirror column must remain.
    assert "sshkeys = models.TextField(" in model


# --- serializer ---------------------------------------------------------------


def test_serializer_sshkeys_intent_is_write_only_encrypted() -> None:
    ser = _read(SERIALIZER)
    assert "sshkeys_intent = serializers.CharField(" in ser
    assert "write_only=True" in ser
    assert "has_sshkeys = serializers.BooleanField(read_only=True)" in ser
    assert 'data["sshkeys_enc"] = encrypt_primary_secret(sshkeys_intent)' in ser
    # The raw encrypted column is never exposed as a readable serializer field.
    fields_block = ser.split("fields = (", 1)[1].split("brief_fields", 1)[0]
    assert '"sshkeys_enc"' not in fields_block


def test_serializer_exposes_intent_fields() -> None:
    ser = _read(SERIALIZER)
    for field in INTENT_FIELDS + ("sshkeys_intent", "has_sshkeys"):
        assert f'"{field}"' in ser, field


# --- migration ----------------------------------------------------------------


def test_migration_adds_all_fields_idempotently() -> None:
    mig = _read(MIGRATION)
    assert "add_field_idempotent" in mig
    assert '("netbox_proxbox", "0063_merge_rpc_enabled_service_monitoring")' in mig
    for field in INTENT_FIELDS + ("sshkeys_enc",):
        assert f'field_name="{field}"' in mig, field


# --- UI wiring ----------------------------------------------------------------


def test_form_includes_intent_fields() -> None:
    form = _read(FORM)
    for field in INTENT_FIELDS:
        assert f'"{field}"' in form, field


def test_table_and_template_reference_intent() -> None:
    table = _read(TABLE)
    template = _read(TEMPLATE)
    assert "is_intent" in table
    assert "has_sshkeys" in table
    assert "object.is_intent" in template
    assert "object.nms_credential_id" in template
    assert "object.has_sshkeys" in template
