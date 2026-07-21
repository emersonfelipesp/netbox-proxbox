"""Typed Proxbox sync-state sidecars for legacy custom-field payloads."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


def _core_url(obj: object | None) -> str:
    """Return a linked core object's URL when it provides one."""
    if obj is None:
        return ""
    get_absolute_url = getattr(obj, "get_absolute_url", None)
    if not callable(get_absolute_url):
        return ""
    try:
        return str(get_absolute_url())
    except Exception:
        return ""


class ProxboxSyncStateBase(NetBoxModel):
    """Shared sync state copied from the legacy Proxbox custom fields."""

    proxmox_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "Timestamp mirrored from the legacy proxmox_last_updated custom field."
        ),
    )
    last_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("proxbox-api run identifier mirrored from proxbox_last_run_id."),
    )

    class Meta:
        abstract = True


class ProxboxVirtualMachineSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox virtual machine."""

    virtual_machine = models.OneToOneField(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="virtual_machine_sync_states",
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="virtual_machine_sync_states",
    )
    proxmox_node_name = models.CharField(max_length=255, blank=True)
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="virtual_machine_sync_states",
    )
    proxmox_cluster_name = models.CharField(max_length=255, blank=True)
    proxmox_endpoint_raw_id = models.IntegerField(null=True, blank=True)

    proxmox_vm_id = models.IntegerField(null=True, blank=True)
    proxmox_vm_type = models.CharField(max_length=64, blank=True)
    # Name this VM had in Proxmox as of the last successful sync.
    #
    # Without it, a rename cannot be attributed: "NetBox name != incoming
    # Proxmox name" looks identical whether an operator renamed the VM inside
    # NetBox or somebody renamed it in Proxmox. proxbox-api's collision resolver
    # assumed the former and pushed the stale NetBox name back onto the payload,
    # so a Proxmox-side rename was silently discarded
    # (netbox-proxbox issue #617).
    #
    # With it, the two cases separate cleanly:
    #   NetBox name != this value          -> a human edited it in NetBox -> keep
    #   NetBox name == this value != new   -> renamed in Proxmox          -> update
    #
    # Blank means "not yet recorded" (every row on first upgrade), and callers
    # must fall back to the previous behaviour so nothing regresses mid-rollout.
    proxmox_vm_name = models.CharField(max_length=255, blank=True)
    proxmox_start_at_boot = models.BooleanField(null=True, blank=True)
    proxmox_unprivileged_container = models.BooleanField(null=True, blank=True)
    proxmox_qemu_agent = models.BooleanField(null=True, blank=True)
    proxmox_search_domain = models.CharField(max_length=255, blank=True)
    proxmox_link = models.URLField(max_length=500, blank=True)
    proxmox_status = models.CharField(max_length=64, blank=True)
    proxmox_uptime = models.IntegerField(null=True, blank=True)
    proxmox_tags = models.TextField(blank=True)
    proxmox_os = models.CharField(max_length=255, blank=True)
    proxmox_storage = models.CharField(max_length=255, blank=True)
    proxmox_disk = models.CharField(max_length=255, blank=True)
    proxmox_interfaces = models.TextField(blank=True)
    proxmox_vmid = models.CharField(max_length=64, blank=True)
    proxmox_notes = models.TextField(blank=True)
    proxmox_tcp_states = models.TextField(blank=True)
    proxmox_cpu_type = models.CharField(max_length=255, blank=True)
    proxmox_storage_ids = models.TextField(blank=True)
    proxmox_storage_names = models.TextField(blank=True)
    proxmox_device_names = models.TextField(blank=True)
    proxmox_migration_duration = models.IntegerField(null=True, blank=True)
    proxmox_migration_type = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("virtual_machine",)
        verbose_name = _("Proxbox virtual machine sync state")
        verbose_name_plural = _("Proxbox virtual machine sync states")

    def __str__(self) -> str:
        return f"{self.virtual_machine} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.virtual_machine)


class ProxboxDeviceSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox device."""

    device = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_sync_states",
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_sync_states",
    )
    proxmox_node_name = models.CharField(max_length=255, blank=True)
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_sync_states",
    )
    proxmox_cluster_name = models.CharField(max_length=255, blank=True)

    proxmox_link = models.URLField(max_length=500, blank=True)
    proxmox_tags = models.TextField(blank=True)
    proxmox_os = models.CharField(max_length=255, blank=True)
    proxmox_storage = models.CharField(max_length=255, blank=True)
    proxmox_disk = models.CharField(max_length=255, blank=True)
    proxmox_interfaces = models.TextField(blank=True)
    proxmox_vmid = models.CharField(max_length=64, blank=True)
    proxmox_notes = models.TextField(blank=True)
    proxmox_tcp_states = models.TextField(blank=True)
    proxmox_cpu_type = models.CharField(max_length=255, blank=True)
    proxmox_storage_ids = models.TextField(blank=True)
    proxmox_storage_names = models.TextField(blank=True)
    proxmox_device_names = models.TextField(blank=True)
    hardware_chassis_serial = models.CharField(max_length=255, blank=True)
    hardware_chassis_manufacturer = models.CharField(max_length=255, blank=True)
    hardware_chassis_product = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("device",)
        verbose_name = _("Proxbox device sync state")
        verbose_name_plural = _("Proxbox device sync states")

    def __str__(self) -> str:
        return f"{self.device} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.device)

    def clean(self) -> None:
        super().clean()
        if self.proxmox_node_id is None:
            return
        if getattr(self.proxmox_node, "netbox_device_id", None) != self.device_id:
            raise ValidationError(
                {
                    "proxmox_node": _(
                        "Proxmox node must be linked to the sync-state device."
                    )
                }
            )


class ProxboxClusterSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox cluster."""

    cluster = models.OneToOneField(
        to="virtualization.Cluster",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cluster_sync_states",
    )
    proxmox_cluster_name = models.CharField(max_length=255, blank=True)
    proxmox_cluster_status = models.CharField(max_length=64, blank=True)
    proxmox_cluster_raw_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("cluster",)
        verbose_name = _("Proxbox cluster sync state")
        verbose_name_plural = _("Proxbox cluster sync states")

    def __str__(self) -> str:
        return f"{self.cluster} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.cluster)

    def clean(self) -> None:
        super().clean()
        if self.proxmox_cluster_id is None:
            return
        if getattr(self.proxmox_cluster, "netbox_cluster_id", None) != self.cluster_id:
            raise ValidationError(
                {
                    "proxmox_cluster": _(
                        "Proxmox cluster must be linked to the sync-state cluster."
                    )
                }
            )


class ProxboxIPAddressSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox IP address."""

    ip_address = models.OneToOneField(
        to="ipam.IPAddress",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxmox_interface = models.CharField(max_length=255, blank=True)
    proxmox_mac = models.CharField(max_length=64, blank=True)
    proxmox_ip_addresses = models.TextField(blank=True)

    class Meta:
        ordering = ("ip_address",)
        verbose_name = _("Proxbox IP address sync state")
        verbose_name_plural = _("Proxbox IP address sync states")

    def __str__(self) -> str:
        return f"{self.ip_address} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.ip_address)


class ProxboxInterfaceSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox device interface."""

    interface = models.OneToOneField(
        to="dcim.Interface",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    nic_speed_gbps = models.IntegerField(null=True, blank=True)
    nic_duplex = models.CharField(max_length=64, blank=True)
    nic_link = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ("interface",)
        verbose_name = _("Proxbox interface sync state")
        verbose_name_plural = _("Proxbox interface sync states")

    def __str__(self) -> str:
        return f"{self.interface} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.interface)


class ProxboxVLANSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox VLAN."""

    vlan = models.OneToOneField(
        to="ipam.VLAN",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxmox_vlan_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("vlan",)
        verbose_name = _("Proxbox VLAN sync state")
        verbose_name_plural = _("Proxbox VLAN sync states")

    def __str__(self) -> str:
        return f"{self.vlan} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.vlan)


class ProxboxClusterGroupSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox cluster group."""

    cluster_group = models.OneToOneField(
        to="virtualization.ClusterGroup",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxmox_cluster_name = models.CharField(max_length=255, blank=True)
    proxmox_cluster_status = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("cluster_group",)
        verbose_name = _("Proxbox cluster group sync state")
        verbose_name_plural = _("Proxbox cluster group sync states")

    def __str__(self) -> str:
        return f"{self.cluster_group} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.cluster_group)


class ProxboxVirtualDiskSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox virtual disk."""

    virtual_disk = models.OneToOneField(
        to="virtualization.VirtualDisk",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxbox_storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="virtual_disk_sync_states",
    )
    proxbox_storage_raw_id = models.BigIntegerField(null=True, blank=True)
    proxbox_storage_raw_value = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("virtual_disk",)
        verbose_name = _("Proxbox virtual disk sync state")
        verbose_name_plural = _("Proxbox virtual disk sync states")

    def __str__(self) -> str:
        return f"{self.virtual_disk} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.virtual_disk)


class ProxboxVMInterfaceSyncState(ProxboxSyncStateBase):
    """Typed Proxmox custom-field payload for a NetBox VM interface."""

    vm_interface = models.OneToOneField(
        to="virtualization.VMInterface",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )
    proxbox_bridge = models.ForeignKey(
        to="dcim.Interface",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proxbox_vm_interface_sync_states",
    )
    proxbox_bridge_raw_id = models.BigIntegerField(null=True, blank=True)
    proxbox_bridge_raw_value = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("vm_interface",)
        verbose_name = _("Proxbox VM interface sync state")
        verbose_name_plural = _("Proxbox VM interface sync states")

    def __str__(self) -> str:
        return f"{self.vm_interface} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.vm_interface)


class ProxboxDeviceRoleSyncState(ProxboxSyncStateBase):
    """Sync-state marker for a NetBox device role touched by Proxbox."""

    device_role = models.OneToOneField(
        to="dcim.DeviceRole",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )

    class Meta:
        ordering = ("device_role",)
        verbose_name = _("Proxbox device role sync state")
        verbose_name_plural = _("Proxbox device role sync states")

    def __str__(self) -> str:
        return f"{self.device_role} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.device_role)


class ProxboxDeviceTypeSyncState(ProxboxSyncStateBase):
    """Sync-state marker for a NetBox device type touched by Proxbox."""

    device_type = models.OneToOneField(
        to="dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )

    class Meta:
        ordering = ("device_type",)
        verbose_name = _("Proxbox device type sync state")
        verbose_name_plural = _("Proxbox device type sync states")

    def __str__(self) -> str:
        return f"{self.device_type} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.device_type)


class ProxboxManufacturerSyncState(ProxboxSyncStateBase):
    """Sync-state marker for a NetBox manufacturer touched by Proxbox."""

    manufacturer = models.OneToOneField(
        to="dcim.Manufacturer",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )

    class Meta:
        ordering = ("manufacturer",)
        verbose_name = _("Proxbox manufacturer sync state")
        verbose_name_plural = _("Proxbox manufacturer sync states")

    def __str__(self) -> str:
        return f"{self.manufacturer} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.manufacturer)


class ProxboxSiteSyncState(ProxboxSyncStateBase):
    """Sync-state marker for a NetBox site touched by Proxbox."""

    site = models.OneToOneField(
        to="dcim.Site",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )

    class Meta:
        ordering = ("site",)
        verbose_name = _("Proxbox site sync state")
        verbose_name_plural = _("Proxbox site sync states")

    def __str__(self) -> str:
        return f"{self.site} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.site)


class ProxboxClusterTypeSyncState(ProxboxSyncStateBase):
    """Sync-state marker for a NetBox cluster type touched by Proxbox."""

    cluster_type = models.OneToOneField(
        to="virtualization.ClusterType",
        on_delete=models.CASCADE,
        related_name="proxbox_sync_state",
    )

    class Meta:
        ordering = ("cluster_type",)
        verbose_name = _("Proxbox cluster type sync state")
        verbose_name_plural = _("Proxbox cluster type sync states")

    def __str__(self) -> str:
        return f"{self.cluster_type} Proxbox sync state"

    def get_absolute_url(self) -> str:
        return _core_url(self.cluster_type)
