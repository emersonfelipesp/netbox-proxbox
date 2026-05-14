"""Source contracts for the NodeSSHCredential operator UI surface."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "urls.py"
VIEWS_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "ssh_credential.py"
FORMS_PATH = REPO_ROOT / "netbox_proxbox" / "forms" / "ssh_credential.py"
TABLES_PATH = REPO_ROOT / "netbox_proxbox" / "tables" / "__init__.py"
NAV_PATH = REPO_ROOT / "netbox_proxbox" / "navigation.py"
SETTINGS_TEMPLATE_PATH = (
    REPO_ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox" / "settings.html"
)


def _class_source(path: Path, class_name: str) -> str:
    text = path.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            src = ast.get_source_segment(text, node)
            assert src is not None
            return src
    raise AssertionError(f"class {class_name!r} not found in {path}")


def test_plugin_urls_register_ssh_credential_model_views():
    src = URLS_PATH.read_text()
    assert "ssh-credentials/<int:pk>/" in src
    assert 'get_model_urls("netbox_proxbox", "nodesshcredential")' in src
    assert "ssh-credentials/" in src
    assert 'get_model_urls("netbox_proxbox", "nodesshcredential", detail=False)' in src


def test_ssh_credential_crud_views_are_registered():
    src = VIEWS_PATH.read_text()
    assert "@register_model_view(NodeSSHCredential)" in src
    assert (
        '@register_model_view(NodeSSHCredential, "list", path="", detail=False)' in src
    )
    assert '@register_model_view(NodeSSHCredential, "add", detail=False)' in src
    assert '@register_model_view(NodeSSHCredential, "edit")' in src
    assert '@register_model_view(NodeSSHCredential, "delete")' in src
    assert '@register_model_view(NodeSSHCredential, "bulk_delete", detail=False)' in src
    assert "NodeSSHCredentialForm" in src
    assert "NodeSSHCredentialFilterForm" in src
    assert "NodeSSHCredentialTable" in src


def test_ssh_credential_navigation_entry_exposes_list_and_add():
    src = NAV_PATH.read_text()
    assert "nodesshcredential_list" in src
    assert "nodesshcredential_add" in src
    assert 'link_text="SSH Credentials"' in src


def test_settings_template_renders_hardware_discovery_flag():
    src = SETTINGS_TEMPLATE_PATH.read_text()
    assert "Hardware Discovery" in src
    assert "form.hardware_discovery_enabled" in src


def test_ssh_credential_form_uses_write_only_secret_fields():
    src = FORMS_PATH.read_text()
    assert "forms.PasswordInput(render_value=False)" in src
    assert "private_key = forms.CharField" in src
    assert "Leave blank on edit to keep the stored value" in src
    assert "_apply_secret_inputs" in src


def test_ssh_credential_table_default_columns_stay_on_credential_fields():
    src = _class_source(TABLES_PATH, "NodeSSHCredentialTable")
    assert '"has_password"' in src
    assert '"has_private_key"' in src
    assert '"auth_method"' in src
    assert '"domain"' not in src
    assert '"use_https"' not in src
