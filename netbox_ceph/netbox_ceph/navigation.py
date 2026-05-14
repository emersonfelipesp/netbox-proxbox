"""NetBox plugin navigation menu for netbox-ceph."""

from __future__ import annotations

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


_buttons = {
    "settings": [
        PluginMenuButton(
            link="plugins:netbox_ceph:cephpluginsettings_singleton_edit",
            title="Edit settings",
            icon_class="mdi mdi-cog",
        ),
    ],
}


_items = (
    PluginMenuItem(
        link="plugins:netbox_ceph:cephcluster_list",
        link_text="Clusters",
        permissions=["netbox_ceph.view_cephcluster"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephdaemon_list",
        link_text="Daemons",
        permissions=["netbox_ceph.view_cephdaemon"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephosd_list",
        link_text="OSDs",
        permissions=["netbox_ceph.view_cephosd"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephpool_list",
        link_text="Pools",
        permissions=["netbox_ceph.view_cephpool"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephfilesystem_list",
        link_text="Filesystems",
        permissions=["netbox_ceph.view_cephfilesystem"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephcrushrule_list",
        link_text="CRUSH Rules",
        permissions=["netbox_ceph.view_cephcrushrule"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephflag_list",
        link_text="Flags",
        permissions=["netbox_ceph.view_cephflag"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephhealthcheck_list",
        link_text="Health Checks",
        permissions=["netbox_ceph.view_cephhealthcheck"],
    ),
    PluginMenuItem(
        link="plugins:netbox_ceph:cephpluginsettings_singleton_edit",
        link_text="Plugin Settings",
        permissions=["netbox_ceph.change_cephpluginsettings"],
        buttons=_buttons["settings"],
    ),
)


menu = PluginMenu(
    label="Ceph",
    groups=(("Inventory", _items),),
    icon_class="mdi mdi-database-clock",
)
