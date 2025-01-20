# TODO: Create Default Custom Fields
from proxbox_api.session.netbox import NetboxSessionDep
from proxbox_api.logging import log

from fastapi import WebSocket

async def create_default_custom_fields(
    nb: NetboxSessionDep,
    websocket: WebSocket,
    custom_field: str,
):
    if custom_field == "proxmox_vm_id":
        custom_field_id = nb.session.extras.custom_fields.create(
            {
                "object_types": [
                    "virtualization.virtualmachine"
                ],
                "type": "integer",
                "name": "proxmox_vm_id",
                "label": "VM ID",
                "description": "Proxmox Virtual Machine or Container ID",
                "ui_visible": "always",
                "ui_editable": "hidden",
                "weight": 100,
                "filter_logic": "loose",
                "search_weight": 1000,
                "group_name": "Proxmox"
            }
        )

        if custom_field_id:
            print(f"Custom Field Created: {custom_field_id}")
            return custom_field_id

    if custom_field == "proxmox_start_at_boot":
        start_at_boot_field = nb.session.extras.custom_fields.create(
            {
                "object_types": [
                    "virtualization.virtualmachine"
                ],
                "type": "boolean",
                "name": "proxmox_start_at_boot",
                "label": "Start at Boot",
                "description": "Proxmox Start at Boot Option",
                "ui_visible": "always",
                "ui_editable": "hidden",
                "weight": 100,
                "filter_logic": "loose",
                "search_weight": 1000,
                "group_name": "Proxmox"
            }
        )

        if start_at_boot_field:
            print(f"Custom Field Created: {start_at_boot_field}")
            return start_at_boot_field
    
    if custom_field == "proxmox_unprivileged_container":
        start_unprivileged_field = nb.session.extras.custom_fields.create(
            {
                "object_types": [
                    "virtualization.virtualmachine"
                ],
                "type": "boolean",
                "name": "proxmox_unprivileged_container",
                "label": "Unprivileged Container",
                "description": "Proxmox Unprivileged Container",
                "ui_visible": "if-set",
                "ui_editable": "hidden",
                "weight": 100,
                "filter_logic": "loose",
                "search_weight": 1000,
                "group_name": "Proxmox"
            }
        )

        if start_unprivileged_field:
            print(f"Custom Field Created: {start_unprivileged_field}")
            return start_unprivileged_field
    
    if custom_field == "proxmox_qemu_agent":
        start_qemu_agent_field = nb.session.extras.custom_fields.create(
            {
                "object_types": [
                    "virtualization.virtualmachine"
                ],
                "type": "boolean",
                "name": "proxmox_qemu_agent",
                "label": "QEMU Guest Agent",
                "description": "Proxmox QEMU Guest Agent",
                "ui_visible": "if-set",
                "ui_editable": "hidden",
                "weight": 100,
                "filter_logic": "loose",
                "search_weight": 1000,
                "group_name": "Proxmox"
            }
        )

        if start_qemu_agent_field:
            print(f"Custom Field Created: {start_qemu_agent_field}")
            return start_qemu_agent_field
    
    if custom_field == "proxmox_search_domain":
        search_domain_field = nb.session.extras.custom_fields.create(
            {
                "object_types": [
                    "virtualization.virtualmachine"
                ],
                "type": "text",
                "name": "proxmox_search_domain",
                "label": "Search Domain",
                "description": "Proxmox Search Domain",
                "ui_visible": "if-set",
                "ui_editable": "hidden",
                "weight": 100,
                "filter_logic": "loose",
                "search_weight": 1000,
                "group_name": "Proxmox"
            }
        )

        if search_domain_field:
            print(f"Custom Field Created: {search_domain_field}")
            return search_domain_field
    
    return None

# TODO: Create Default Objects
async def create_default_objects():
    # Create Default Sites

    # Create Default Device Types

    # Create Default Device Roles

    # Create Default Cluster Types

    # Create Default Clusters

    # Create Default Devices
    pass