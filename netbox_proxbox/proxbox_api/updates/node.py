from .. import (
    create,
)

# Update STATUS field on /dcim/device/{id}
def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node['online'] == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status.value == 'offline':
            netbox_node.status.value = 'active'
            
            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False


    elif proxmox_node['online'] == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status.value == 'active':
            netbox_node.status.value = 'offline'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False

    else:
        status_updated = False

    return status_updated




# Update CLUSTER field on /dcim/device/{id}
def cluster(netbox_node, proxmox_node, proxmox_cluster):
    #
    # Compare CLUSTER
    #
    if proxmox_cluster != None:
        # If cluster is filled, but different from actual cluster, update it.
        if netbox_node.cluster.name != proxmox_cluster['name']:
            # Search for Proxmox Cluster using create.cluster() function
            cluster_id = create.virtualization.cluster().id

            # Use Cluster ID to update NODE information
            netbox_node.cluster.id = cluster_id

            if netbox_node.save() == True:
                cluster_updated = True
            else:
                cluster_updated = False

        else:
            cluster_updated = False

    # If cluster is empty, update it.
    elif proxmox_cluster == None:
        # Search for Proxmox Cluster using create.cluster() function
        cluster_id = create.virtualization.cluster().id

        # Use Cluster ID to update NODE information
        netbox_node.cluster.id = cluster_id

        if netbox_node.save() == True:
            cluster_updated = True
        else:
            cluster_updated = False
    
    # If cluster was not empty and also not different, do not make any change.
    else:
        cluster_updated = False

    return cluster_updated
