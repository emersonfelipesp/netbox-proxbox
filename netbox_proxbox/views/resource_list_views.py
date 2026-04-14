from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from netbox import configuration
from utilities.views import ConditionalLoginRequiredMixin
from virtualization.models import Cluster, VirtualDisk, VirtualMachine, VMInterface

from netbox_proxbox.utils import get_fastapi_context_for_request


class NodesView(ConditionalLoginRequiredMixin, View):
    """List NetBox devices tagged ``proxbox`` (synced nodes) for operational review."""

    template = "netbox_proxbox/devices.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load tagged devices and FastAPI URL hints for the devices template."""
        from dcim.models import Device
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "devices": [],
                },
            )

        device_content_type = ContentType.objects.get_for_model(Device)
        tagged_device_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=device_content_type
            ).values_list("object_id", flat=True)[:100]
        )
        devices = []
        if tagged_device_ids:
            devices = list(
                Device.objects.restrict(request.user, "view")
                .filter(id__in=tagged_device_ids)
                .select_related(
                    "device_type__manufacturer", "role", "site", "tenant", "cluster"
                )
                .prefetch_related("interfaces__ip_addresses")
            )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "devices": devices,
            },
        )


class VirtualMachinesView(ConditionalLoginRequiredMixin, View):
    """List VMs tagged ``proxbox`` for quick visibility alongside backend URLs."""

    template = "netbox_proxbox/virtual_machines.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load tagged VMs and FastAPI URL hints for the virtual machines template."""
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "virtual_machines": [],
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)[:100]
        )
        virtual_machines = []
        if tagged_vm_ids:
            base_qs = (
                VirtualMachine.objects.restrict(request.user, "view")
                .filter(id__in=tagged_vm_ids)
                .select_related(
                    "site",
                    "cluster",
                    "role",
                    "tenant",
                    "platform",
                    "virtual_machine_type",
                )
                .prefetch_related("interfaces__ip_addresses")
            )
            virtual_machines = list(
                base_qs.filter(virtual_machine_type__slug="qemu-virtual-machine")
            )
            if not virtual_machines:
                virtual_machines = list(
                    base_qs.filter(custom_field_data__proxmox_vm_type="qemu")
                )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "virtual_machines": virtual_machines,
            },
        )


class LXCContainersView(ConditionalLoginRequiredMixin, View):
    """List LXC containers tagged ``proxbox`` for quick visibility."""

    template = "netbox_proxbox/lxc_containers.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load tagged LXC containers and FastAPI URL hints for the template."""
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "lxc_containers": [],
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)[:100]
        )
        lxc_containers = []
        if tagged_vm_ids:
            base_qs = (
                VirtualMachine.objects.restrict(request.user, "view")
                .filter(id__in=tagged_vm_ids)
                .select_related(
                    "site",
                    "cluster",
                    "role",
                    "tenant",
                    "platform",
                    "virtual_machine_type",
                )
                .prefetch_related("interfaces__ip_addresses")
            )
            lxc_containers = list(
                base_qs.filter(virtual_machine_type__slug="lxc-container")
            )
            if not lxc_containers:
                lxc_containers = list(
                    base_qs.filter(custom_field_data__proxmox_vm_type="lxc")
                )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "lxc_containers": lxc_containers,
            },
        )


class VirtualDisksView(ConditionalLoginRequiredMixin, View):
    """List VirtualDisk objects whose parent VM is tagged ``proxbox``."""

    template_name = "netbox_proxbox/virtual_disks.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load proxbox-managed virtual disks for the template."""
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template_name,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "virtual_disks": [],
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        virtual_disks = []
        if tagged_vm_ids:
            virtual_disks = list(
                VirtualDisk.objects.restrict(request.user, "view")
                .filter(virtual_machine_id__in=tagged_vm_ids)
                .select_related("virtual_machine")
                .order_by("virtual_machine__name", "name")
            )

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "virtual_disks": virtual_disks,
            },
        )


class InterfacesView(ConditionalLoginRequiredMixin, View):
    """List all Proxbox-related interfaces (VM virtualization.Interfaces + node dcim.Interfaces).

    Shows a combined view of both VM and node interfaces that were synced from Proxmox,
    with summary counts for total, up, and down interfaces.
    """

    template_name = "netbox_proxbox/interfaces.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load proxbox-tagged VM interfaces and device interfaces."""
        from dcim.models import Device
        from dcim.models import Interface as DCIMInterface
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template_name,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "vm_interfaces": [],
                    "node_interfaces": [],
                    "interfaces_up": 0,
                    "interfaces_down": 0,
                    "interfaces_total": 0,
                },
            )

        device_content_type = ContentType.objects.get_for_model(Device)
        tagged_device_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=device_content_type
            ).values_list("object_id", flat=True)
        )

        vm_interfaces = []
        node_interfaces = []
        interfaces_up = 0
        interfaces_down = 0

        if tagged_device_ids:
            node_interfaces = list(
                DCIMInterface.objects.restrict(request.user, "view")
                .filter(device_id__in=tagged_device_ids)
                .select_related("device")
                .prefetch_related("ip_addresses")
                .order_by("device__name", "name")
            )
            for iface in node_interfaces:
                if iface.enabled:
                    interfaces_up += 1
                else:
                    interfaces_down += 1

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        if tagged_vm_ids:
            vm_interfaces = list(
                VMInterface.objects.restrict(request.user, "view")
                .filter(virtual_machine_id__in=tagged_vm_ids)
                .select_related("virtual_machine")
                .prefetch_related("ip_addresses")
                .order_by("virtual_machine__name", "name")
            )
            for iface in vm_interfaces:
                if iface.enabled:
                    interfaces_up += 1
                else:
                    interfaces_down += 1

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "vm_interfaces": vm_interfaces,
                "node_interfaces": node_interfaces,
                "interfaces_up": interfaces_up,
                "interfaces_down": interfaces_down,
                "interfaces_total": len(vm_interfaces) + len(node_interfaces),
            },
        )


class ClustersView(ConditionalLoginRequiredMixin, View):
    """List NetBox clusters tagged ``proxbox`` (synced Proxmox clusters) for operational review."""

    template = "netbox_proxbox/clusters.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load tagged clusters and FastAPI URL hints for the clusters template."""
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "clusters": [],
                },
            )

        cluster_content_type = ContentType.objects.get_for_model(Cluster)
        tagged_cluster_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=cluster_content_type
            ).values_list("object_id", flat=True)[:100]
        )
        clusters = []
        if tagged_cluster_ids:
            clusters = list(
                Cluster.objects.restrict(request.user, "view")
                .filter(id__in=tagged_cluster_ids)
                .select_related("type", "group", "site", "tenant")
            )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "clusters": clusters,
            },
        )


class IPAddressesView(ConditionalLoginRequiredMixin, View):
    """List all Proxbox-related IP addresses (linked to VM interfaces or node interfaces).

    Shows a combined view of IP addresses that were synced from Proxmox and assigned
    to Proxbox-managed interfaces, with summary counts.
    """

    template_name = "netbox_proxbox/ip_addresses.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load proxbox-tagged IP addresses assigned to proxbox interfaces."""
        from dcim.models import Device
        from dcim.models import Interface as DCIMInterface
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem
        from ipam.models import IPAddress

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        if not proxbox_tag:
            return render(
                request,
                self.template_name,
                {
                    "configuration": plugin_configuration,
                    "fastapi_url": fastapi_info.get("http_url", ""),
                    "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                    "vm_ips": [],
                    "node_ips": [],
                    "vm_ips_count": 0,
                    "node_ips_count": 0,
                    "total_ips": 0,
                },
            )

        device_content_type = ContentType.objects.get_for_model(Device)
        tagged_device_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=device_content_type
            ).values_list("object_id", flat=True)
        )
        vm_ips = []
        node_ips = []

        if tagged_device_ids:
            node_interface_ids = list(
                DCIMInterface.objects.filter(
                    device_id__in=tagged_device_ids
                ).values_list("id", flat=True)
            )
            node_ips = list(
                IPAddress.objects.restrict(request.user, "view")
                .filter(
                    assigned_object_type__app_label="dcim",
                    assigned_object_type__model="interface",
                    assigned_object_id__in=node_interface_ids,
                )
                .prefetch_related("assigned_object")
                .order_by("address")
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        if tagged_vm_ids:
            vm_interface_ids = list(
                VMInterface.objects.filter(
                    virtual_machine_id__in=tagged_vm_ids
                ).values_list("id", flat=True)
            )
            vm_ips = list(
                IPAddress.objects.restrict(request.user, "view")
                .filter(
                    assigned_object_type__app_label="virtualization",
                    assigned_object_type__model="vminterface",
                    assigned_object_id__in=vm_interface_ids,
                )
                .prefetch_related("assigned_object")
                .order_by("address")
            )

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "vm_ips": vm_ips,
                "node_ips": node_ips,
                "vm_ips_count": len(vm_ips),
                "node_ips_count": len(node_ips),
                "total_ips": len(vm_ips) + len(node_ips),
            },
        )
