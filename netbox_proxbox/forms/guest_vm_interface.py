"""Forms for guest OS VM interface inventory."""

from django import forms

from ipam.models import IPAddress
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from virtualization.models import VirtualMachine, VMInterface

from netbox_proxbox.models import GuestVMInterface, GuestVMInterfaceAddress


class GuestVMInterfaceForm(NetBoxModelForm):
    """Create/edit form for guest OS VM interfaces."""

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
    )
    vm_interface = DynamicModelChoiceField(
        queryset=VMInterface.objects.all(),
        required=False,
    )
    comments = CommentField()

    class Meta:
        model = GuestVMInterface
        fields = (
            "virtual_machine",
            "vm_interface",
            "name",
            "mac_address",
            "enabled",
            "mtu",
            "tags",
            "comments",
        )


class GuestVMInterfaceFilterForm(NetBoxModelFilterSetForm):
    """Filter form for guest OS VM interface list views."""

    model = GuestVMInterface

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )
    vm_interface = DynamicModelChoiceField(
        queryset=VMInterface.objects.all(),
        required=False,
    )
    name = forms.CharField(required=False)
    mac_address = forms.CharField(required=False)
    enabled = forms.BooleanField(required=False)


class GuestVMInterfaceAddressForm(NetBoxModelForm):
    """Create/edit form for guest interface address links."""

    guest_interface = DynamicModelChoiceField(
        queryset=GuestVMInterface.objects.all(),
        required=True,
    )
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=True,
        help_text="Select an existing core NetBox IP address; do not duplicate IP rows.",
    )
    comments = CommentField()

    class Meta:
        model = GuestVMInterfaceAddress
        fields = (
            "guest_interface",
            "ip_address",
            "tags",
            "comments",
        )


class GuestVMInterfaceAddressFilterForm(NetBoxModelFilterSetForm):
    """Filter form for guest interface address list views."""

    model = GuestVMInterfaceAddress

    guest_interface = DynamicModelChoiceField(
        queryset=GuestVMInterface.objects.all(),
        required=False,
    )
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
    )
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )
    vm_interface = DynamicModelChoiceField(
        queryset=VMInterface.objects.all(),
        required=False,
    )
