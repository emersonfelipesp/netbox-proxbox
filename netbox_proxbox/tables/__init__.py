"""Define NetBox table classes for endpoint list views."""

# Django Imports
import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext as _

# NetBox Imports
from netbox.tables import ChoiceFieldColumn, NetBoxTable
from netbox.tables.columns import BooleanColumn

# Proxbox Imports
from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    NodeSSHCredential,
    ProxmoxEndpoint,
)
from netbox_proxbox.tables.backup_routine import BackupRoutineTable
from netbox_proxbox.tables.firewall import (
    ProxmoxFirewallAliasTable,
    ProxmoxFirewallIPSetEntryTable,
    ProxmoxFirewallIPSetTable,
    ProxmoxFirewallOptionsTable,
    ProxmoxFirewallRuleTable,
    ProxmoxFirewallSecurityGroupTable,
)
from netbox_proxbox.tables.sdn import (
    ProxmoxSdnBindingTable,
    ProxmoxSdnControllerTable,
    ProxmoxSdnFabricTable,
    ProxmoxSdnRouteMapTable,
    ProxmoxSdnPrefixListTable,
    ProxmoxSdnSubnetTable,
    ProxmoxSdnVNetTable,
    ProxmoxSdnZoneTable,
)
from netbox_proxbox.tables.datacenter import ProxmoxDatacenterCpuModelTable
from netbox_proxbox.tables.cloud_image_template import CloudImageTemplateTable
from netbox_proxbox.tables.cluster import ProxmoxClusterTable, ProxmoxNodeTable
from netbox_proxbox.tables.deletion_requests import DeletionRequestTable
from netbox_proxbox.tables.guest_vm_interface import (
    GuestVMInterfaceAddressTable,
    GuestVMInterfaceTable,
)
from netbox_proxbox.tables.replication import ReplicationTable
from netbox_proxbox.tables.storage import ProxmoxStorageTable
from netbox_proxbox.tables.sync_state import (
    ProxboxClusterGroupSyncStateTable,
    ProxboxClusterSyncStateTable,
    ProxboxClusterTypeSyncStateTable,
    ProxboxDeviceRoleSyncStateTable,
    ProxboxDeviceSyncStateTable,
    ProxboxDeviceTypeSyncStateTable,
    ProxboxIPAddressSyncStateTable,
    ProxboxInterfaceSyncStateTable,
    ProxboxManufacturerSyncStateTable,
    ProxboxSiteSyncStateTable,
    ProxboxVirtualDiskSyncStateTable,
    ProxboxVirtualMachineSyncStateTable,
    ProxboxVLANSyncStateTable,
    ProxboxVMInterfaceSyncStateTable,
)
from netbox_proxbox.tables.vm_backup import VMBackupTable
from netbox_proxbox.tables.vm_cloudinit import ProxmoxVMCloudInitTable
from netbox_proxbox.tables.vm_snapshot import VMSnapshotTable
from netbox_proxbox.tables.vm_task_history import VMTaskHistoryTable
from netbox_proxbox.tables.pdm_remote import PDMRemoteTable
from netbox_proxbox.tables.vm_template import ProxmoxVMTemplateTable

STATUS_BADGE_TEMPLATE = """
<span class="badge text-bg-grey"
      data-service-status-url="{% url 'plugins:netbox_proxbox:keepalive_status' '{{ service }}' record.pk %}">
    <span class="spinner-border spinner-border-sm" role="status"></span>
</span>
"""

PROXMOX_STATUS_BADGE_TEMPLATE = """
{% if not record.enabled %}
<span class="badge text-bg-secondary"
      title="Proxmox endpoint '{{ record }}' is disabled."
      data-bs-toggle="tooltip"
      data-bs-title="Proxmox endpoint '{{ record }}' is disabled.">
    Disabled
</span>
{% else %}
<span class="badge text-bg-grey"
      data-service-status-url="{% url 'plugins:netbox_proxbox:keepalive_status' 'proxmox' record.pk %}">
    <span class="spinner-border spinner-border-sm" role="status"></span>
</span>
{% endif %}
"""


class ProxmoxEndpointTable(NetBoxTable):
    """django-tables2 layout for Proxmox endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    environment = ChoiceFieldColumn()
    ssh_credential_source = ChoiceFieldColumn()
    verify_ssl = BooleanColumn()
    enabled = BooleanColumn()
    status = tables.TemplateColumn(
        template_code=PROXMOX_STATUS_BADGE_TEMPLATE,
        verbose_name=_("Status"),
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "domain",
            "ip_address",
            "port",
            "mode",
            "environment",
            "version",
            "repoid",
            "username",
            "token_name",
            "ssh_credential_source",
            "verify_ssl",
            "enabled",
            "timeout",
            "max_retries",
            "retry_backoff",
            "site",
            "tenant",
            "status",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "domain",
            "ip_address",
            "port",
            "mode",
            "environment",
            "version",
            "status",
            "verify_ssl",
            "enabled",
        )


class NetBoxEndpointTable(NetBoxTable):
    """django-tables2 layout for remote NetBox API endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    enabled = BooleanColumn()
    token = tables.Column(linkify=True)
    status = tables.TemplateColumn(
        template_code=STATUS_BADGE_TEMPLATE.replace("{{ service }}", "netbox"),
        verbose_name=_("Status"),
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = NetBoxEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "ip_address",
            "port",
            "verify_ssl",
            "enabled",
            "token",
            "status",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "ip_address",
            "port",
            "status",
            "verify_ssl",
            "enabled",
            "token",
        )


class FastAPIEndpointTable(NetBoxTable):
    """django-tables2 layout for ProxBox FastAPI backend endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    use_https = BooleanColumn()
    verify_ssl = BooleanColumn()
    enabled = BooleanColumn()
    status = tables.TemplateColumn(
        template_code=STATUS_BADGE_TEMPLATE.replace("{{ service }}", "fastapi"),
        verbose_name=_("Status"),
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = FastAPIEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "domain",
            "ip_address",
            "port",
            "use_https",
            "verify_ssl",
            "enabled",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "token",
            "status",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "domain",
            "ip_address",
            "port",
            "status",
            "use_https",
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
        )


class NodeSSHCredentialTable(NetBoxTable):
    """django-tables2 layout for hardware-discovery SSH credentials."""

    node = tables.Column(linkify=True)
    auth_method = ChoiceFieldColumn()
    sudo_required = BooleanColumn()
    has_password = BooleanColumn(verbose_name=_("Password stored"))
    has_private_key = BooleanColumn(verbose_name=_("Private key stored"))

    class Meta(NetBoxTable.Meta):
        model = NodeSSHCredential
        fields = (
            "pk",
            "id",
            "node",
            "username",
            "port",
            "auth_method",
            "known_host_fingerprint",
            "sudo_required",
            "has_password",
            "has_private_key",
            "actions",
        )
        default_columns = (
            "pk",
            "node",
            "username",
            "port",
            "auth_method",
            "sudo_required",
            "has_password",
            "has_private_key",
        )
