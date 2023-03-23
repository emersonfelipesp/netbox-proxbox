import sys

# PLUGIN_CONFIG variables
from ..plugins_config import (
    NETBOX_SESSION as nb,
    PROXMOX_SESSION as proxmox,
    NETBOX_VM_ROLE_ID,

)

from . import (
    extras,
)

import logging

#
# virtualization.cluster_types
#
def cluster_type():
    #
    # Cluster Type
    #
    cluster_type_name = 'Proxmox'
    cluster_type_slug = 'proxmox'
    
    cluster_type_proxbox = nb.virtualization.cluster_types.get(
        name = cluster_type_name,
        slug = cluster_type_slug
    )

    # If no 'cluster_type' found, create one
    if cluster_type_proxbox == None:

        try:
            cluster_type = nb.virtualization.cluster_types.create(
                name = cluster_type_name,
                slug = cluster_type_slug,
                description = 'Proxmox Virtual Environment. Open-source server management platform'
            )
        except Exception as request_error:
            raise RuntimeError(f"Error creating the '{cluster_type_name}' cluster type.") from request_error

    else:
        cluster_type = cluster_type_proxbox
    
    return cluster_type






# 
# virtualization.clusters
#
def cluster():
    #
    # Cluster
    #
    # Search cluster name on Proxmox
    proxmox_cluster = proxmox.cluster.status.get()
    proxmox_cluster_name = proxmox_cluster[0].get("name")

    # Verify if there any cluster created with:
    # Name equal to Proxmox's Cluster name
    # Cluster type equal to 'proxmox'
    try:
        cluster_proxbox = nb.virtualization.clusters.get(
           name = proxmox_cluster_name,
           type = cluster_type().slug
        )
    except ValueError as error:
        logging.error(f"[ERROR] More than one cluster is created with the name '{proxmox_cluster_name}', making proxbox to abort update.\n   > {error}")
        return
    
    nb_cluster_name = None
    try:
        if cluster_proxbox != None:
            nb_cluster_name = cluster_proxbox.name
    except Exception as error:
        logging.error(f"[ERROR] {error}")

    duplicate = False
    try:
        # Check if Proxbox tag exist.
        if cluster_proxbox != None:
            search_tag = cluster_proxbox.tags.index(extras.tag())
    except ValueError as error:
        logging.warning(f"[WARNING] Cluster with the same name as {nb_cluster_name} already exists.\n> Proxbox will create another one with (2) in the name\n{error}")
        cluster_proxbox = False
        duplicate = True

    # If 'cluster' is found, check for duplicated and create another one, if necessary:
    if cluster_proxbox != None:
        # Check if it is duplicated:
        if duplicate == True:
            proxmox_cluster_name = f"{proxmox_cluster_name} (2)" 

            # Check if duplicated device was already created.
            try:
                search_device = nb.virtualization.clusters.get(
                    name = proxmox_cluster_name
                )
                
                if search_device != None:
                    return search_device
                
            except Exception as error:
                logging.error(f"[ERROR] {error}")
        else:
            return cluster_proxbox

        try:
            # Create the cluster with only name and cluster_type
            cluster = nb.virtualization.clusters.create(
                name = proxmox_cluster_name,
                type = cluster_type().id,
                tags = [extras.tag().id]
            )
            return cluster
        except:
            return f"Error creating the '{proxmox_cluster_name}' cluster. Possible errors: the name '{proxmox_cluster_name}' is already used."
    
    # If no Cluster is found, create one.
    else:
        try:
            # Create the cluster with only name and cluster_type
            cluster = nb.virtualization.clusters.create(
                name = proxmox_cluster_name,
                type = cluster_type().id,
                tags = [extras.tag().id]
            )
            return cluster
        except:
            return f"Error creating the '{proxmox_cluster_name}' cluster. Possible errors: the name '{proxmox_cluster_name}' is already used."










#
# virtualization.virtual_machines
#
def virtual_machine(proxmox_vm, duplicate):
    # Create json with basic VM/CT information
    vm_json = {}
    netbox_obj = None

    if proxmox_vm['status'] == 'running':
        vm_json["status"] = 'active'
    elif proxmox_vm == 'stopped':
        vm_json["status"] = 'offline'

    if duplicate:
        logging.warning("[WARNING] VM/CT is duplicated")
        vm_json["name"] = f"{proxmox_vm['name']} (2)"
    else:
        vm_json["name"] = proxmox_vm['name']
    
    vm_json["status"] = 'active'
    vm_json["cluster"] = cluster().id
    vm_json["role"] = extras.role(role_id = NETBOX_VM_ROLE_ID).id
    vm_json["tags"] = [extras.tag().id]
    
    # Create VM/CT with json 'vm_json'
    try:
        netbox_obj = nb.virtualization.virtual_machines.create(vm_json)
        return netbox_obj

    except:
        logging.error("[proxbox.create.virtual_machine] Creation of VM/CT failed.")
        netbox_obj = None

    
    return netbox_obj
