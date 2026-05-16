"""NetBox plugin navigation menu for netbox-pbs."""

from __future__ import annotations

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

_buttons = {
    "servers": [
        PluginMenuButton(
            link="plugins:netbox_pbs:pbsserver_add",
            title="Add server",
            icon_class="mdi mdi-plus-thick",
            permissions=["netbox_pbs.add_pbsserver"],
        ),
    ],
    "settings": [
        PluginMenuButton(
            link="plugins:netbox_pbs:pbspluginsettings_singleton_edit",
            title="Edit settings",
            icon_class="mdi mdi-cog",
        ),
    ],
}

_items = (
    PluginMenuItem(
        link="plugins:netbox_pbs:pbsserver_list",
        link_text="Servers",
        permissions=["netbox_pbs.view_pbsserver"],
        buttons=_buttons["servers"],
    ),
    PluginMenuItem(
        link="plugins:netbox_pbs:pbsdatastore_list",
        link_text="Datastores",
        permissions=["netbox_pbs.view_pbsdatastore"],
    ),
    PluginMenuItem(
        link="plugins:netbox_pbs:pbssnapshot_list",
        link_text="Snapshots",
        permissions=["netbox_pbs.view_pbssnapshot"],
    ),
    PluginMenuItem(
        link="plugins:netbox_pbs:pbsjob_list",
        link_text="Jobs",
        permissions=["netbox_pbs.view_pbsjob"],
    ),
    PluginMenuItem(
        link="plugins:netbox_pbs:pbspluginsettings_singleton_edit",
        link_text="Plugin Settings",
        permissions=["netbox_pbs.change_pbspluginsettings"],
        buttons=_buttons["settings"],
    ),
)

menu = PluginMenu(
    label="PBS",
    groups=(("Inventory", _items),),
    icon_class="mdi mdi-database-clock",
)
