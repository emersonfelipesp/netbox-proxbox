"""Define the NetBox plugin navigation menu and shortcut buttons."""

from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
# from utilities.choices import ButtonColorChoices

fullupdate_item = PluginMenuItem(
    link="plugins:netbox_proxbox:home",
    link_text="Homepage",
)

nodes_item = PluginMenuItem(
    link="plugins:netbox_proxbox:nodes",
    link_text="Nodes (Devices)",
)

virtual_machines_item = PluginMenuItem(
    link="plugins:netbox_proxbox:virtual_machines",
    link_text="Virtual Machines",
)

lxc_containers_item = PluginMenuItem(
    link="plugins:netbox_proxbox:lxc_containers",
    link_text="LXC Containers",
)

storage_item = PluginMenuItem(
    link="plugins:netbox_proxbox:proxmoxstorage_list",
    link_text="Storage",
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

settings_item = PluginMenuItem(
    link="plugins:netbox_proxbox:settings",
    link_text="Settings",
)

backups_item = PluginMenuItem(
    link="plugins:netbox_proxbox:vmbackup_list",
    link_text="Backups",
)

snapshots_item = PluginMenuItem(
    link="plugins:netbox_proxbox:vmsnapshot_list",
    link_text="Snapshots",
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

community_item = PluginMenuItem(
    link="plugins:netbox_proxbox:community",
    link_text="Community",
    buttons=[
        PluginMenuButton(
            "plugins:netbox_proxbox:discussions",
            "GitHub Discussions",
            "mdi mdi-github",
            # ButtonColorChoices.GRAY,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:discord",
            "Discord Community",
            "mdi mdi-forum",
            # ButtonColorChoices.BLACK,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:telegram",
            "Telegram Community",
            "mdi mdi-send",
            # ButtonColorChoices.BLUE,
        ),
    ],
)


menu = PluginMenu(
    label="Proxbox",
    groups=(
        (
            "Proxmox Plugin",
            (
                fullupdate_item,
                nodes_item,
                virtual_machines_item,
                lxc_containers_item,
                storage_item,
                backups_item,
                snapshots_item,
                schedule_sync_item,
                sync_jobs_item,
                settings_item,
            ),
        ),
        (
            "Endpoints",
            (
                proxmox_endpoints_item,
                netbox_endpoints_item,
                fastapi_endpoints_item,
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
