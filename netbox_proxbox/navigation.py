from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
#from utilities.choices import ButtonColorChoices

fullupdate_item = PluginMenuItem(
    link='plugins:netbox_proxbox:home',
    link_text='Full Update',
)

nodes_item = PluginMenuItem(
    link='plugins:netbox_proxbox:nodes',
    link_text='Nodes (Devices)',
)

virtual_machines_item = PluginMenuItem(
    link='plugins:netbox_proxbox:virtual_machines',
    link_text='Virtual Machines',
)

sync_processes_item = PluginMenuItem(
    link='plugins:netbox_proxbox:syncprocess_list',
    link_text='Sync Processes',
)

contributing_item = PluginMenuItem(
    link='plugins:netbox_proxbox:contributing',
    link_text='Contributing!',
)

"""
    Endpoints Navigation Buttons.
"""
proxmox_endpoints_item = PluginMenuItem(
    link='plugins:netbox_proxbox:proxmoxendpoint_list',
    link_text='Proxmox API',
    buttons=(
        PluginMenuButton('plugins:netbox_proxbox:proxmoxendpoint_add', 'Add Proxmox Endpoint', 'mdi mdi-plus'),
    )
)

netbox_endpoints_item = PluginMenuItem(
    link='plugins:netbox_proxbox:netboxendpoint_list',
    link_text='NetBox API',
    buttons=(
        PluginMenuButton('plugins:netbox_proxbox:netboxendpoint_add', 'Add NetBox Endpoint', 'mdi mdi-plus'),
    )
)

fastapi_endpoints_item = PluginMenuItem(
    link='plugins:netbox_proxbox:fastapiendpoint_list',
    link_text='ProxBox API (FastAPI)',
    buttons=(
        PluginMenuButton('plugins:netbox_proxbox:fastapiendpoint_add', 'Add Proxbox API Endpoint', 'mdi mdi-plus'),
    )
)

community_item = PluginMenuItem(
    link='plugins:netbox_proxbox:community',
    link_text='Community',
    buttons=[
        PluginMenuButton(
            "plugins:netbox_proxbox:discussions",
            "GitHub Discussions",
            "mdi mdi-github",
            #ButtonColorChoices.GRAY,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:discord",
            "Discord Community",
            "mdi mdi-forum",
            #ButtonColorChoices.BLACK,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:telegram",
            "Telegram Community",
            "mdi mdi-send",
            #ButtonColorChoices.BLUE,
        ),
    ]
)


menu = PluginMenu(
    label='Proxbox',
    groups=(
        ('Proxmox Plugin', (
                fullupdate_item,
                nodes_item,
                virtual_machines_item,
                sync_processes_item,
            )
         ),
        ('Endpoints', (proxmox_endpoints_item, netbox_endpoints_item, fastapi_endpoints_item,)),
        ('Join our community', (contributing_item, community_item,)),
    ),
    icon_class='mdi mdi-dns'
)