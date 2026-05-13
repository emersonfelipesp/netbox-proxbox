"""NetBox plugin navigation menu for netbox-pbs.

One top-level menu (``Proxmox Backup Server``) with three groups:

* **Inventory** — PBSEndpoint (editable) and PBSNode (read-only mirror).
* **Backups** — PBSDatastore, PBSBackupGroup, PBSSnapshot (all read-only).
* **Jobs** — PBSJobStatus (read-only).

The five reflected models intentionally show no add/import buttons in
the navigation; the read-only enforcement lives in ``views.py`` where
no ``edit``/``bulk_*`` views are registered.
"""

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


pbs_endpoint_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbsendpoint_list",
    link_text="PBS Endpoints",
    permissions=["netbox_pbs.view_pbsendpoint"],
    buttons=(
        PluginMenuButton(
            link="plugins:netbox_pbs:pbsendpoint_add",
            title="Add PBS Endpoint",
            icon_class="mdi mdi-plus-thick",
            permissions=["netbox_pbs.add_pbsendpoint"],
        ),
        PluginMenuButton(
            link="plugins:netbox_pbs:pbsendpoint_bulk_import",
            title="Import PBS Endpoints",
            icon_class="mdi mdi-upload",
            permissions=["netbox_pbs.add_pbsendpoint"],
        ),
    ),
)


pbs_node_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbsnode_list",
    link_text="PBS Nodes",
    permissions=["netbox_pbs.view_pbsnode"],
)


pbs_datastore_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbsdatastore_list",
    link_text="Datastores",
    permissions=["netbox_pbs.view_pbsdatastore"],
)


pbs_backup_group_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbsbackupgroup_list",
    link_text="Backup Groups",
    permissions=["netbox_pbs.view_pbsbackupgroup"],
)


pbs_snapshot_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbssnapshot_list",
    link_text="Snapshots",
    permissions=["netbox_pbs.view_pbssnapshot"],
)


pbs_job_status_item = PluginMenuItem(
    link="plugins:netbox_pbs:pbsjobstatus_list",
    link_text="Job Status",
    permissions=["netbox_pbs.view_pbsjobstatus"],
)


menu = PluginMenu(
    label="Proxmox Backup Server",
    groups=(
        ("Inventory", (pbs_endpoint_item, pbs_node_item)),
        ("Backups", (pbs_datastore_item, pbs_backup_group_item, pbs_snapshot_item)),
        ("Jobs", (pbs_job_status_item,)),
    ),
    icon_class="mdi mdi-database-clock",
)
