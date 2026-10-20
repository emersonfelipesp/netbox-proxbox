"""Real-NetBox coverage for endpoint-scoped Proxmox operational actions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = netbox_source_roots(REPO_ROOT)
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
    pytest.skip("Django/NetBox is unavailable.", allow_module_level=True)

if not hasattr(django, "__path__"):
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
    pytest.skip(
        "The mocked suite does not provide real Django.", allow_module_level=True
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is unavailable: {exc}", allow_module_level=True
    )

from django.contrib.auth.models import Permission  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.http import HttpResponse, JsonResponse  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from virtualization.models import Cluster, ClusterType, VirtualMachine  # noqa: E402

from netbox_proxbox.api import proxmox_tags  # noqa: E402
from netbox_proxbox.api import views as api_views  # noqa: E402
from netbox_proxbox.choices import FirewallRuleTypeChoices, FirewallZoneChoices  # noqa: E402
from netbox_proxbox.intent import firewall_common  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    ProxboxVirtualMachineSyncState,
    ProxmoxEndpoint,
    ProxmoxFirewallRule,
)
from netbox_proxbox.views import firewall, operational, proxmox_create_instance  # noqa: E402
from tests.django_support import (  # noqa: E402
    create_legacy_proxmox_cluster,
    grant_user_permissions,
    make_api_token,
    make_user,
)


def _grant(
    user: object,
    model: type,
    actions: list[str],
    *,
    constraints: dict[str, object] | None = None,
) -> None:
    permission = ObjectPermission.objects.create(
        name=f"operational {'/'.join(actions)} {model._meta.label} {user.username}",
        actions=actions,
        constraints=constraints,
    )
    permission.object_types.add(ContentType.objects.get_for_model(model))
    permission.users.add(user)


class OperationalPermissionTests(TestCase):
    """Operational actions honor endpoint scope, compatibility, and token scope."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint_a = ProxmoxEndpoint.objects.create(
            name="operational-a",
            enabled=True,
            allow_writes=True,
            allow_packer_template_builds=True,
        )
        cls.endpoint_b = ProxmoxEndpoint.objects.create(
            name="operational-b",
            enabled=True,
            allow_writes=True,
            allow_packer_template_builds=True,
        )
        cluster_type = ClusterType.objects.create(
            name="Operational", slug="operational"
        )
        cls.vm_a = cls._create_vm("operational-vm-a", cls.endpoint_a, cluster_type, 201)
        cls.vm_b = cls._create_vm("operational-vm-b", cls.endpoint_b, cluster_type, 202)
        cls.lxc_a = cls._create_vm(
            "operational-lxc-a",
            cls.endpoint_a,
            cluster_type,
            203,
            vm_type="lxc",
        )
        cls.rule_a = cls._create_rule(cls.endpoint_a, 1)
        cls.rule_b = cls._create_rule(cls.endpoint_b, 2)

        cls.operator = make_user("operational-operator", is_staff=True)
        _grant(
            cls.operator,
            ProxmoxEndpoint,
            ["view", "add"],
        )
        _grant(
            cls.operator,
            ProxmoxEndpoint,
            ["run_proxmox_action"],
            constraints={"pk": cls.endpoint_a.pk},
        )
        _grant(cls.operator, VirtualMachine, ["view"])
        _grant(cls.operator, ProxmoxFirewallRule, ["view", "add", "change"])

        cls.ungranted = make_user("operational-ungranted", is_staff=True)
        _grant(cls.ungranted, VirtualMachine, ["view"])

        cls.action_only = make_user("operational-action-only", is_staff=True)
        _grant(
            cls.action_only,
            ProxmoxEndpoint,
            ["run_proxmox_action"],
            constraints={"pk": cls.endpoint_a.pk},
        )

        cls.no_firewall_add = make_user("operational-no-firewall-add", is_staff=True)
        _grant(
            cls.no_firewall_add,
            ProxmoxEndpoint,
            ["view", "run_proxmox_action"],
            constraints={"pk": cls.endpoint_a.pk},
        )
        _grant(cls.no_firewall_add, ProxmoxFirewallRule, ["view", "change"])

        cls.legacy = make_user("operational-legacy", is_staff=True)
        _grant(cls.legacy, VirtualMachine, ["view"])
        legacy_type = ContentType.objects.get(app_label="core", model="objecttype")
        legacy_permission, _created = Permission.objects.get_or_create(
            content_type=legacy_type,
            codename="run_proxmox_action",
            defaults={"name": "Can run Proxmox operational actions"},
        )
        grant_user_permissions(cls.legacy, [legacy_permission])
        cls.legacy = type(cls.legacy).objects.get(pk=cls.legacy.pk)

    @classmethod
    def _create_vm(
        cls,
        name: str,
        endpoint: ProxmoxEndpoint,
        cluster_type: ClusterType,
        vmid: int,
        *,
        vm_type: str = "qemu",
    ) -> VirtualMachine:
        cluster = Cluster.objects.create(name=name, type=cluster_type)
        proxmox_cluster = create_legacy_proxmox_cluster(
            endpoint=endpoint,
            netbox_cluster=cluster,
            name=name,
        )
        vm = VirtualMachine.objects.create(name=name, cluster=cluster, status="active")
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=vm,
            endpoint=endpoint,
            proxmox_cluster=proxmox_cluster,
            proxmox_cluster_name=name,
            proxmox_node_name="pve1",
            proxmox_endpoint_raw_id=endpoint.pk,
            proxmox_vm_id=vmid,
            proxmox_vm_type=vm_type,
        )
        return vm

    @staticmethod
    def _create_rule(endpoint: ProxmoxEndpoint, position: int) -> ProxmoxFirewallRule:
        return ProxmoxFirewallRule.objects.create(
            endpoint=endpoint,
            zone=FirewallZoneChoices.DATACENTER,
            pos=position,
            rule_type=FirewallRuleTypeChoices.IN,
            action="ACCEPT",
        )

    def _session_client(self, user: object) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def _token_client(self, *, write_enabled: bool) -> tuple[Client, dict[str, str]]:
        token, headers = make_api_token(self.operator)
        token.write_enabled = write_enabled
        token.save(update_fields=["write_enabled"])
        return Client(), headers

    @staticmethod
    def _operational_url(vm: VirtualMachine, action: str) -> str:
        return reverse(
            f"virtualization:virtualmachine_proxbox_operational_{action}",
            args=[vm.pk],
        )

    @staticmethod
    def _firewall_push_url(rule: ProxmoxFirewallRule) -> str:
        return reverse(
            "plugins:netbox_proxbox:proxmoxfirewallrule_push_to_proxmox",
            args=[rule.pk],
        )

    @staticmethod
    def _firewall_preview_url(rule: ProxmoxFirewallRule) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:proxmoxfirewallrule-preview",
            args=[rule.pk],
        )

    @staticmethod
    def _firewall_api_push_url(rule: ProxmoxFirewallRule) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:proxmoxfirewallrule-push",
            args=[rule.pk],
        )

    @staticmethod
    def _firewall_bulk_push_url() -> str:
        return reverse(
            "plugins:netbox_proxbox:proxmoxfirewallrule_bulk_push",
        )

    @staticmethod
    def _firewall_api_bulk_push_url() -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:proxmoxfirewallrule-bulk-push",
        )

    @staticmethod
    def _tags_url(vm: VirtualMachine) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:api-virtual-machines-proxmox-tags",
            args=[vm.pk],
        )

    @staticmethod
    def _lxc_tags_url(vm: VirtualMachine) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:api-lxc-containers-proxmox-tags",
            args=[vm.pk],
        )

    @staticmethod
    def _template_build_url(endpoint: ProxmoxEndpoint) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-build-pve-template",
            args=[endpoint.pk],
        )

    @staticmethod
    def _cloud_pipeline_url(endpoint: ProxmoxEndpoint) -> str:
        return reverse(
            "plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-cloud-image-build-pipeline",
            args=[endpoint.pk],
        )

    @staticmethod
    def _create_instance_url(endpoint: ProxmoxEndpoint) -> str:
        return reverse(
            "plugins:netbox_proxbox:proxmoxendpoint_create_instance",
            args=[endpoint.pk],
        )

    @override_settings(LOGIN_REQUIRED=True)
    def test_object_grant_is_scoped_and_legacy_permission_remains_valid(self) -> None:
        forward = HttpResponse(status=204)
        with patch.object(operational, "_forward_verb", return_value=forward):
            client = self._session_client(self.operator)
            self.assertEqual(
                client.post(self._operational_url(self.vm_a, "start")).status_code,
                204,
            )
            self.assertEqual(
                client.post(self._operational_url(self.vm_b, "start")).status_code,
                404,
            )
            self.assertEqual(
                self._session_client(self.ungranted)
                .post(self._operational_url(self.vm_a, "start"))
                .status_code,
                403,
            )
            user_class = type(self.legacy)
            original_has_perm = user_class.has_perm

            def _legacy_backend(user, permission, obj=None):
                if (
                    user.pk == self.legacy.pk
                    and permission == "core.run_proxmox_action"
                ):
                    return True
                return original_has_perm(user, permission, obj)

            with patch.object(user_class, "has_perm", _legacy_backend):
                self.assertEqual(
                    self._session_client(self.legacy)
                    .post(self._operational_url(self.vm_b, "start"))
                    .status_code,
                    204,
                )
            self.assertNotEqual(
                Client().post(self._operational_url(self.vm_a, "start")).status_code,
                204,
            )

    def test_migrate_and_firewall_preview_enforce_endpoint_scope(self) -> None:
        client = self._session_client(self.operator)
        with patch.object(
            operational, "_forward_verb", return_value=HttpResponse(status=204)
        ):
            self.assertEqual(
                client.post(
                    self._operational_url(self.vm_a, "migrate"),
                    {"target": "pve2"},
                ).status_code,
                204,
            )
            self.assertEqual(
                client.post(
                    self._operational_url(self.vm_b, "migrate"),
                    {"target": "pve2"},
                ).status_code,
                404,
            )

        firewall_result = SimpleNamespace(status="ok")
        with patch.object(
            firewall, "push_firewall_object", return_value=firewall_result
        ):
            self.assertEqual(
                client.post(self._firewall_push_url(self.rule_a)).status_code, 302
            )
            self.assertEqual(
                client.post(self._firewall_push_url(self.rule_b)).status_code, 404
            )

        token, headers = make_api_token(self.operator)
        token.write_enabled = False
        token.save(update_fields=["write_enabled"])
        preview = SimpleNamespace(to_response=lambda: {"status": "ok"})
        with patch.object(api_views, "preview_firewall_object", return_value=preview):
            self.assertEqual(
                Client()
                .get(self._firewall_preview_url(self.rule_a), **headers)
                .status_code,
                200,
            )
            self.assertEqual(
                Client()
                .get(self._firewall_preview_url(self.rule_b), **headers)
                .status_code,
                404,
            )
        token.write_enabled = True
        token.save(update_fields=["write_enabled"])
        api_push_result = SimpleNamespace(to_response=lambda: {"status": "ok"})
        with patch.object(
            api_views, "push_firewall_object", return_value=api_push_result
        ):
            self.assertEqual(
                Client()
                .post(self._firewall_api_push_url(self.rule_a), **headers)
                .status_code,
                200,
            )
            self.assertEqual(
                Client()
                .post(self._firewall_api_push_url(self.rule_b), **headers)
                .status_code,
                404,
            )
            self.assertEqual(
                Client()
                .post(
                    self._firewall_api_bulk_push_url(),
                    data=json.dumps({"ids": [self.rule_b.pk]}),
                    content_type="application/json",
                    **headers,
                )
                .status_code,
                403,
            )

    def test_tags_enforce_endpoint_scope(self) -> None:
        client, headers = self._token_client(write_enabled=True)
        context = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={},
            verify_ssl=True,
        )
        backend_response = SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {"ok": True, "tags_after": ["safe"]},
        )
        backend_ids = {
            self.endpoint_a.pk: 701,
            self.endpoint_b.pk: self.endpoint_a.pk,
        }

        def resolve_target(*, endpoint, user, **_kwargs):
            if endpoint.pk != self.endpoint_a.pk:
                raise proxmox_tags.OperationalTargetError(
                    "permission_denied",
                    "Proxmox endpoint is outside the operational permission scope.",
                    404,
                )
            return SimpleNamespace(
                endpoint=endpoint,
                backend_endpoint_id=backend_ids[endpoint.pk],
                context=context,
            )

        with (
            patch.object(
                proxmox_tags,
                "resolve_operational_target",
                side_effect=resolve_target,
            ),
            patch.object(
                proxmox_tags.requests,
                "request",
                return_value=backend_response,
            ) as backend_request,
        ):
            allowed = client.put(
                self._tags_url(self.vm_a),
                data=json.dumps({"tags": ["safe"]}),
                content_type="application/json",
                **headers,
            )
            denied = client.put(
                self._tags_url(self.vm_b),
                data=json.dumps({"tags": ["safe"]}),
                content_type="application/json",
                **headers,
            )

        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(denied.status_code, 404, denied.content)
        backend_request.assert_called_once()
        self.assertEqual(
            backend_request.call_args.kwargs["params"], {"endpoint_id": 701}
        )
        self.assertNotEqual(701, self.endpoint_a.pk)

    def test_operational_verb_uses_translated_backend_identity(self) -> None:
        client = self._session_client(self.operator)
        context = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={},
            verify_ssl=True,
        )
        backend_response = SimpleNamespace(
            status_code=202,
            text="",
            json=lambda: {"status": "accepted"},
        )
        with (
            patch.object(
                operational,
                "resolve_operational_target",
                side_effect=lambda **kwargs: SimpleNamespace(
                    endpoint=kwargs["endpoint"],
                    backend_endpoint_id=701,
                    context=context,
                ),
            ),
            patch.object(
                operational.requests,
                "post",
                return_value=backend_response,
            ) as backend_post,
        ):
            allowed = client.post(self._operational_url(self.vm_a, "start"))
            denied = client.post(self._operational_url(self.vm_b, "start"))

        self.assertEqual(allowed.status_code, 302, allowed.content)
        self.assertEqual(denied.status_code, 404, denied.content)
        backend_post.assert_called_once()
        self.assertEqual(backend_post.call_args.kwargs["params"], {"endpoint_id": 701})
        self.assertNotEqual(701, self.endpoint_a.pk)

    def test_real_firewall_preview_uses_only_the_authorized_backend_scope(self) -> None:
        context = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={"Authorization": "redacted"},
            verify_ssl=True,
        )
        calls: list[dict[str, object]] = []
        endpoint_a_name = self.endpoint_a.name
        endpoint_b_name = self.endpoint_b.name
        endpoint_a_pk = self.endpoint_a.pk
        rule_position = self.rule_a.pos

        class Client:
            def get(self, _url, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    status_code=200,
                    text="",
                    json=lambda: [
                        {
                            "cluster_name": endpoint_b_name,
                            "backend_endpoint_id": endpoint_a_pk,
                            "pos": rule_position,
                            "action": "DROP",
                        },
                        {
                            "cluster_name": endpoint_a_name,
                            "backend_endpoint_id": 701,
                            "pos": rule_position,
                            "action": "ACCEPT",
                        },
                    ],
                )

        with (
            patch.object(
                firewall_common,
                "resolve_operational_target",
                return_value=SimpleNamespace(
                    endpoint=self.endpoint_a,
                    backend_endpoint_id=701,
                    context=context,
                ),
            ),
            patch.object(
                firewall_common,
                "enabled_backend_endpoint_scope",
                return_value=(
                    {"source": "database", "proxmox_endpoint_ids": "701"},
                    {self.endpoint_a.pk: 701},
                    None,
                ),
            ),
        ):
            result = firewall_common.preview_firewall_object(
                self.rule_a,
                user=self.operator,
                client=Client(),
            )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.proxmox_state["backend_endpoint_id"], 701)
        self.assertEqual(
            calls[0]["params"],
            {"source": "database", "proxmox_endpoint_ids": "701"},
        )

    def _vm_firewall_rule(
        self,
        *,
        endpoint: ProxmoxEndpoint,
        vm: VirtualMachine,
        position: int,
    ) -> ProxmoxFirewallRule:
        return ProxmoxFirewallRule.objects.create(
            endpoint=endpoint,
            zone=FirewallZoneChoices.VM_QEMU,
            virtual_machine=vm,
            pos=position,
            rule_type=FirewallRuleTypeChoices.IN,
            action="ACCEPT",
        )

    def test_vm_firewall_refuses_missing_authoritative_identity_without_io(
        self,
    ) -> None:
        vm = VirtualMachine.objects.create(
            name="firewall-missing-identity",
            cluster=self.vm_a.cluster,
            status="active",
        )
        rule = self._vm_firewall_rule(endpoint=self.endpoint_a, vm=vm, position=31)
        client = SimpleNamespace(calls=[])

        with (
            patch.object(firewall_common, "resolve_operational_target") as resolve,
            self.assertRaises(firewall_common.FirewallPushError) as raised,
        ):
            firewall_common.push_firewall_object(
                rule, actor=self.operator.username, user=self.operator, client=client
            )

        self.assertEqual(raised.exception.reason, "vm_endpoint_identity_required")
        resolve.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_vm_firewall_refuses_disabled_authoritative_identity_without_io(
        self,
    ) -> None:
        rule = self._vm_firewall_rule(
            endpoint=self.endpoint_b, vm=self.vm_b, position=32
        )
        self.endpoint_b.enabled = False
        self.endpoint_b.save(update_fields=["enabled"])
        self.vm_b.refresh_from_db()
        client = SimpleNamespace(calls=[])
        try:
            with (
                patch.object(firewall_common, "resolve_operational_target") as resolve,
                self.assertRaises(firewall_common.FirewallPushError) as raised,
            ):
                firewall_common.push_firewall_object(
                    rule,
                    actor=self.operator.username,
                    user=self.operator,
                    client=client,
                )
        finally:
            self.endpoint_b.enabled = True
            self.endpoint_b.save(update_fields=["enabled"])

        self.assertEqual(raised.exception.reason, "endpoint_disabled")
        resolve.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_vm_firewall_refuses_conflicting_endpoint_with_colliding_vmid(self) -> None:
        state = self.vm_b.proxbox_sync_state
        state.proxmox_vm_id = self.vm_a.proxbox_sync_state.proxmox_vm_id
        state.save(update_fields=["proxmox_vm_id"])
        self.vm_b.refresh_from_db()
        rule = self._vm_firewall_rule(
            endpoint=self.endpoint_a, vm=self.vm_b, position=33
        )
        client = SimpleNamespace(calls=[])

        with (
            patch.object(firewall_common, "resolve_operational_target") as resolve,
            self.assertRaises(firewall_common.FirewallPushError) as raised,
        ):
            firewall_common.push_firewall_object(
                rule, actor=self.operator.username, user=self.operator, client=client
            )

        self.assertEqual(raised.exception.reason, "endpoint_mismatch")
        resolve.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_vm_firewall_accepts_consistent_authoritative_identity(self) -> None:
        rule = self._vm_firewall_rule(
            endpoint=self.endpoint_a, vm=self.vm_a, position=34
        )
        context = SimpleNamespace(
            http_url="https://backend-a.example.test",
            headers={},
            verify_ssl=True,
        )
        target = SimpleNamespace(
            endpoint=self.endpoint_a,
            backend_endpoint_id=701,
            context=context,
        )

        class Client:
            calls: list[tuple[str, dict[str, object]]] = []

            def post(self, url: str, **kwargs: object) -> SimpleNamespace:
                self.calls.append((url, kwargs))
                return SimpleNamespace(
                    status_code=200,
                    text='{"status": "pushed"}',
                    json=lambda: {"status": "pushed"},
                )

        client = Client()
        with patch.object(
            firewall_common, "resolve_operational_target", return_value=target
        ):
            result = firewall_common.push_firewall_object(
                rule, actor=self.operator.username, user=self.operator, client=client
            )

        self.assertEqual(result.status, "pushed")
        self.assertIn("endpoint_id=701", client.calls[0][0])
        self.assertNotIn(f"endpoint_id={self.endpoint_a.pk}", client.calls[0][0])

    def test_disabled_firewall_endpoint_blocks_all_api_backend_calls(self) -> None:
        self.endpoint_a.enabled = False
        self.endpoint_a.save(update_fields=["enabled"])
        client = self._session_client(self.operator)
        with (
            patch.object(api_views, "push_firewall_object") as push,
            patch.object(api_views, "preview_firewall_object") as preview,
        ):
            responses = (
                client.post(self._firewall_api_push_url(self.rule_a)),
                client.get(self._firewall_preview_url(self.rule_a)),
                client.post(
                    self._firewall_api_bulk_push_url(),
                    data=json.dumps({"ids": [self.rule_a.pk]}),
                    content_type="application/json",
                ),
            )

        self.assertEqual([response.status_code for response in responses], [403] * 3)
        push.assert_not_called()
        preview.assert_not_called()

    @override_settings(LOGIN_REQUIRED=True)
    def test_read_only_tokens_are_rejected_on_every_write_surface(self) -> None:
        client, headers = self._token_client(write_enabled=False)
        with (
            patch.object(operational, "_forward_verb") as forward,
            patch.object(firewall, "push_firewall_object") as firewall_push,
            patch.object(api_views, "push_firewall_object") as api_firewall_push,
            patch.object(proxmox_tags, "_forward_tags_request") as tags_forward,
            patch.object(
                api_views.ProxmoxEndpointViewSet, "_template_build_payload"
            ) as template_payload,
            patch.object(api_views, "build_pve_template_via_backend") as pve_build,
            patch.object(
                api_views, "build_cloud_image_pipeline_via_backend"
            ) as cloud_build,
            patch.object(
                proxmox_create_instance, "_create_instance_branch_precondition"
            ) as branch_check,
            patch.object(proxmox_create_instance, "_provision_qemu") as qemu_create,
            patch.object(proxmox_create_instance, "_provision_lxc") as lxc_create,
        ):
            requests = (
                client.post(self._operational_url(self.vm_a, "start"), **headers),
                client.post(self._operational_url(self.vm_a, "stop"), **headers),
                client.post(self._operational_url(self.vm_a, "snapshot"), **headers),
                client.post(
                    self._operational_url(self.vm_a, "migrate"),
                    {"target": "pve2"},
                    **headers,
                ),
                client.post(self._firewall_push_url(self.rule_a), **headers),
                client.post(
                    self._firewall_bulk_push_url(),
                    {"pk": [self.rule_a.pk], "return_url": "/"},
                    **headers,
                ),
                client.post(self._firewall_api_push_url(self.rule_a), **headers),
                client.post(
                    self._firewall_api_bulk_push_url(),
                    data=json.dumps({"ids": [self.rule_a.pk]}),
                    content_type="application/json",
                    **headers,
                ),
                client.put(
                    self._tags_url(self.vm_a),
                    data=json.dumps({"tags": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.patch(
                    self._tags_url(self.vm_a),
                    data=json.dumps({"add": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.put(
                    self._lxc_tags_url(self.lxc_a),
                    data=json.dumps({"tags": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.patch(
                    self._lxc_tags_url(self.lxc_a),
                    data=json.dumps({"remove": ["old"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._template_build_url(self.endpoint_a),
                    data=json.dumps({"vmid": 900}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._cloud_pipeline_url(self.endpoint_a),
                    data=json.dumps({"vmid": 901}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "qemu"}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "lxc"}),
                    content_type="application/json",
                    **headers,
                ),
            )

        self.assertEqual([response.status_code for response in requests], [403] * 16)
        self.assertIn(b"does not allow write operations", requests[0].content)
        forward.assert_not_called()
        firewall_push.assert_not_called()
        api_firewall_push.assert_not_called()
        tags_forward.assert_not_called()
        template_payload.assert_not_called()
        pve_build.assert_not_called()
        cloud_build.assert_not_called()
        branch_check.assert_not_called()
        qemu_create.assert_not_called()
        lxc_create.assert_not_called()

    @override_settings(LOGIN_REQUIRED=True)
    def test_anonymous_requests_never_reach_operational_handlers(self) -> None:
        client = Client()
        with (
            patch.object(operational, "_forward_verb") as forward,
            patch.object(firewall, "push_firewall_object") as firewall_push,
            patch.object(api_views, "push_firewall_object") as api_firewall_push,
            patch.object(proxmox_tags, "_forward_tags_request") as tags_forward,
            patch.object(
                api_views.ProxmoxEndpointViewSet, "_template_build_payload"
            ) as template_payload,
            patch.object(
                proxmox_create_instance, "_create_instance_branch_precondition"
            ) as branch_check,
        ):
            responses = (
                client.post(self._operational_url(self.vm_a, "start")),
                client.post(
                    self._operational_url(self.vm_a, "migrate"),
                    {"target": "pve2"},
                ),
                client.post(self._firewall_push_url(self.rule_a)),
                client.post(self._firewall_api_push_url(self.rule_a)),
                client.put(
                    self._tags_url(self.vm_a),
                    data=json.dumps({"tags": ["safe"]}),
                    content_type="application/json",
                ),
                client.post(
                    self._template_build_url(self.endpoint_a),
                    data=json.dumps({"vmid": 900}),
                    content_type="application/json",
                ),
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "qemu"}),
                    content_type="application/json",
                ),
            )

        self.assertTrue(
            all(response.status_code in {302, 403} for response in responses)
        )
        forward.assert_not_called()
        firewall_push.assert_not_called()
        api_firewall_push.assert_not_called()
        tags_forward.assert_not_called()
        template_payload.assert_not_called()
        branch_check.assert_not_called()

    @override_settings(LOGIN_REQUIRED=True)
    def test_write_enabled_tokens_reach_every_write_surface(self) -> None:
        client, headers = self._token_client(write_enabled=True)
        firewall_result = SimpleNamespace(status="ok")
        api_firewall_result = SimpleNamespace(to_response=lambda: {"status": "ok"})
        context = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={},
            verify_ssl=True,
            endpoint_id=1,
        )
        with (
            patch.object(
                operational, "_forward_verb", return_value=HttpResponse(status=204)
            ),
            patch.object(
                firewall, "push_firewall_object", return_value=firewall_result
            ),
            patch.object(
                api_views,
                "push_firewall_object",
                return_value=api_firewall_result,
            ),
            patch.object(
                proxmox_tags,
                "_forward_tags_request",
                return_value=Response({"ok": True}),
            ),
            patch.object(
                api_views.ProxmoxEndpointViewSet,
                "_template_build_payload",
                return_value=({}, SimpleNamespace(context=context), None),
            ),
            patch.object(
                api_views,
                "build_pve_template_via_backend",
                return_value=({"status": "ok"}, 200),
            ),
            patch.object(
                api_views,
                "build_cloud_image_pipeline_via_backend",
                return_value=({"status": "ok"}, 200),
            ),
            patch.object(
                proxmox_create_instance,
                "_create_instance_branch_precondition",
                return_value=None,
            ),
            patch.object(
                proxmox_create_instance,
                "validate_create_instance_payload",
                side_effect=lambda data: (
                    str(data.get("kind")),
                    {"target_node": "pve1"},
                ),
            ),
            patch.object(
                proxmox_create_instance,
                "resolve_operational_target",
                side_effect=lambda **kwargs: SimpleNamespace(
                    endpoint=kwargs["endpoint"],
                    backend_endpoint_id=701,
                    context=context,
                ),
            ),
            patch.object(
                proxmox_create_instance,
                "_provision_qemu",
                return_value=JsonResponse({"ok": True}),
            ),
            patch.object(
                proxmox_create_instance,
                "_provision_lxc",
                return_value=JsonResponse({"ok": True}),
            ),
        ):
            responses = (
                client.post(self._operational_url(self.vm_a, "start"), **headers),
                client.post(self._operational_url(self.vm_a, "stop"), **headers),
                client.post(self._operational_url(self.vm_a, "snapshot"), **headers),
                client.post(
                    self._operational_url(self.vm_a, "migrate"),
                    {"target": "pve2"},
                    **headers,
                ),
                client.post(self._firewall_push_url(self.rule_a), **headers),
                client.post(
                    self._firewall_bulk_push_url(),
                    {"pk": [self.rule_a.pk], "return_url": "/"},
                    **headers,
                ),
                client.post(self._firewall_api_push_url(self.rule_a), **headers),
                client.post(
                    self._firewall_api_bulk_push_url(),
                    data=json.dumps({"ids": [self.rule_a.pk]}),
                    content_type="application/json",
                    **headers,
                ),
                client.put(
                    self._tags_url(self.vm_a),
                    data=json.dumps({"tags": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.patch(
                    self._tags_url(self.vm_a),
                    data=json.dumps({"add": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.put(
                    self._lxc_tags_url(self.lxc_a),
                    data=json.dumps({"tags": ["safe"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.patch(
                    self._lxc_tags_url(self.lxc_a),
                    data=json.dumps({"remove": ["old"]}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._template_build_url(self.endpoint_a),
                    data=json.dumps({"vmid": 900}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._cloud_pipeline_url(self.endpoint_a),
                    data=json.dumps({"vmid": 901}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "qemu"}),
                    content_type="application/json",
                    **headers,
                ),
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "lxc"}),
                    content_type="application/json",
                    **headers,
                ),
            )

        self.assertEqual(
            [response.status_code for response in responses],
            [204] * 4 + [302] * 2 + [200] * 10,
        )

    def test_template_build_and_create_instance_use_the_target_endpoint(self) -> None:
        client = self._session_client(self.operator)
        context = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={},
            verify_ssl=True,
            endpoint_id=1,
        )
        target = SimpleNamespace(
            endpoint=self.endpoint_a,
            backend_endpoint_id=701,
            context=context,
        )
        with (
            patch.object(
                api_views,
                "resolve_authorized_template_build_target",
                return_value=target,
            ),
            patch.object(
                api_views,
                "build_pve_template_via_backend",
                return_value=({"status": "ok"}, 200),
            ) as pve_build,
            patch.object(
                api_views,
                "build_cloud_image_pipeline_via_backend",
                return_value=({"status": "ok"}, 200),
            ) as cloud_build,
            patch.object(
                proxmox_create_instance,
                "_create_instance_branch_precondition",
                return_value=None,
            ),
            patch.object(
                proxmox_create_instance,
                "validate_create_instance_payload",
                return_value=("qemu", {"target_node": "pve1"}),
            ),
            patch.object(
                proxmox_create_instance,
                "resolve_operational_target",
                side_effect=lambda **kwargs: SimpleNamespace(
                    endpoint=kwargs["endpoint"],
                    backend_endpoint_id=701,
                    context=context,
                ),
            ),
            patch.object(
                proxmox_create_instance,
                "_provision_qemu",
                return_value=JsonResponse({"ok": True}),
            ),
        ):
            response = client.post(
                self._template_build_url(self.endpoint_a),
                data=json.dumps({"vmid": 900}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(
                client.post(
                    self._template_build_url(self.endpoint_b),
                    data=json.dumps({"vmid": 901}),
                    content_type="application/json",
                ).status_code,
                404,
            )
            self.assertEqual(
                client.post(
                    self._cloud_pipeline_url(self.endpoint_a),
                    data=json.dumps({"vmid": 902}),
                    content_type="application/json",
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post(
                    self._cloud_pipeline_url(self.endpoint_b),
                    data=json.dumps({"vmid": 903}),
                    content_type="application/json",
                ).status_code,
                404,
            )
            self.assertEqual(
                client.post(
                    self._create_instance_url(self.endpoint_a),
                    data=json.dumps({"kind": "qemu"}),
                    content_type="application/json",
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post(
                    self._create_instance_url(self.endpoint_b),
                    data=json.dumps({"kind": "qemu"}),
                    content_type="application/json",
                ).status_code,
                404,
            )

        pve_build.assert_called_once()
        self.assertEqual(pve_build.call_args.args[0]["endpoint_id"], 701)
        self.assertIs(pve_build.call_args.kwargs["context"], context)
        cloud_build.assert_called_once()
        self.assertEqual(cloud_build.call_args.args[0]["endpoint_id"], 701)
        self.assertIs(cloud_build.call_args.kwargs["context"], context)

    def test_existing_endpoint_object_scopes_remain_required(self) -> None:
        client = self._session_client(self.action_only)
        self.assertEqual(
            client.post(
                self._template_build_url(self.endpoint_a),
                data=json.dumps({"vmid": 900}),
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self._session_client(self.no_firewall_add)
            .post(self._firewall_api_push_url(self.rule_a))
            .status_code,
            404,
        )
        self.assertEqual(
            client.post(
                self._create_instance_url(self.endpoint_a),
                data=json.dumps({"kind": "qemu"}),
                content_type="application/json",
            ).status_code,
            404,
        )
