"""NetBox plugin navigation menu for netbox-packer."""

from __future__ import annotations

from netbox.plugins import PluginMenu, PluginMenuItem


menu = PluginMenu(
    label="Packer",
    groups=(
        (
            "Image Factory",
            (
                PluginMenuItem(
                    link="plugins:netbox_packer:packerimagedefinition_list",
                    link_text="Image Definitions",
                    permissions=["netbox_packer.view_packerimagedefinition"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_packer:packerimagebuild_list",
                    link_text="Image Builds",
                    permissions=["netbox_packer.view_packerimagebuild"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_packer:packerpluginsettings_singleton_edit",
                    link_text="Plugin Settings",
                    permissions=["netbox_packer.change_packerpluginsettings"],
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-package-variant-closed",
)
