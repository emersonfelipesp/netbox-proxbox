"""Fast source/security contracts for encryption-key recovery."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "netbox_proxbox" / "models"
RECOVERY = ROOT / "netbox_proxbox" / "services" / "encryption_recovery.py"
MIGRATIONS = ROOT / "netbox_proxbox" / "migrations"


def _migration_containing(operation_fragment: str) -> str:
    """Find a migration by operation content, independent of its sequence name."""

    matches = [
        path
        for path in MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.py")
        if operation_fragment in path.read_text()
    ]
    assert len(matches) == 1, (
        f"expected one migration containing {operation_fragment!r}, found {matches}"
    )
    return matches[0].read_text()


def _encrypted_model_fields() -> set[tuple[str, str]]:
    fields: set[tuple[str, str]] = set()
    for path in MODELS.glob("*.py"):
        module = ast.parse(path.read_text())
        for class_node in (
            node for node in module.body if isinstance(node, ast.ClassDef)
        ):
            for node in class_node.body:
                target: ast.Name | None = None
                value: ast.expr | None = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = (
                        node.targets[0]
                        if isinstance(node.targets[0], ast.Name)
                        else None
                    )
                    value = node.value
                elif isinstance(node, ast.AnnAssign):
                    target = node.target if isinstance(node.target, ast.Name) else None
                    value = node.value
                if (
                    target is not None
                    and target.id.endswith("_enc")
                    and isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "models"
                ):
                    fields.add((class_node.name, target.id))
    return fields


def _registry_fields() -> tuple[
    set[tuple[str, str]],
    dict[str, tuple[str, ...]],
    dict[str, str | None],
    set[str],
]:
    module = ast.parse(RECOVERY.read_text())
    assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "ENCRYPTED_FIELD_FAMILIES"
    )
    assert isinstance(assignment.value, ast.Tuple)
    fields: set[tuple[str, str]] = set()
    trust_fields: dict[str, tuple[str, ...]] = {}
    optional_apps: dict[str, str | None] = {}
    family_keys: set[str] = set()
    for family in assignment.value.elts:
        assert isinstance(family, ast.Call)
        keywords = {keyword.arg: keyword.value for keyword in family.keywords}
        key = ast.literal_eval(keywords["key"])
        model_name = ast.literal_eval(keywords["model_label"]).rsplit(".", 1)[-1]
        encrypted_fields = ast.literal_eval(keywords["encrypted_fields"])
        trust = ast.literal_eval(keywords.get("trust_fields", ast.Tuple(elts=[])))
        optional_app = ast.literal_eval(
            keywords.get("optional_app_label", ast.Constant(value=None))
        )
        family_keys.add(key)
        trust_fields[key] = trust
        optional_apps[key] = optional_app
        fields.update((model_name, field_name) for field_name in encrypted_fields)
    return fields, trust_fields, optional_apps, family_keys


def test_registry_exhaustively_owns_every_plugin_encrypted_model_field() -> None:
    registry_fields, _trust_fields, optional_apps, family_keys = _registry_fields()

    assert registry_fields == _encrypted_model_fields() | {
        ("PBSPluginSettings", "proxbox_api_key_enc")
    }
    assert family_keys == {
        "proxmox_api",
        "proxmox_ssh",
        "fastapi_backend_key",
        "pbs_api",
        "pbs_fallback_api",
        "pdm_api",
        "node_ssh",
        "cloud_init_ssh_keys",
        "firecracker_agent",
    }
    assert optional_apps == {
        "proxmox_api": None,
        "proxmox_ssh": None,
        "fastapi_backend_key": None,
        "pbs_api": None,
        "pbs_fallback_api": "netbox_pbs",
        "pdm_api": None,
        "node_ssh": None,
        "cloud_init_ssh_keys": None,
        "firecracker_agent": None,
    }


def test_reset_registry_clears_each_family_trust_receipt() -> None:
    _registry_fields_set, trust_fields, _optional_apps, _family_keys = (
        _registry_fields()
    )

    assert trust_fields == {
        "proxmox_api": ("pushed_credential_fingerprint",),
        "proxmox_ssh": ("ssh_known_host_fingerprint",),
        "fastapi_backend_key": ("backend_key_target_fingerprint",),
        "pbs_api": ("fingerprint",),
        "pbs_fallback_api": (),
        "pdm_api": ("fingerprint",),
        "node_ssh": ("known_host_fingerprint",),
        "cloud_init_ssh_keys": (),
        "firecracker_agent": (),
    }


def test_optional_family_is_filtered_through_model_resolution_not_imports() -> None:
    source = RECOVERY.read_text()
    form = (ROOT / "netbox_proxbox" / "forms" / "settings.py").read_text()

    assert 'optional_app_label="netbox_pbs"' in source
    assert 'dormant_db_table="netbox_pbs_pbspluginsettings"' in source
    assert 'model_label="netbox_pbs.PBSPluginSettings"' in source
    assert 'encrypted_fields=("proxbox_api_key_enc",)' in source
    assert "apps.get_app_config(family.optional_app_label)" in source
    assert "except LookupError:" in source
    assert "return None" in source
    assert "EncryptionRecoveryConfigurationError" in source
    assert "_dormant_optional_ciphertext_exists" in source
    assert "model._meta.get_field(field_name)" in source
    assert "FieldDoesNotExist" in source
    assert "available_encrypted_field_families()" in form


def test_rotation_verifies_all_ciphertext_before_any_reencryption_write() -> None:
    source = RECOVERY.read_text()
    rotation = source[
        source.index("def rotate_encryption_key") : source.index(
            "def reset_encrypted_families"
        )
    ]

    assert "with transaction.atomic():" in rotation
    assert ".select_for_update()" in rotation
    assert "family_models = lock_encrypted_field_tables()" in rotation
    first_pass = rotation.index("for family, model in family_models:")
    second_pass = rotation.index("for family, model in family_models:", first_pass + 1)
    assert first_pass < second_pass
    setting_write = rotation.index("encryption_key=new_value")
    assert first_pass < setting_write < second_pass
    assert second_pass < rotation.index("enc_helpers.encrypt(")
    assert "accumulating in memory" in rotation
    assert "No encrypted values or settings were changed." in rotation


def test_key_mutations_use_one_postgresql_table_lock_protocol() -> None:
    source = RECOVERY.read_text()
    settings_model = (MODELS / "plugin_settings.py").read_text()
    app_config = (ROOT / "netbox_proxbox" / "__init__.py").read_text()
    auto_configuration = (
        ROOT / "netbox_proxbox" / "services" / "endpoint_autoconfiguration.py"
    ).read_text()

    assert 'connection.vendor != "postgresql"' in source
    assert "IN SHARE ROW EXCLUSIVE MODE" in source
    assert "connection.ops.quote_name(table_name)" in source
    assert source.count("lock_encrypted_field_tables()") >= 2
    assert "lock_encrypted_field_tables(using=using)" in settings_model
    assert ".select_for_update()" in settings_model
    assert "install_encrypted_writer_guards()" in app_config
    assert "Encrypted values were prepared with a stale" in source
    assert "_install_recovery_queryset_write_guards(model)" in source
    assert "conditional_queryset" in source
    assert "snapshot = dict(zip(recovery_fields" in source
    assert "def guarded_bulk_update(" in source
    assert "def guarded_bulk_create(" in source
    assert "def _locked_encrypted_queryset_update(" in source
    assert "_ENCRYPTED_QUERYSET_WRITE_PERMIT" in source
    assert "ciphertext does not match the locked settings key" in source
    reset = source[source.index("def reset_encrypted_families") :]
    assert reset.index("select_for_update()") < reset.index(
        "lock_encrypted_field_tables()"
    )
    assert auto_configuration.index("select_for_update()") < auto_configuration.index(
        "encrypted_candidate = encrypt_primary_secret(candidate)"
    )


def test_recovery_operations_write_secret_free_object_change_events() -> None:
    source = RECOVERY.read_text()

    assert "ObjectChange.objects.create(" in source
    assert 'operation="rotate"' in source
    assert 'operation="reset"' in source
    assert 'outcome="succeeded"' in source
    assert '"families": list(family_keys)' in source
    assert '"rows_affected": rows_affected' in source
    assert (
        "old_key" not in source[source.index("event = {") : source.index("username =")]
    )
    assert (
        "new_key" not in source[source.index("event = {") : source.index("username =")]
    )


def test_destructive_reset_is_confirmed_atomic_and_non_signaling() -> None:
    source = RECOVERY.read_text()
    reset = source[source.index("def reset_encrypted_families") :]

    assert (
        'RESET_CONFIRMATION_PHRASE: Final = "RESET PROXBOX ENCRYPTED SECRETS"' in source
    )
    assert "confirmation != RESET_CONFIRMATION_PHRASE" in reset
    assert "with transaction.atomic():" in reset
    assert "model.objects.filter(pk=pk), **clear_values" in reset
    assert "enc_helpers.decrypt(" in reset
    assert "operational_reset_values" in reset
    assert ".save(" not in reset


def test_recovery_surfaces_never_render_keys_and_runtime_stays_permissioned() -> None:
    api = (ROOT / "netbox_proxbox" / "api" / "views.py").read_text()
    template = (
        ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox" / "settings.html"
    ).read_text()

    assert "encryption_key if _user_can_read_runtime_secret(request.user)" in api
    assert "_user_can_read_runtime_secret(request.user)" in api
    assert 'get_permission_for_model(models.ProxboxPluginSettings, "change")' in api
    assert "old_key.value" not in template
    assert "new_key.value" not in template
    assert "settings_obj.encryption_key" not in template
    assert "innerHTML" not in template
    assert (
        'sensitive_post_parameters("old_key", "new_key", "confirm_new_key")'
        in (ROOT / "netbox_proxbox" / "views" / "settings.py").read_text()
    )
    settings_view = (ROOT / "netbox_proxbox" / "views" / "settings.py").read_text()
    assert 'sensitive_post_parameters("encryption_key")' in settings_view
    assert "@sensitive_variables()\n    def post" in settings_view
    assert "@sensitive_variables()\ndef rotate_encryption_key" in RECOVERY.read_text()
    assert (
        "@sensitive_variables()\ndef reset_encrypted_families" in RECOVERY.read_text()
    )
    assert (
        "@sensitive_variables()\ndef encrypted_family_statuses" in RECOVERY.read_text()
    )
    assert "@sensitive_variables()\ndef ciphertext_state" in RECOVERY.read_text()
    terminal_view = (
        ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
    ).read_text()
    assert "@sensitive_variables()\n    def _apply_node_credential" in terminal_view
    encryption_helpers = (
        ROOT / "netbox_proxbox" / "utils" / "encryption.py"
    ).read_text()
    assert encryption_helpers.count("@sensitive_variables()") == 5
    settings_form = (ROOT / "netbox_proxbox" / "forms" / "settings.py").read_text()
    assert "current_encryption_key" not in settings_form
    assert 'kwargs.pop("encryption_key_configured", False)' in settings_form


def test_permission_routes_and_signal_fail_closed_boundaries_are_wired() -> None:
    model = (MODELS / "plugin_settings.py").read_text()
    migration = _migration_containing(
        "Can destructively reset Proxbox encrypted secrets"
    )
    urls = (ROOT / "netbox_proxbox" / "urls.py").read_text()
    signals = (ROOT / "netbox_proxbox" / "signals.py").read_text()

    assert '"reset_encrypted_secrets"' in model
    assert '"reset_encrypted_secrets"' in migration
    assert 'name="encryption_key_rotate"' in urls
    assert 'name="encrypted_secret_reset"' in urls
    assert "except EncryptionError:" in signals
    assert "exc_info=True" not in signals


def test_list_and_dashboard_state_uses_ciphertext_not_decrypted_plaintext() -> None:
    tables = (ROOT / "netbox_proxbox" / "tables" / "__init__.py").read_text()
    proxmox_card = (
        ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "home"
        / "proxmox_card.html"
    ).read_text()
    fastapi_card = (
        ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "home"
        / "fastapi_card.html"
    ).read_text()

    assert "credential_state" in tables
    assert 'accessor="token"' not in tables
    assert "password_encryption_state" in proxmox_card
    assert "token_value_encryption_state" in proxmox_card
    assert "credential_encryption_state" in fastapi_card
    assert "{{ object.password }}" not in proxmox_card
    assert "{% if object.password %}" not in proxmox_card
    assert "{{ object.token }}" not in fastapi_card
    assert "{% if object.token %}" not in fastapi_card
