"""CRUD views for guest OS VM interface inventory."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import (
    GuestVMInterfaceAddressFilterSet,
    GuestVMInterfaceFilterSet,
)
from netbox_proxbox.forms import (
    GuestVMInterfaceAddressFilterForm,
    GuestVMInterfaceAddressForm,
    GuestVMInterfaceFilterForm,
    GuestVMInterfaceForm,
)
from netbox_proxbox.models import GuestVMInterface, GuestVMInterfaceAddress
from netbox_proxbox.tables import (
    GuestVMInterfaceAddressTable,
    GuestVMInterfaceTable,
)

__all__ = (
    "GuestVMInterfaceView",
    "GuestVMInterfaceListView",
    "GuestVMInterfaceEditView",
    "GuestVMInterfaceDeleteView",
    "GuestVMInterfaceBulkDeleteView",
    "GuestVMInterfaceAddressView",
    "GuestVMInterfaceAddressListView",
    "GuestVMInterfaceAddressEditView",
    "GuestVMInterfaceAddressDeleteView",
    "GuestVMInterfaceAddressBulkDeleteView",
)


@register_model_view(GuestVMInterface, "list", path="", detail=False)
class GuestVMInterfaceListView(generic.ObjectListView):
    """Global list of guest OS VM interfaces."""

    queryset = GuestVMInterface.objects.select_related(
        "virtual_machine",
        "vm_interface",
    )
    table = GuestVMInterfaceTable
    filterset = GuestVMInterfaceFilterSet
    filterset_form = GuestVMInterfaceFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(GuestVMInterface)
class GuestVMInterfaceView(generic.ObjectView):
    """Detail view for one guest OS VM interface."""

    queryset = GuestVMInterface.objects.select_related(
        "virtual_machine",
        "vm_interface",
    ).prefetch_related("addresses", "addresses__ip_address")


@register_model_view(GuestVMInterface, "add", detail=False)
@register_model_view(GuestVMInterface, "edit")
class GuestVMInterfaceEditView(generic.ObjectEditView):
    """Create or edit a guest OS VM interface row."""

    queryset = GuestVMInterface.objects.all()
    form = GuestVMInterfaceForm
    default_return_url = "plugins:netbox_proxbox:guestvminterface_list"


@register_model_view(GuestVMInterface, "delete")
class GuestVMInterfaceDeleteView(generic.ObjectDeleteView):
    """Delete a single guest OS VM interface row."""

    queryset = GuestVMInterface.objects.all()
    default_return_url = "plugins:netbox_proxbox:guestvminterface_list"


@register_model_view(GuestVMInterface, "bulk_delete", detail=False)
class GuestVMInterfaceBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete guest OS VM interfaces from the list page."""

    queryset = GuestVMInterface.objects.all()
    filterset = GuestVMInterfaceFilterSet
    table = GuestVMInterfaceTable
    default_return_url = "plugins:netbox_proxbox:guestvminterface_list"


@register_model_view(GuestVMInterfaceAddress, "list", path="", detail=False)
class GuestVMInterfaceAddressListView(generic.ObjectListView):
    """Global list of guest interface address links."""

    queryset = GuestVMInterfaceAddress.objects.select_related(
        "guest_interface",
        "guest_interface__virtual_machine",
        "guest_interface__vm_interface",
        "ip_address",
    )
    table = GuestVMInterfaceAddressTable
    filterset = GuestVMInterfaceAddressFilterSet
    filterset_form = GuestVMInterfaceAddressFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(GuestVMInterfaceAddress)
class GuestVMInterfaceAddressView(generic.ObjectView):
    """Detail view for one guest interface address link."""

    queryset = GuestVMInterfaceAddress.objects.select_related(
        "guest_interface",
        "guest_interface__virtual_machine",
        "guest_interface__vm_interface",
        "ip_address",
    )


@register_model_view(GuestVMInterfaceAddress, "add", detail=False)
@register_model_view(GuestVMInterfaceAddress, "edit")
class GuestVMInterfaceAddressEditView(generic.ObjectEditView):
    """Create or edit a guest interface address link."""

    queryset = GuestVMInterfaceAddress.objects.all()
    form = GuestVMInterfaceAddressForm
    default_return_url = "plugins:netbox_proxbox:guestvminterfaceaddress_list"


@register_model_view(GuestVMInterfaceAddress, "delete")
class GuestVMInterfaceAddressDeleteView(generic.ObjectDeleteView):
    """Delete a single guest interface address link."""

    queryset = GuestVMInterfaceAddress.objects.all()
    default_return_url = "plugins:netbox_proxbox:guestvminterfaceaddress_list"


@register_model_view(GuestVMInterfaceAddress, "bulk_delete", detail=False)
class GuestVMInterfaceAddressBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete guest interface address links from the list page."""

    queryset = GuestVMInterfaceAddress.objects.all()
    filterset = GuestVMInterfaceAddressFilterSet
    table = GuestVMInterfaceAddressTable
    default_return_url = "plugins:netbox_proxbox:guestvminterfaceaddress_list"
