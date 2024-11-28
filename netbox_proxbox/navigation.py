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

contributing_item = PluginMenuItem(
    link='plugins:netbox_proxbox:contributing',
    link_text='Contributing!',
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
        ('Proxmox Plugin', (fullupdate_item, nodes_item, virtual_machines_item,)),
        ('Join our community', (contributing_item, community_item,)),
    ),
    icon_class='mdi mdi-dns'
)