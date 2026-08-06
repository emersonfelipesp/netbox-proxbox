"""NetBox-backed persistence tests for ``NodeSSHCredentialForm``."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.test import TestCase  # noqa: E402
from extras.models import Tag  # noqa: E402

from netbox_proxbox.forms.ssh_credential import NodeSSHCredentialForm  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxboxPluginSettings,
)
from netbox_proxbox.models.ssh_credential import (  # noqa: E402
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
)


FINGERPRINT = "SHA256:" + "A" * 43
ENCRYPTION_KEY = "0123456789abcdef0123456789abcdef"
PASSWORD = "form-regression-password"
PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "form-regression-private-key\n"
    "-----END OPENSSH PRIVATE KEY-----"
)
INITIAL_PRIVATE_KEY = "initial-private-key-must-not-render"


class NodeSSHCredentialFormPersistenceTest(TestCase):
    """Exercise the real NetBox form and TaggableManager save chain."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(
            name="ssh-form-endpoint", enabled=False
        )
        cls.node = ProxmoxNode.objects.create(
            endpoint=cls.endpoint,
            name="ssh-form-node",
            ip_address="192.0.2.96",
        )
        cls.tag = Tag.objects.create(name="SSH form regression")

    def setUp(self) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        settings_obj.encryption_key = ENCRYPTION_KEY
        settings_obj.save(update_fields=("encryption_key",))

    def _form_data(
        self,
        *,
        auth_method: str,
        tags: tuple[int, ...] = (),
        password: str = "",
        private_key: str = "",
    ) -> dict[str, object]:
        return {
            "node": self.node.pk,
            "username": "proxbox-discovery",
            "port": 22,
            "auth_method": auth_method,
            "known_host_fingerprint": FINGERPRINT,
            "sudo_required": True,
            "tags": tags,
            "password": password,
            "private_key": private_key,
        }

    def test_password_credential_saves_without_tags(self) -> None:
        form = NodeSSHCredentialForm(
            data=self._form_data(auth_method=AUTH_METHOD_PASSWORD, password=PASSWORD)
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        credential = form.save()

        self.assertNotEqual(credential.password_enc, PASSWORD)
        self.assertEqual(credential.get_password(key=ENCRYPTION_KEY), PASSWORD)
        self.assertEqual(list(credential.tags.all()), [])
        self.assertEqual(credential._m2m_values["tags"], [])

    def test_private_key_credential_saves_with_tags(self) -> None:
        form = NodeSSHCredentialForm(
            data=self._form_data(
                auth_method=AUTH_METHOD_KEY,
                private_key=PRIVATE_KEY,
                tags=(self.tag.pk,),
            )
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        credential = form.save()

        self.assertNotEqual(credential.private_key_enc, PRIVATE_KEY)
        self.assertEqual(credential.get_private_key(key=ENCRYPTION_KEY), PRIVATE_KEY)
        self.assertQuerySetEqual(credential.tags.all(), [self.tag], ordered=False)
        self.assertEqual(credential._m2m_values["tags"], [self.tag])

    def test_auth_method_requires_its_matching_secret(self) -> None:
        cases = (
            (AUTH_METHOD_PASSWORD, {"private_key": PRIVATE_KEY}),
            (AUTH_METHOD_KEY, {"password": PASSWORD}),
        )

        for auth_method, submitted_secret in cases:
            with self.subTest(auth_method=auth_method):
                form = NodeSSHCredentialForm(
                    data=self._form_data(
                        auth_method=auth_method,
                        **submitted_secret,
                    )
                )
                self.assertFalse(form.is_valid())
                self.assertIn("auth_method", form.errors)

    def test_plaintext_secret_requires_a_configured_encryption_key(self) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        settings_obj.encryption_key = ""
        settings_obj.save(update_fields=("encryption_key",))
        form = NodeSSHCredentialForm(
            data=self._form_data(auth_method=AUTH_METHOD_PASSWORD, password=PASSWORD)
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
        self.assertIn(
            "Configure ProxboxPluginSettings.encryption_key", str(form.errors)
        )
        self.assertNotIn(PASSWORD, str(form.errors))

    def test_invalid_bound_form_never_renders_submitted_secrets(self) -> None:
        data = self._form_data(
            auth_method=AUTH_METHOD_KEY,
            password=PASSWORD,
            private_key=PRIVATE_KEY,
        )
        data["known_host_fingerprint"] = "invalid-fingerprint"
        form = NodeSSHCredentialForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertEqual(form.cleaned_data["private_key"], PRIVATE_KEY)
        rendered = form.as_p()

        self.assertIn('name="password"', rendered)
        self.assertIn('name="private_key"', rendered)
        self.assertNotIn(PASSWORD, rendered)
        self.assertNotIn(PRIVATE_KEY, rendered)
        self.assertNotIn("form-regression-private-key", rendered)

    def test_unbound_form_never_renders_an_initial_private_key(self) -> None:
        form = NodeSSHCredentialForm(
            initial={"password": PASSWORD, "private_key": INITIAL_PRIVATE_KEY}
        )

        rendered = form.as_p()

        self.assertNotIn(PASSWORD, rendered)
        self.assertNotIn(INITIAL_PRIVATE_KEY, rendered)
