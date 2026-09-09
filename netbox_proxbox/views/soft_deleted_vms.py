"""Human-only cleanup views for Proxbox orphan virtual machines."""

from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpRequest
from netbox.object_actions import BulkDelete
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from virtualization.models import VirtualMachine
from virtualization.tables import VirtualMachineTable

from netbox_proxbox.constants import (
    SOFT_DELETE_TAG_SLUG,
    SOFT_DELETE_VM_STATUS,
)
from netbox_proxbox.utils import has_virtual_machine_type_field


def _virtual_machine_table() -> type[VirtualMachineTable]:
    """Return a VM table compatible with NetBox 4.5 and 4.6."""
    if has_virtual_machine_type_field(VirtualMachine):
        return VirtualMachineTable

    class LegacyVirtualMachineTable(VirtualMachineTable):
        """Core VM table without the NetBox 4.6-only type relation."""

        virtual_machine_type = None

        class Meta(VirtualMachineTable.Meta):
            fields = tuple(
                field
                for field in VirtualMachineTable.Meta.fields
                if field != "virtual_machine_type"
            )
            default_columns = tuple(
                field
                for field in VirtualMachineTable.Meta.default_columns
                if field != "virtual_machine_type"
            )

    return LegacyVirtualMachineTable


SOFT_DELETED_VM_TABLE = _virtual_machine_table()


class SoftDeletedVirtualMachineFilterSet:
    """Apply the immutable orphan marker and status safety boundary."""

    def __init__(self, data: object, queryset: QuerySet, *, request: HttpRequest):
        self.data = data
        self.queryset = queryset
        self.request = request

    @property
    def qs(self) -> QuerySet:
        """Return only VMs explicitly marked for human-only cleanup."""
        return self.queryset.filter(
            tags__slug=SOFT_DELETE_TAG_SLUG,
            status=SOFT_DELETE_VM_STATUS,
        ).distinct()


class _SoftDeletedVirtualMachineQuerysetMixin:
    """Keep list and delete operations inside the marker safety boundary."""

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Return only viewable, marked virtual machines."""
        queryset = VirtualMachine.objects.restrict(request.user, "view")
        return SoftDeletedVirtualMachineFilterSet(
            request.GET,
            queryset,
            request=request,
        ).qs


class SoftDeletedVirtualMachinesView(
    _SoftDeletedVirtualMachineQuerysetMixin,
    generic.ObjectListView,
):
    """List marked orphan VMs with a dedicated human purge action."""

    queryset = VirtualMachine.objects.all()
    table = SOFT_DELETED_VM_TABLE
    filterset = SoftDeletedVirtualMachineFilterSet
    template_name = "netbox_proxbox/soft_deleted_virtual_machines.html"
    actions = (BulkDelete,)

    def get_required_permission(self) -> str:
        """Require delete permission before exposing the purge page."""
        return get_permission_for_model(VirtualMachine, "delete")


class SoftDeletedVirtualMachinesBulkDeleteView(
    _SoftDeletedVirtualMachineQuerysetMixin,
    generic.BulkDeleteView,
):
    """Confirm and delete only the selected marked orphan VMs."""

    queryset = VirtualMachine.objects.all()
    filterset = SoftDeletedVirtualMachineFilterSet
    table = SOFT_DELETED_VM_TABLE
    default_return_url = "plugins:netbox_proxbox:soft_deleted_vms"


__all__ = (
    "SoftDeletedVirtualMachineFilterSet",
    "SoftDeletedVirtualMachinesBulkDeleteView",
    "SoftDeletedVirtualMachinesView",
)
