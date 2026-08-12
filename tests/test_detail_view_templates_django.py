"""Real-NetBox contracts for registered object-detail templates."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

# The mocked suite deliberately installs ``django`` as a plain module. Keep this
# file collectible there without letting a half-stubbed framework reach setup.
if not hasattr(django, "__path__"):
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
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

from django.apps import apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django.template.loader import get_template  # noqa: E402
from django.test import Client, SimpleTestCase, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils.module_loading import import_string  # noqa: E402
from netbox.registry import registry  # noqa: E402
from netbox.views.generic import ObjectView  # noqa: E402

from netbox_proxbox.choices import (  # noqa: E402
    FirewallRuleTypeChoices,
    FirewallScopeChoices,
    FirewallZoneChoices,
    SdnFabricTypeChoices,
)
from netbox_proxbox.models import (  # noqa: E402
    NodeSSHCredential,
    ProxmoxCluster,
    ProxmoxDatacenterCpuModel,
    ProxmoxEndpoint,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
    ProxmoxMetricsInfluxDB,
    ProxmoxNode,
    ProxmoxSdnBinding,
    ProxmoxSdnController,
    ProxmoxSdnFabric,
    ProxmoxSdnPrefixList,
    ProxmoxSdnRouteMap,
    ProxmoxSdnSubnet,
    ProxmoxSdnVNet,
    ProxmoxSdnZone,
)
from netbox_proxbox.models.ssh_credential import (  # noqa: E402
    AUTH_METHOD_PASSWORD,
)
from netbox_proxbox.models.proxmox_metrics import MASKED_SECRET_REF  # noqa: E402


_PLUGIN_VIEW_MODULE_PREFIX = "netbox_proxbox.views"
_METRICS_INFLUX_URL_MARKER = "raw-influx-url-must-not-render"
_REQUIRED_OBJECT_VIEW_REGISTRY = {
    "netbox_proxbox.backuproutine:backuproutine": "netbox_proxbox.views.backup_routine.BackupRoutineView",
    "netbox_proxbox.cloudimagetemplate:cloudimagetemplate": "netbox_proxbox.views.cloud_image_templates.CloudImageTemplateView",
    "netbox_proxbox.deletionrequest:deletionrequest": "netbox_proxbox.views.deletion_requests.DeletionRequestView",
    "netbox_proxbox.fastapiendpoint:fastapiendpoint": "netbox_proxbox.views.endpoints.fastapi.FastAPIEndpointView",
    "netbox_proxbox.fastapiendpoint:openapi": "netbox_proxbox.views.endpoints.fastapi.FastAPIOpenAPIView",
    "netbox_proxbox.guestvminterface:guestvminterface": "netbox_proxbox.views.guest_vm_interface.GuestVMInterfaceView",
    "netbox_proxbox.guestvminterfaceaddress:guestvminterfaceaddress": "netbox_proxbox.views.guest_vm_interface.GuestVMInterfaceAddressView",
    "netbox_proxbox.netboxendpoint:netboxendpoint": "netbox_proxbox.views.endpoints.netbox.NetBoxEndpointView",
    "netbox_proxbox.nodesshcredential:nodesshcredential": "netbox_proxbox.views.ssh_credential.NodeSSHCredentialView",
    "netbox_proxbox.pdmendpoint:pdmendpoint": "netbox_proxbox.views.endpoints.pdm.PDMEndpointView",
    "netbox_proxbox.proxmoxcluster:proxmoxcluster": "netbox_proxbox.views.proxmox_cluster_node.ProxmoxClusterView",
    "netbox_proxbox.proxmoxdatacentercpumodel:proxmoxdatacentercpumodel": "netbox_proxbox.views.datacenter.ProxmoxDatacenterCpuModelView",
    "netbox_proxbox.proxmoxendpoint:cluster_nodes": "netbox_proxbox.views.cluster_nodes_tab.ProxmoxEndpointClusterNodesTabView",
    "netbox_proxbox.proxmoxendpoint:overwrite_behavior": "netbox_proxbox.views.endpoints.proxmox.ProxmoxEndpointOverwriteBehaviorView",
    "netbox_proxbox.proxmoxendpoint:proxmoxendpoint": "netbox_proxbox.views.endpoints.proxmox.ProxmoxEndpointView",
    "netbox_proxbox.proxmoxendpoint:services": "netbox_proxbox.views.endpoints.proxmox.ProxmoxEndpointServicesView",
    "netbox_proxbox.proxmoxendpoint:ssh_terminal": "netbox_proxbox.views.endpoints.proxmox.ProxmoxEndpointSSHTerminalView",
    "netbox_proxbox.proxmoxendpoint:sync_jobs": "netbox_proxbox.views.endpoints.proxmox.ProxmoxEndpointSyncJobsTabView",
    "netbox_proxbox.proxmoxendpoint:templates": "netbox_proxbox.views.proxmox_templates_tab.ProxmoxEndpointTemplatesTabView",
    "netbox_proxbox.proxmoxfirewallalias:proxmoxfirewallalias": "netbox_proxbox.views.firewall.ProxmoxFirewallAliasView",
    "netbox_proxbox.proxmoxfirewallipset:proxmoxfirewallipset": "netbox_proxbox.views.firewall.ProxmoxFirewallIPSetView",
    "netbox_proxbox.proxmoxfirewallipsetentry:proxmoxfirewallipsetentry": "netbox_proxbox.views.firewall.ProxmoxFirewallIPSetEntryView",
    "netbox_proxbox.proxmoxfirewalloptions:proxmoxfirewalloptions": "netbox_proxbox.views.firewall.ProxmoxFirewallOptionsView",
    "netbox_proxbox.proxmoxfirewallrule:proxmoxfirewallrule": "netbox_proxbox.views.firewall.ProxmoxFirewallRuleView",
    "netbox_proxbox.proxmoxfirewallsecuritygroup:proxmoxfirewallsecuritygroup": "netbox_proxbox.views.firewall.ProxmoxFirewallSecurityGroupView",
    "netbox_proxbox.proxmoxmetricsinfluxdb:proxmoxmetricsinfluxdb": "netbox_proxbox.views.proxmox_metrics.ProxmoxMetricsInfluxDBView",
    "netbox_proxbox.proxmoxnode:proxmoxnode": "netbox_proxbox.views.proxmox_cluster_node.ProxmoxNodeView",
    "netbox_proxbox.proxmoxsdnbinding:proxmoxsdnbinding": "netbox_proxbox.views.sdn.ProxmoxSdnBindingView",
    "netbox_proxbox.proxmoxsdncontroller:proxmoxsdncontroller": "netbox_proxbox.views.sdn.ProxmoxSdnControllerView",
    "netbox_proxbox.proxmoxsdnfabric:proxmoxsdnfabric": "netbox_proxbox.views.sdn.ProxmoxSdnFabricView",
    "netbox_proxbox.proxmoxsdnprefixlist:proxmoxsdnprefixlist": "netbox_proxbox.views.sdn.ProxmoxSdnPrefixListView",
    "netbox_proxbox.proxmoxsdnroutemap:proxmoxsdnroutemap": "netbox_proxbox.views.sdn.ProxmoxSdnRouteMapView",
    "netbox_proxbox.proxmoxsdnsubnet:proxmoxsdnsubnet": "netbox_proxbox.views.sdn.ProxmoxSdnSubnetView",
    "netbox_proxbox.proxmoxsdnvnet:proxmoxsdnvnet": "netbox_proxbox.views.sdn.ProxmoxSdnVNetView",
    "netbox_proxbox.proxmoxsdnzone:proxmoxsdnzone": "netbox_proxbox.views.sdn.ProxmoxSdnZoneView",
    "netbox_proxbox.proxmoxstorage:backups": "netbox_proxbox.views.storage.ProxmoxStorageBackupsTabView",
    "netbox_proxbox.proxmoxstorage:proxmoxstorage": "netbox_proxbox.views.storage.ProxmoxStorageView",
    "netbox_proxbox.proxmoxstorage:snapshots": "netbox_proxbox.views.storage.ProxmoxStorageSnapshotsTabView",
    "netbox_proxbox.proxmoxstorage:virtual_disks": "netbox_proxbox.views.storage.ProxmoxStorageVirtualDisksTabView",
    "netbox_proxbox.proxmoxvmcloudinit:proxmoxvmcloudinit": "netbox_proxbox.views.vm_cloudinit.ProxmoxVMCloudInitView",
    "netbox_proxbox.proxmoxvmtemplate:proxmoxvmtemplate": "netbox_proxbox.views.vm_template.ProxmoxVMTemplateView",
    "netbox_proxbox.replication:replication": "netbox_proxbox.views.replication.ReplicationView",
    "netbox_proxbox.vmbackup:vmbackup": "netbox_proxbox.views.vm_backup.VMBackupView",
    "netbox_proxbox.vmsnapshot:vmsnapshot": "netbox_proxbox.views.vm_snapshot.VMSnapshotView",
    "netbox_proxbox.vmtaskhistory:vmtaskhistory": "netbox_proxbox.views.vm_task_history.VMTaskHistoryView",
    "virtualization.cluster:proxbox-storages": "netbox_proxbox.views.cluster.ClusterStoragesTabView",
    "virtualization.cluster:proxbox-summary": "netbox_proxbox.views.cluster.ClusterSummaryTabView",
    "virtualization.virtualmachine:backups": "netbox_proxbox.views.vm_backup.VMBackupTabView",
    "virtualization.virtualmachine:proxmox_cloudinit": "netbox_proxbox.views.vm_cloudinit.ProxmoxVMCloudInitTabView",
    "virtualization.virtualmachine:proxmox_config": "netbox_proxbox.views.vm_config.ProxmoxVMConfigTabView",
    "virtualization.virtualmachine:proxmox_ha": "netbox_proxbox.views.vm_ha.ProxmoxVMHATabView",
    "virtualization.virtualmachine:replications": "netbox_proxbox.views.replication.ReplicationTabView",
    "virtualization.virtualmachine:snapshots": "netbox_proxbox.views.vm_snapshot.VMSnapshotTabView",
    "virtualization.virtualmachine:task_history": "netbox_proxbox.views.vm_task_history.VMTaskHistoryTabView",
}
_SSH_PASSWORD_MARKER = "detail-view-password-must-not-render"
_SSH_PRIVATE_KEY_MARKER = "detail-view-private-key-must-not-render"
_METRICS_QUERY_TOKEN_MARKER = "detail-view-query-token-must-not-render"
_METRICS_WRITER_TOKEN_MARKER = "detail-view-writer-token-must-not-render"


def _registered_plugin_object_views() -> tuple[tuple[str, type[ObjectView]], ...]:
    """Return the plugin ObjectViews from NetBox's populated runtime registry."""
    # Importing the URL module executes every registration before inspection,
    # including views attached to NetBox core models.
    importlib.import_module("netbox_proxbox.urls")

    registrations: list[tuple[str, type[ObjectView]]] = []
    for app_label, model_views in registry["views"].items():
        for model_name, view_configs in model_views.items():
            for config in view_configs:
                if not config.get("detail", True):
                    continue
                view_class = config["view"]
                if isinstance(view_class, str):
                    view_class = import_string(view_class)
                if not isinstance(view_class, type) or not issubclass(
                    view_class, ObjectView
                ):
                    continue
                if not view_class.__module__.startswith(_PLUGIN_VIEW_MODULE_PREFIX):
                    continue
                view_name = config.get("name") or model_name
                registrations.append(
                    (f"{app_label}.{model_name}:{view_name}", view_class)
                )

    registrations.sort(key=lambda registration: registration[0])
    return tuple(registrations)


def _registered_detail_view(
    app_label: str, model_name: str, view_name: str
) -> type[ObjectView] | None:
    """Return one concrete detail-view registration by its exact identity."""
    for config in registry["views"].get(app_label, {}).get(model_name, ()):  # type: ignore[union-attr]
        if not config.get("detail", True):
            continue
        if (config.get("name") or model_name) != view_name:
            continue
        view_class = config["view"]
        if isinstance(view_class, str):
            view_class = import_string(view_class)
        if isinstance(view_class, type) and issubclass(view_class, ObjectView):
            return view_class
    return None


class RegisteredObjectViewTemplateRuntimeTest(SimpleTestCase):
    """Validate actual runtime template resolution for every plugin ObjectView."""

    def test_pdm_detail_override_is_class_aware_idempotent_and_strict(self) -> None:
        proxbox_urls = importlib.import_module("netbox_proxbox.urls")
        model_registry = registry["views"].setdefault("netbox_proxbox", {})
        model_name = proxbox_urls._PDM_ENDPOINT_MODEL_NAME
        had_registration = model_name in model_registry
        original_registration = list(model_registry.get(model_name, ()))
        PDMEndpointView = importlib.import_module(
            "netbox_proxbox.views.endpoints.pdm"
        ).PDMEndpointView

        CompanionDetailView = type("CompanionDetailView", (), {})
        OtherCompanionDetailView = type("OtherCompanionDetailView", (), {})
        own = {"view": PDMEndpointView, "detail": True, "name": ""}
        foreign = {"view": CompanionDetailView, "detail": True, "name": ""}
        named = {
            "view": OtherCompanionDetailView,
            "detail": True,
            "name": "sync_now",
        }
        non_detail = {
            "view": OtherCompanionDetailView,
            "detail": False,
            "name": "",
        }

        try:
            model_registry[model_name] = [foreign, named, own, non_detail]

            proxbox_urls._install_pdm_endpoint_detail_override()

            installed = model_registry[model_name]
            self.assertTrue(any(config is own for config in installed))
            self.assertFalse(any(config is foreign for config in installed))
            self.assertTrue(any(config is named for config in installed))
            self.assertTrue(any(config is non_detail for config in installed))
            self.assertEqual(len(installed), 3)

            proxbox_urls._install_pdm_endpoint_detail_override()
            self.assertIs(model_registry[model_name], installed)

            invalid_shapes = (
                ([], "found 0"),
                ([own, dict(own)], "found 2"),
                (
                    [
                        own,
                        foreign,
                        {
                            "view": OtherCompanionDetailView,
                            "detail": True,
                            "name": "",
                        },
                    ],
                    "2 companion base detail views",
                ),
            )
            for registrations, expected_message in invalid_shapes:
                with self.subTest(registrations=registrations):
                    model_registry[model_name] = registrations
                    with self.assertRaisesRegex(ImproperlyConfigured, expected_message):
                        proxbox_urls._install_pdm_endpoint_detail_override()
        finally:
            if had_registration:
                model_registry[model_name] = original_registration
            else:
                model_registry.pop(model_name, None)

    def test_runtime_registry_object_views_resolve_through_django_loader(self) -> None:
        registrations = _registered_plugin_object_views()
        actual_registry = {
            registry_name: f"{view_class.__module__}.{view_class.__qualname__}"
            for registry_name, view_class in registrations
        }
        expected_registry = dict(_REQUIRED_OBJECT_VIEW_REGISTRY)

        self.assertEqual(
            len(registrations),
            len(actual_registry),
            "Duplicate plugin ObjectView registry identifiers were loaded.",
        )
        self.assertEqual(
            actual_registry,
            expected_registry,
            "The runtime ObjectView registry drifted; update the explicit contract.",
        )

        for registry_name, view_class in registrations:
            with self.subTest(view=registry_name):
                template_name = view_class().get_template_name()
                self.assertIsInstance(template_name, str)
                self.assertTrue(template_name)
                self.assertIsNotNone(get_template(template_name))


class MissingDetailTemplateRenderTest(TestCase):
    """Authenticated GET smokes for all detail templates added by the bug fix."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            username="detail-template-viewer",
            is_superuser=True,
        )
        cls.endpoint = ProxmoxEndpoint.objects.create(name="detail-render-endpoint")
        cls.cluster = ProxmoxCluster.objects.create(
            endpoint=cls.endpoint,
            name="detail-render-cluster",
        )
        cls.node = ProxmoxNode.objects.create(
            endpoint=cls.endpoint,
            proxmox_cluster=cls.cluster,
            name="detail-render-node",
            ip_address="192.0.2.195",
        )
        cls.ssh_credential = NodeSSHCredential.objects.create(
            node=cls.node,
            username="detail-render-ssh-user",
            auth_method=AUTH_METHOD_PASSWORD,
            known_host_fingerprint=f"SHA256:{'A' * 43}",
            password_enc=_SSH_PASSWORD_MARKER,
            private_key_enc=_SSH_PRIVATE_KEY_MARKER,
        )
        cls.cpu_model = ProxmoxDatacenterCpuModel.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            cputype="detail-render-cpu",
        )
        cls.security_group = ProxmoxFirewallSecurityGroup.objects.create(
            endpoint=cls.endpoint,
            name="detail-render-security-group",
        )
        cls.firewall_rule = ProxmoxFirewallRule.objects.create(
            endpoint=cls.endpoint,
            zone=FirewallZoneChoices.DATACENTER,
            security_group=cls.security_group,
            pos=195,
            rule_type=FirewallRuleTypeChoices.IN,
            action="DETAIL-RENDER-ACCEPT",
        )
        cls.ipset = ProxmoxFirewallIPSet.objects.create(
            endpoint=cls.endpoint,
            scope=FirewallScopeChoices.DATACENTER,
            name="detail-render-ipset",
        )
        cls.ipset_entry = ProxmoxFirewallIPSetEntry.objects.create(
            ipset=cls.ipset,
            cidr="192.0.2.195/32",
        )
        cls.firewall_alias = ProxmoxFirewallAlias.objects.create(
            endpoint=cls.endpoint,
            scope=FirewallScopeChoices.DATACENTER,
            name="detail-render-alias",
            cidr="198.51.100.195/32",
        )
        cls.firewall_options = ProxmoxFirewallOptions.objects.create(
            endpoint=cls.endpoint,
            zone=FirewallZoneChoices.DATACENTER,
            policy_in="DETAIL-RENDER-DROP",
        )
        cls.metrics = ProxmoxMetricsInfluxDB.objects.create(
            name="detail-render-metrics",
            endpoint=cls.endpoint,
            proxmox_cluster=cls.cluster,
            influx_url="https://influx.example.test:8086",
            query_token_secret_ref="nms-secret:00000000-0000-4000-8000-000000000195",
        )
        cls.sdn_fabric = ProxmoxSdnFabric.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            fabric_name="detail-render-fabric",
            fabric_type=SdnFabricTypeChoices.BGP,
        )
        cls.sdn_controller = ProxmoxSdnController.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            controller_name="detail-render-controller",
        )
        cls.sdn_zone = ProxmoxSdnZone.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            zone_name="detail-render-zone",
        )
        cls.sdn_vnet = ProxmoxSdnVNet.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            vnet_name="detail-render-vnet",
        )
        cls.sdn_subnet = ProxmoxSdnSubnet.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            vnet_name=cls.sdn_vnet.vnet_name,
            subnet="203.0.113.0/24",
        )
        cls.sdn_binding = ProxmoxSdnBinding.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            source_type="vnet",
            source_name="detail-render-binding",
        )
        cls.sdn_route_map = ProxmoxSdnRouteMap.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            name="detail-render-route-map",
        )
        cls.sdn_prefix_list = ProxmoxSdnPrefixList.objects.create(
            endpoint=cls.endpoint,
            cluster_name=cls.cluster.name,
            name="detail-render-prefix-list",
            cidr="2001:db8:195::/64",
        )

        cls.detail_pages = (
            (cls.ssh_credential, "detail-render-ssh-user"),
            (cls.cpu_model, "detail-render-cpu"),
            (cls.security_group, "detail-render-security-group"),
            (cls.firewall_rule, "DETAIL-RENDER-ACCEPT"),
            (cls.ipset, "detail-render-ipset"),
            (cls.ipset_entry, "192.0.2.195/32"),
            (cls.firewall_alias, "detail-render-alias"),
            (cls.firewall_options, "DETAIL-RENDER-DROP"),
            (cls.metrics, "detail-render-metrics"),
            (cls.sdn_fabric, "detail-render-fabric"),
            (cls.sdn_controller, "detail-render-controller"),
            (cls.sdn_zone, "detail-render-zone"),
            (cls.sdn_vnet, "detail-render-vnet"),
            (cls.sdn_subnet, "203.0.113.0/24"),
            (cls.sdn_binding, "detail-render-binding"),
            (cls.sdn_route_map, "detail-render-route-map"),
            (cls.sdn_prefix_list, "detail-render-prefix-list"),
        )

    def setUp(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)

    def test_all_added_detail_templates_render_for_authenticated_user(self) -> None:
        for instance, expected_text in self.detail_pages:
            model_name = instance._meta.model_name
            template_name = f"netbox_proxbox/{model_name}.html"
            url = reverse(f"plugins:netbox_proxbox:{model_name}", args=[instance.pk])
            with self.subTest(model=model_name, url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTemplateUsed(response, template_name)
                self.assertContains(response, expected_text)

    def test_node_ssh_credential_render_never_exposes_stored_secrets(self) -> None:
        url = reverse(
            "plugins:netbox_proxbox:nodesshcredential",
            args=[self.ssh_credential.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotContains(response, _SSH_PASSWORD_MARKER)
        self.assertNotContains(response, _SSH_PRIVATE_KEY_MARKER)

    def test_metrics_render_uses_fail_closed_display_properties(self) -> None:
        self.metrics.influx_url = _METRICS_INFLUX_URL_MARKER
        self.metrics.query_token_secret_ref = _METRICS_QUERY_TOKEN_MARKER
        self.metrics.writer_token_secret_ref = _METRICS_WRITER_TOKEN_MARKER
        url = reverse(
            "plugins:netbox_proxbox:proxmoxmetricsinfluxdb",
            args=[self.metrics.pk],
        )

        with patch(
            "netbox.views.generic.get_object_or_404",
            return_value=self.metrics,
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotContains(response, _METRICS_INFLUX_URL_MARKER)
        self.assertNotContains(response, _METRICS_QUERY_TOKEN_MARKER)
        self.assertNotContains(response, _METRICS_WRITER_TOKEN_MARKER)
        self.assertContains(response, MASKED_SECRET_REF, count=3)
        rendered_object = response.context["object"]
        self.assertEqual(rendered_object.influx_url_display, MASKED_SECRET_REF)
        self.assertEqual(
            rendered_object.query_token_secret_ref_display, MASKED_SECRET_REF
        )
        self.assertEqual(
            rendered_object.writer_token_secret_ref_display, MASKED_SECRET_REF
        )
