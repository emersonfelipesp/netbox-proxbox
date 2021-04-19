
# Provides standard field types like 'CharField' and 'ForeignKey'
from django.db import models

from django.urls import reverse

# Model class 'ChangeLoggedModel' defined by Netbox
from extras.models import ChangeLoggedModel

# Class defined by Netbox to handle IPv4/IPv6 address
#from ipam.fields import IPAddressField

# Class defined by Netbox to define (choice) the VM operational status
from virtualization.models import VirtualMachineStatusChoices

# 'RestrictedQuerySet' will make it possible to filter out objects 
# for which user doest nothave specific rights
from utilities.querysets import RestrictedQuerySet

# model class that subclasses 'ChangeLoggedModel'
class VmResources(ChangeLoggedModel):
    cluster = models.ForeignKey(      # Field 'cluster' links to Netbox's 'virtualization.Cluster' model
        to="virtualization.Cluster",  # and is set to 'ForeignKey' because of it.
        on_delete=models.SET_NULL,    # If Netbox linked object is deleted, set the field to NULL
        blank=True, # Makes field optional
        null=True   # Allows corresponding database column to be NULL (contain no value)
    )
    node = models.CharField(
        max_length=64,
        blank=True
    )
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.PROTECT     # linked virtual_machine cannot be deleted as long as this object exists
    )
    status = models.CharField(
        max_length=50,
        choices=VirtualMachineStatusChoices,
        default=VirtualMachineStatusChoices.STATUS_ACTIVE,
        verbose_name='Status'
    )    
    proxmox_vm_id = models.PositiveIntegerField()
    vcpus = models.PositiveIntegerField()
    memory = models.PositiveIntegerField()
    disk = models.PositiveIntegerField()
    type = models.CharField(
        max_length=64,
        blank=True
    )
    # Retrieve and filter 'VmResources' records
    objects = RestrictedQuerySet.as_manager()

    def get_absolute_url(self):
        """Provide absolute URL to a Bgp Peering object."""

        # 'reverse' generate correct URL for given class record based on the provided pk.
        return reverse("plugins:netbox_proxbox:proxbox", kwargs={"pk": self.pk})
'''
Model example

class BgpPeering(ChangeLoggedModel):
    site = models.ForeignKey(
        to="dcim.Site", on_delete=models.SET_NULL, blank=True, null=True
    )
    device = models.ForeignKey(to="dcim.Device", on_delete=models.PROTECT)
    local_ip = models.ForeignKey(to="ipam.IPAddress", on_delete=models.PROTECT)
    local_as = ASNField(help_text="32-bit ASN used locally")
    remote_ip = IPAddressField(help_text="IPv4 or IPv6 address (with mask)")
    remote_as = ASNField(help_text="32-bit ASN used by peer")
    peer_name = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=200, blank=True)
'''