from __future__ import annotations

from django.core.paginator import Page, Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from netbox import configuration
from utilities.paginator import EnhancedPaginator, get_paginate_count
from utilities.views import ConditionalLoginRequiredMixin
from virtualization.models import Cluster, VirtualDisk, VirtualMachine, VMInterface

from netbox_proxbox.utils import (
    filter_queryset_by_proxmox_vm_type,
    get_fastapi_context_for_request,
    get_proxbox_tagged_object_ids,
    vm_type_select_related_fields,
)


def paginate_object_list(
    request: HttpRequest,
    object_list: object,
    *,
    page_param: str = "page",
) -> tuple[Paginator, Page]:
    """Paginate ``object_list`` the same way NetBox object tables do.

    Uses NetBox's :class:`~utilities.paginator.EnhancedPaginator` and
    :func:`~utilities.paginator.get_paginate_count` so the plugin list pages
    honour the ``per_page`` query parameter, the user's saved page-size
    preference, and the global ``PAGINATE_COUNT``/``MAX_PAGE_SIZE`` settings.

    ``page_param`` lets a single page paginate more than one table
    independently (e.g. the Interfaces and IP Addresses pages, which render a
    VM table and a node table side by side). ``Paginator.get_page`` is used so
    that missing, non-numeric, or out-of-range page numbers degrade gracefully
    instead of raising.
    """
    paginator = EnhancedPaginator(object_list, get_paginate_count(request))
    page = paginator.get_page(request.GET.get(page_param))
    return paginator, page


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
                    "devices_total": 0,
                    "page": None,
                    "paginator": None,
                },
            )

        device_content_type = ContentType.objects.get_for_model(Device)
        tagged_device_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=device_content_type
            ).values_list("object_id", flat=True)
        )
        devices_qs = (
            Device.objects.restrict(request.user, "view")
            .filter(id__in=tagged_device_ids)
            .select_related(
                "device_type__manufacturer", "role", "site", "tenant", "cluster"
            )
            .prefetch_related("interfaces__ip_addresses")
        )
        paginator, page = paginate_object_list(request, devices_qs)

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "devices": page,
                "devices_total": paginator.count,
                "page": page,
                "paginator": paginator,
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
                    "virtual_machines_total": 0,
                    "page": None,
                    "paginator": None,
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        base_qs = (
            VirtualMachine.objects.restrict(request.user, "view")
            .filter(id__in=tagged_vm_ids)
            .select_related(*vm_type_select_related_fields(VirtualMachine))
            .prefetch_related("interfaces__ip_addresses")
        )
        virtual_machines_qs = filter_queryset_by_proxmox_vm_type(
            base_qs,
            VirtualMachine,
            vm_type="qemu",
            vm_type_slug="qemu-virtual-machine",
        )
        paginator, page = paginate_object_list(request, virtual_machines_qs)

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "virtual_machines": page,
                "virtual_machines_total": paginator.count,
                "page": page,
                "paginator": paginator,
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
                    "lxc_containers_total": 0,
                    "page": None,
                    "paginator": None,
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        base_qs = (
            VirtualMachine.objects.restrict(request.user, "view")
            .filter(id__in=tagged_vm_ids)
            .select_related(*vm_type_select_related_fields(VirtualMachine))
            .prefetch_related("interfaces__ip_addresses")
        )
        lxc_containers_qs = filter_queryset_by_proxmox_vm_type(
            base_qs,
            VirtualMachine,
            vm_type="lxc",
            vm_type_slug="lxc-container",
        )
        paginator, page = paginate_object_list(request, lxc_containers_qs)

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "lxc_containers": page,
                "lxc_containers_total": paginator.count,
                "page": page,
                "paginator": paginator,
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
                    "virtual_disks_total": 0,
                    "page": None,
                    "paginator": None,
                },
            )

        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )
        virtual_disks_qs = (
            VirtualDisk.objects.restrict(request.user, "view")
            .filter(virtual_machine_id__in=tagged_vm_ids)
            .select_related("virtual_machine")
            .order_by("virtual_machine__name", "name")
        )
        paginator, page = paginate_object_list(request, virtual_disks_qs)

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "virtual_disks": page,
                "virtual_disks_total": paginator.count,
                "page": page,
                "paginator": paginator,
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
                    "vm_interfaces_total": 0,
                    "node_interfaces_total": 0,
                    "vm_interfaces_paginator": None,
                    "node_interfaces_paginator": None,
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
        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )

        node_interfaces_qs = (
            DCIMInterface.objects.restrict(request.user, "view")
            .filter(device_id__in=tagged_device_ids)
            .select_related("device")
            .prefetch_related("ip_addresses")
            .order_by("device__name", "name")
        )
        vm_interfaces_qs = (
            VMInterface.objects.restrict(request.user, "view")
            .filter(virtual_machine_id__in=tagged_vm_ids)
            .select_related("virtual_machine")
            .prefetch_related("ip_addresses")
            .order_by("virtual_machine__name", "name")
        )

        # Summary counts must reflect every synced interface, not just the
        # interfaces visible on the current page, so they are computed at the
        # database level before pagination slices the querysets.
        node_total = node_interfaces_qs.count()
        vm_total = vm_interfaces_qs.count()
        node_up = node_interfaces_qs.filter(enabled=True).count()
        vm_up = vm_interfaces_qs.filter(enabled=True).count()
        interfaces_up = node_up + vm_up
        interfaces_total = node_total + vm_total
        interfaces_down = interfaces_total - interfaces_up

        vm_paginator, vm_page = paginate_object_list(
            request, vm_interfaces_qs, page_param="vm_page"
        )
        node_paginator, node_page = paginate_object_list(
            request, node_interfaces_qs, page_param="node_page"
        )

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "vm_interfaces": vm_page,
                "node_interfaces": node_page,
                "vm_interfaces_total": vm_total,
                "node_interfaces_total": node_total,
                "vm_interfaces_paginator": vm_paginator,
                "node_interfaces_paginator": node_paginator,
                "interfaces_up": interfaces_up,
                "interfaces_down": interfaces_down,
                "interfaces_total": interfaces_total,
            },
        )


class ClustersView(ConditionalLoginRequiredMixin, View):
    """List NetBox clusters tagged ``proxbox`` (synced Proxmox clusters) for operational review."""

    template = "netbox_proxbox/clusters.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Load tagged clusters and FastAPI URL hints for the clusters template."""
        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_info = get_fastapi_context_for_request(request)

        from django.db.models import Count

        tagged_cluster_ids = get_proxbox_tagged_object_ids(Cluster)
        clusters_qs = (
            Cluster.objects.restrict(request.user, "view")
            .filter(id__in=tagged_cluster_ids)
            .select_related("type", "group", "_site", "tenant")
            .annotate(
                device_count=Count("devices", distinct=True),
                vm_count=Count("virtual_machines", distinct=True),
            )
        )
        paginator, page = paginate_object_list(request, clusters_qs)
        for cluster in page:
            cluster.site_display = cluster._site

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "clusters": page,
                "clusters_total": paginator.count,
                "page": page,
                "paginator": paginator,
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
                    "vm_ips_paginator": None,
                    "node_ips_paginator": None,
                    "total_ips": 0,
                },
            )

        device_content_type = ContentType.objects.get_for_model(Device)
        tagged_device_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=device_content_type
            ).values_list("object_id", flat=True)
        )
        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        tagged_vm_ids = list(
            TaggedItem.objects.filter(
                tag=proxbox_tag, content_type=vm_content_type
            ).values_list("object_id", flat=True)
        )

        node_interface_ids = list(
            DCIMInterface.objects.filter(
                device_id__in=tagged_device_ids
            ).values_list("id", flat=True)
        )
        node_ips_qs = (
            IPAddress.objects.restrict(request.user, "view")
            .filter(
                assigned_object_type__app_label="dcim",
                assigned_object_type__model="interface",
                assigned_object_id__in=node_interface_ids,
            )
            .prefetch_related("assigned_object")
            .order_by("address")
        )

        vm_interface_ids = list(
            VMInterface.objects.filter(
                virtual_machine_id__in=tagged_vm_ids
            ).values_list("id", flat=True)
        )
        vm_ips_qs = (
            IPAddress.objects.restrict(request.user, "view")
            .filter(
                assigned_object_type__app_label="virtualization",
                assigned_object_type__model="vminterface",
                assigned_object_id__in=vm_interface_ids,
            )
            .prefetch_related("assigned_object")
            .order_by("address")
        )

        vm_ips_count = vm_ips_qs.count()
        node_ips_count = node_ips_qs.count()
        vm_paginator, vm_page = paginate_object_list(
            request, vm_ips_qs, page_param="vm_page"
        )
        node_paginator, node_page = paginate_object_list(
            request, node_ips_qs, page_param="node_page"
        )

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "vm_ips": vm_page,
                "node_ips": node_page,
                "vm_ips_count": vm_ips_count,
                "node_ips_count": node_ips_count,
                "vm_ips_paginator": vm_paginator,
                "node_ips_paginator": node_paginator,
                "total_ips": vm_ips_count + node_ips_count,
            },
        )
