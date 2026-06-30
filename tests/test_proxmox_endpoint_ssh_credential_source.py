"""Behavior tests for ProxmoxEndpoint SSH credential source selection."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    import django
except ModuleNotFoundError:
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.core.exceptions import ValidationError
from django.test import TestCase

from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.models.ssh_credential import (
    AUTH_METHOD_PASSWORD,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
)


FINGERPRINT = "SHA256:" + "A" * 43


def _form_data(**overrides: str) -> dict[str, str]:
    data = {
        "name": "lab-pve",
        "domain": "pve.example.com",
        "port": "8006",
        "username": "root@pam",
        "password": "endpoint-secret",
        "token_name": "",
        "token_value": "",
        "verify_ssl": "",
        "enabled": "on",
        "allow_writes": "",
        "environment": "",
        "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
        "ssh_username": "",
        "ssh_port": "22",
        "ssh_auth_method": AUTH_METHOD_PASSWORD,
        "ssh_known_host_fingerprint": "",
    }
    data.update(overrides)
    return data


class ProxmoxEndpointSSHCredentialSourceTest(TestCase):
    def test_effective_ssh_username_strips_realm_in_reuse_mode(self):
        endpoint = ProxmoxEndpoint(
            username="root@pam",
            ssh_username="proxbox",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
        )
        self.assertEqual(endpoint.effective_ssh_username, "root")

    def test_effective_ssh_username_uses_dedicated_username(self):
        endpoint = ProxmoxEndpoint(
            username="root@pam",
            ssh_username="proxbox",
            ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
        )
        self.assertEqual(endpoint.effective_ssh_username, "proxbox")

    def test_has_ssh_terminal_credentials_reuse_uses_endpoint_password(self):
        endpoint = ProxmoxEndpoint(
            domain="pve.example.com",
            username="root@pam",
            password="endpoint-secret",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
            ssh_known_host_fingerprint=FINGERPRINT,
        )
        self.assertTrue(endpoint.has_ssh_terminal_credentials)

    def test_has_ssh_terminal_credentials_reuse_false_without_password(self):
        endpoint = ProxmoxEndpoint(
            domain="pve.example.com",
            username="root@pam",
            password="",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
            ssh_known_host_fingerprint=FINGERPRINT,
        )
        self.assertFalse(endpoint.has_ssh_terminal_credentials)

    def test_model_clean_reuse_requires_password_and_fingerprint(self):
        endpoint = ProxmoxEndpoint(
            domain="pve.example.com",
            username="root@pam",
            password="",
            token_name="root@pam!token",
            token_value="token-secret",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
        )

        with self.assertRaises(ValidationError) as caught:
            endpoint.clean()

        self.assertIn("ssh_credential_source", caught.exception.message_dict)
        self.assertIn("ssh_known_host_fingerprint", caught.exception.message_dict)

    def test_form_reuse_accepts_endpoint_password_and_fingerprint(self):
        form = ProxmoxEndpointForm(
            data=_form_data(
                ssh_credential_source=SSH_CRED_SOURCE_REUSE,
                ssh_known_host_fingerprint=FINGERPRINT,
            )
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())

    def test_form_reuse_rejects_token_only_endpoint(self):
        form = ProxmoxEndpointForm(
            data=_form_data(
                password="",
                token_name="root@pam!token",
                token_value="token-secret",
                ssh_credential_source=SSH_CRED_SOURCE_REUSE,
                ssh_known_host_fingerprint=FINGERPRINT,
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ssh_credential_source", form.errors)

    def test_form_dedicated_remains_optional_until_any_ssh_field_is_set(self):
        form = ProxmoxEndpointForm(data=_form_data())

        self.assertTrue(form.is_valid(), form.errors.as_data())
