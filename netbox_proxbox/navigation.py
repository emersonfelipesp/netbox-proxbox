"""Define the NetBox plugin navigation menu and shortcut buttons."""

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

fullupdate_item = PluginMenuItem(
    link="plugins:netbox_proxbox:home",
    link_text="Homepage",
)

dashboard_item = PluginMenuItem(
    link="plugins:netbox_proxbox:dashboard",
    link_text="Dashboard",
)

clusters_item = PluginMenuItem(
    link="plugins:netbox_proxbox:clusters",
    link_text="Clusters",
)

nodes_item = PluginMenuItem(
    link="plugins:netbox_proxbox:nodes",
    link_text="Nodes (Devices)",
)

virtual_machines_item = PluginMenuItem(
    link="plugins:netbox_proxbox:virtual_machines",
    link_text="Virtual Machines",
)

vm_templates_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxvmtemplate_list",
    link_text="VM Templates",
)

lxc_containers_item = PluginMenuItem(
    link="plugins:netbox_proxbox:lxc_containers",
    link_text="LXC Containers",
)

interfaces_item = PluginMenuItem(
    link="plugins:netbox_proxbox:interfaces",
    link_text="Interfaces",
)

guest_vm_interfaces_item = PluginMenuItem(
    link="plugins:netbox_proxbox:guestvminterface_list",
    link_text="Guest VM Interfaces",
)

ip_addresses_item = PluginMenuItem(
    link="plugins:netbox_proxbox:ip_addresses",
    link_text="IP Addresses",
)

storage_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxstorage_list",
    link_text="Storage",
)

virtual_disks_item = PluginMenuItem(
    link="plugins:netbox_proxbox:virtual_disks",
    link_text="Virtual Disks",
)

schedule_sync_item = PluginMenuItem(
    link="plugins:netbox_proxbox:schedule_sync",
    link_text="Schedule Sync",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:schedule_sync",
            "Schedule",
            "mdi mdi-clock-outline",
        ),
    ),
)

sync_jobs_item = PluginMenuItem(
    link="core:job_list",
    link_text="Sync Jobs",
)

backend_logs_item = PluginMenuItem(
    link="plugins:netbox_proxbox:backend_logs",
    link_text="Backend Logs",
)

settings_item = PluginMenuItem(
    link="plugins:netbox_proxbox:settings",
    link_text="Settings",
)

backups_item = PluginMenuItem(
    link="plugins:netbox_proxbox:vmbackup_list",
    link_text="Backups",
)

backup_routines_item = PluginMenuItem(
    link="plugins:netbox_proxbox:backuproutine_list",
    link_text="Backup Routines",
)

snapshots_item = PluginMenuItem(
    link="plugins:netbox_proxbox:vmsnapshot_list",
    link_text="Snapshots",
)

replications_item = PluginMenuItem(
    link="plugins:netbox_proxbox:replication_list",
    link_text="Replications",
)

ha_item = PluginMenuItem(
    link="plugins:netbox_proxbox:ha",
    link_text="HA Status",
)

task_history_item = PluginMenuItem(
    link="plugins:netbox_proxbox:vmtaskhistory_list",
    link_text="Task History",
)

vm_cloudinit_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxvmcloudinit_list",
    link_text="VM Cloud-init",
)

cloud_images_item = PluginMenuItem(
    link="plugins:netbox_proxbox:cloudimagetemplate_list",
    link_text="Cloud Image Build Pipeline",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:cloudimagetemplate_add",
            "Add Cloud Image",
            "mdi mdi-plus",
        ),
    ),
)

contributing_item = PluginMenuItem(
    link="plugins:netbox_proxbox:contributing",
    link_text="Contributing!",
)

# Endpoints navigation entries (Proxmox / NetBox / FastAPI targets).
proxmox_endpoints_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxendpoint_list",
    link_text="Proxmox API",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxendpoint_add",
            "Add Proxmox Endpoint",
            "mdi mdi-plus",
        ),
    ),
)

netbox_endpoints_item = PluginMenuItem(
    link="plugins:netbox_proxbox:netboxendpoint_list",
    link_text="NetBox API",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:netboxendpoint_add",
            "Add NetBox Endpoint",
            "mdi mdi-plus",
        ),
    ),
)

fastapi_endpoints_item = PluginMenuItem(
    link="plugins:netbox_proxbox:fastapiendpoint_list",
    link_text="ProxBox API (FastAPI)",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:fastapiendpoint_add",
            "Add Proxbox API Endpoint",
            "mdi mdi-plus",
        ),
    ),
)

ssh_credentials_item = PluginMenuItem(
    link="plugins:netbox_proxbox:nodesshcredential_list",
    link_text="SSH Credentials",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:nodesshcredential_add",
            "Add SSH Credential",
            "mdi mdi-plus",
        ),
    ),
)

firewall_rules_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewallrule_list",
    link_text="Firewall Rules",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxfirewallrule_add",
            "Add Rule",
            "mdi mdi-plus",
        ),
    ),
)

firewall_security_groups_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list",
    link_text="Security Groups",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_add",
            "Add Security Group",
            "mdi mdi-plus",
        ),
    ),
)

firewall_ipsets_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewallipset_list",
    link_text="IP Sets",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxfirewallipset_add",
            "Add IP Set",
            "mdi mdi-plus",
        ),
    ),
)

firewall_aliases_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewallalias_list",
    link_text="Aliases",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxfirewallalias_add",
            "Add Alias",
            "mdi mdi-plus",
        ),
    ),
)

firewall_ipset_entries_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewallipsetentry_list",
    link_text="IP Set Entries",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxfirewallipsetentry_add",
            "Add IP Set Entry",
            "mdi mdi-plus",
        ),
    ),
)

firewall_options_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxfirewalloptions_list",
    link_text="Firewall Options",
)

sdn_fabrics_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnfabric_list",
    link_text="Fabrics",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnfabric_add",
            "Add Fabric",
            "mdi mdi-plus",
        ),
    ),
)

sdn_controllers_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdncontroller_list",
    link_text="Controllers",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdncontroller_add",
            "Add Controller",
            "mdi mdi-plus",
        ),
    ),
)

sdn_zones_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnzone_list",
    link_text="Zones",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnzone_add",
            "Add Zone",
            "mdi mdi-plus",
        ),
    ),
)

sdn_vnets_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnvnet_list",
    link_text="VNets",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnvnet_add",
            "Add VNet",
            "mdi mdi-plus",
        ),
    ),
)

sdn_subnets_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnsubnet_list",
    link_text="Subnets",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnsubnet_add",
            "Add Subnet",
            "mdi mdi-plus",
        ),
    ),
)

sdn_bindings_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnbinding_list",
    link_text="Bindings",
)

sdn_route_maps_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnroutemap_list",
    link_text="Route Maps",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnroutemap_add",
            "Add Route Map",
            "mdi mdi-plus",
        ),
    ),
)

sdn_prefix_lists_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxsdnprefixlist_list",
    link_text="Prefix Lists",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxsdnprefixlist_add",
            "Add Prefix List",
            "mdi mdi-plus",
        ),
    ),
)

datacenter_cpu_models_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxdatacentercpumodel_list",
    link_text="CPU Models",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxdatacentercpumodel_add",
            "Add CPU Model",
            "mdi mdi-plus",
        ),
    ),
)

metrics_influxdb_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxmetricsinfluxdb_list",
    link_text="InfluxDB Metrics",
    buttons=(
        PluginMenuButton(
            "plugins:netbox_proxbox:proxmoxmetricsinfluxdb_add",
            "Add Metrics Endpoint",
            "mdi mdi-plus",
        ),
    ),
)

community_item = PluginMenuItem(
    link="plugins:netbox_proxbox:community",
    link_text="Community",
    buttons=[
        PluginMenuButton(
            "plugins:netbox_proxbox:discussions",
            "GitHub Discussions",
            "mdi mdi-github",
        ),
    ],
)


menu = PluginMenu(
    label="Proxbox",
    groups=(
        (
            "Overview",
            (
                fullupdate_item,
                dashboard_item,
            ),
        ),
        (
            "Infrastructure",
            (
                clusters_item,
                nodes_item,
                storage_item,
                ha_item,
                datacenter_cpu_models_item,
                metrics_influxdb_item,
            ),
        ),
        (
            "Virtualization",
            (
                virtual_machines_item,
                vm_templates_item,
                lxc_containers_item,
                virtual_disks_item,
                interfaces_item,
                guest_vm_interfaces_item,
                ip_addresses_item,
                vm_cloudinit_item,
                cloud_images_item,
            ),
        ),
        (
            "Security",
            (
                firewall_rules_item,
                firewall_security_groups_item,
                firewall_ipsets_item,
                firewall_ipset_entries_item,
                firewall_aliases_item,
                firewall_options_item,
            ),
        ),
        (
            "SDN",
            (
                sdn_fabrics_item,
                sdn_controllers_item,
                sdn_zones_item,
                sdn_vnets_item,
                sdn_subnets_item,
                sdn_bindings_item,
                sdn_route_maps_item,
                sdn_prefix_lists_item,
            ),
        ),
        (
            "Data Protection",
            (
                backups_item,
                backup_routines_item,
                snapshots_item,
                replications_item,
            ),
        ),
        (
            "Sync & Operations",
            (
                schedule_sync_item,
                sync_jobs_item,
                task_history_item,
                backend_logs_item,
            ),
        ),
        (
            "Configuration",
            (
                settings_item,
                proxmox_endpoints_item,
                netbox_endpoints_item,
                fastapi_endpoints_item,
                ssh_credentials_item,
            ),
        ),
        (
            "Join our community",
            (
                contributing_item,
                community_item,
            ),
        ),
    ),
    icon_class="mdi mdi-dns",
)
