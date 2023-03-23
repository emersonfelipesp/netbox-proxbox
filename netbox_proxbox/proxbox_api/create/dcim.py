# PLUGIN_CONFIG variables
from ..plugins_config import (
    NETBOX_SESSION as nb,
    NETBOX_NODE_ROLE_ID,
    NETBOX_SITE_ID,
)

from . import (
    extras,
    virtualization,
)

import logging

#
# dcim.manufacturers
#
def manufacturer():
    proxbox_manufacturer_name = 'Proxbox Basic Manufacturer'
    proxbox_manufacturer_slug = 'proxbox-manufacturer'
    proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    # Check if Proxbox manufacturer already exists.
    proxbox_manufacturer = nb.dcim.manufacturers.get(
        name = proxbox_manufacturer_name,
        slug = proxbox_manufacturer_slug,
    )

    if proxbox_manufacturer == None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            manufacturer = nb.dcim.manufacturers.create(
                name = proxbox_manufacturer_name,
                slug = proxbox_manufacturer_slug,
                description = proxbox_manufacturer_desc
            )
        except:
            return f"Error creating the '{proxbox_manufacturer_name}' manufacturer. Possible errors: the name '{proxbox_manufacturer_name}' or slug '{proxbox_manufacturer_slug}' is already used."
    
    else:
        manufacturer = proxbox_manufacturer
    
    return manufacturer


#
# dcim.device_types
#
def device_type():
    proxbox_device_type_model = 'Proxbox Model'
    proxbox_device_type_slug = 'proxbox-model'
    proxbox_device_type_comments = "Device Type Proxbox will use when creating the Cluster's Nodes. When the Node is created, you can change the device type to the actual server model."

    # Check if Proxbox manufacturer already exists.
    proxbox_device_types = nb.dcim.device_types.get(
        model = proxbox_device_type_model,
        slug = proxbox_device_type_slug
    )

    if proxbox_device_types == None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            device_type = nb.dcim.device_types.create(
                manufacturer = manufacturer().id,
                model = proxbox_device_type_model,
                slug = proxbox_device_type_slug,
                comments = proxbox_device_type_comments,
                tags = [extras.tag().id]
            )
        except:
            log_message = f"Error creating the '{proxbox_device_type_model}' device type. Possible errors: the model '{proxbox_device_type_model}' or slug '{proxbox_device_type_slug}' is already used."
            logging.error(log_message)
            return log_message
    
    else:
        device_type = proxbox_device_types
    
    return device_type


#
# dcim.sites
#
def site(**kwargs):
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)

    if not isinstance(site_id, int):
        return 'Site ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured SITE_ID in Netbox's PLUGINS_CONFIG, use it.
    if site_id > 0:
        site = nb.dcim.sites.get(id = site_id)
        
        if site == None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif site_id == 0:
        site_proxbox_name = "Proxbox Basic Site"
        site_proxbox_slug = 'proxbox-basic-site'

        # Verify if basic site is already created
        site_proxbox = nb.dcim.sites.get(
            name = site_proxbox_name,
            slug = site_proxbox_slug
        )

        # Create a basic Proxbox site if not created yet.
        if site_proxbox == None:
            try:
                site = nb.dcim.sites.create(
                    name = site_proxbox_name,
                    slug = site_proxbox_slug,
                    status = 'active',
                    tags = [extras.tag().id]
                )
            except:
                return f"Error creating the '{site_proxbox_name}' site. Possible errors: the name '{site_proxbox_name}' or slug '{site_proxbox_slug}' is already used."

        # If basic site already created, use it.
        else:
            site = site_proxbox

    else:
        return 'Site ID configured is invalid.'

    return site


#
# dcim.devices (nodes)
#
def node(proxmox_node):
    # Create json with basic NODE information
    node_json = {}
    node_json["name"] = proxmox_node['name']
    node_json["device_role"] = extras.role(role_id = NETBOX_NODE_ROLE_ID).id
    node_json["device_type"] = device_type().id
    node_json["site"] = site(site_id = NETBOX_SITE_ID).id
    node_json["status"] = 'active'
    node_json["tags"] = [extras.tag().id]

    cluster = virtualization.cluster()
    if cluster:
        if cluster != None:
            node_json["cluster"] = cluster.id
    
    # If device already exists, append (2) to final of the name
    check_duplicate = proxmox_node.get("duplicate", False)
    if check_duplicate:
        # Redefine name appending (2) to final
        node_json["name"] = f"{proxmox_node['name']} (2)"


        original_device = proxmox_node.get("netbox_original_device", None)
        if original_device:
            node_json["comments"] = f"The original device has the following info:<br>**Device ID:** {original_device.id}<br>**Name:** {original_device.name}"

        netbox_obj = None
        search_device = None

        # Create Node with json 'node_json'
        try:
            # GET
            search_device = nb.dcim.devices.get(
                name = node_json["name"],
                cluster = node_json["cluster"]
            )
            return search_device
        except Exception as error:
            logging.error(error)
        
        try:
            # CREATE
            if search_device == None:
                netbox_obj = nb.dcim.devices.create(node_json)
                return netbox_obj
        except Exception as error:
            logging.error(error)

        finally:
            logging.error("[proxbox_api.create.node] Creation of NODE failed.")
            netbox_obj = None
    
    # If NODE is not DUPLICATED, then CREATE it.
    else:
         # Create Node with json 'node_json'
        try:
            netbox_obj = nb.dcim.devices.create(node_json)

        except:
            logging.error("[proxbox_api.create.node] Creation of NODE failed.")
            netbox_obj = None
            return netbox_obj
    
    # In case nothing works, returns error
    netbox_obj = None
    return netbox_obj