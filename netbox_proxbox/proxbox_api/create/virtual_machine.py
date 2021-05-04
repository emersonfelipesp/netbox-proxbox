from . import (
    nb,
    extras,
)


#
# virtualization.cluster_types
#
def cluster_type():
    #
    # Cluster Type
    #
    cluster_type_name = 'Proxmox'
    cluster_type_slug = 'proxbox'
    
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
        except:
            return "Error creating the '{0}' cluster type. Possible errors: the name '{0}' or slug '{1}' is already used.".format(cluster_type_name, cluster_type_slug)   

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
    cluster_proxbox = nb.virtualization.clusters.get(
        name = proxmox_cluster_name,
        type = cluster_type().slug
    )

    # If no 'cluster' found, create one using the name from Proxmox
    if cluster_proxbox == None:

        try:
            # Create the cluster with only name and cluster_type
            cluster = nb.virtualization.clusters.create(
                name = proxmox_cluster_name,
                type = cluster_type().id,
                tags = [extras.tag().id]
            )
        except:
            return "Error creating the '{0}' cluster. Possible errors: the name '{0}' is already used.".format(proxmox_cluster_name)

    else:
        cluster = cluster_proxbox


    return cluster








#
# virtualization.virtual_machines
#
def virtual_machine(proxmox_vm):
    # Create json with basic VM/CT information
    vm_json = {}

    if proxmox_vm['online'] == 0:
        vm_json["status"] = 'offline'
    elif proxmox_vm == 1:
        vm_json["status"] = 'active'

    
    vm_json["name"] = proxmox_vm['name']
    vm_json["status"] = 'active'
    vm_json["cluster"] = cluster().id
    vm_json["role"] = role(role_id = NETBOX_VM_ROLE_ID).id
    vm_json["tags"] = [tag().id]
    
    # Create VM/CT with json 'vm_json'
    try:
        netbox_obj = nb.virtualization.virtual_machines.create(vm_json)

    except:
        print("[proxbox.create.virtual_machine] Creation of VM/CT failed.")
        netbox_obj = None

    else:
        return netbox_obj

    # In case nothing works, returns error
    netbox_obj = None
    return netbox_obj