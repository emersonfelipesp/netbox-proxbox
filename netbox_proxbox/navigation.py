from extras.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
from utilities.choices import ButtonColorChoices

fullupdate_item = PluginMenuItem(
    link='plugins:netbox_proxbox:home',
    link_text='Full Update',
)

contributing_item = PluginMenuItem(
    link='plugins:netbox_proxbox:contributing',
    link_text='Contributing!',
    buttons=[
        PluginMenuButton(
            "plugins:netbox_proxbox:discussions",
            "GitHub Discussions",
            "mdi mdi-github",
            ButtonColorChoices.RED,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:discord",
            "Discord Community",
            "mdi mdi-forum",
            ButtonColorChoices.BLACK,
        ),
        PluginMenuButton(
            "plugins:netbox_proxbox:telegram",
            "Telegram Community",
            "mdi mdi-send",
            ButtonColorChoices.BLUE,
        )
    ]
)


menu = PluginMenu(
    label='Proxbox',
    groups=(
        ('Proxmox Plugin', (fullupdate_item, contributing_item)),
    ),
    icon_class='mdi mdi-dns'
)