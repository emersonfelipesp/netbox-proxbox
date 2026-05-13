"""NetBox plugin navigation menu for netbox-pbs.

PR C1 ships a single placeholder item pointing at the plugin home view.
Datastore / snapshot / job lists are added in PR C2 when the domain
models land.
"""

from netbox.plugins import PluginMenu, PluginMenuItem


home_item = PluginMenuItem(
    link="plugins:netbox_pbs:home",
    link_text="Home",
)


menu = PluginMenu(
    label="Proxmox Backup Server",
    groups=(
        (
            "PBS",
            (home_item,),
        ),
    ),
    icon_class="mdi mdi-database-clock",
)
