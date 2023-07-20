from extras.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
from utilities.choices import ButtonColorChoices

proxbox_item = PluginMenuItem(
    link='plugins:netbox_proxbox:home',
    link_text='Full Update',
)

menu = PluginMenu(
    label='Proxbox',
    groups=(
        ('Proxmox Plugin', (proxbox_item,)),
    ),
    icon_class='mdi mdi-dns'
)