from .plugins_config import (
    NETBOX_VM_ROLE_ID,
    NETBOX_NODE_ROLE_ID,
    NETBOX_SITE_ID,
    PROXMOX_SESSION as proxmox,
    NETBOX_SESSION as nb,
)

#
# FIXED ITEMS (the ones Proxbox doesn't allow to override with PLUGINS_CONFIG)
#

# extras.tags
# 
def tag():
    proxbox_tag_name = 'Proxbox'
    proxbox_tag_slug = 'proxbox'

    # Check if Proxbox tag already exists.
    proxbox_tag = nb.extras.tags.get(
        name = proxbox_tag_name,
        slug = proxbox_tag_slug
    )

    if proxbox_tag == None:
        try:
            # If Proxbox tag does not exist, create one.
            tag = nb.extras.tags.create(
                name = proxbox_tag_name,
                slug = proxbox_tag_slug,
                color = 'ff5722',
                description = "Proxbox Identifier (used to identify the items the plugin created)"
            )
        except:
            return "Error creating the '{0}' tag. Possible errors: the name '{0}' or slug '{1}' is already used.".format(proxbox_tag_name, proxbox_tag_slug)
    else:
        tag = proxbox_tag

    return tag




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
            return "Error creating the '{0}' manufacturer. Possible errors: the name '{0}' or slug '{1}' is already used.".format(proxbox_manufacturer_name, proxbox_manufacturer_slug)
    
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
                tags = [tag().id]
            )
        except:
            return "Error creating the '{0}' device type. Possible errors: the model '{0}' or slug '{1}' is already used.".format(proxbox_device_type_model, proxbox_device_type_slug)
    
    else:
        device_type = proxbox_device_types
    
    return device_type





#
# dcim.device_roles
#
def role(**kwargs):
    # If role_id equals to 0, consider it is not configured by user and must be created by Proxbox
    role_id = kwargs.get("role_id", 0)

    if not isinstance(role_id, int):
        return 'Role ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured ROLE_ID in Netbox's PLUGINS_CONFIG, use it.
    if role_id > 0:
        role = nb.dcim.device_roles.get(id = role_id)
        
        if role == None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif role_id == 0:
        role_proxbox_name = "Proxbox Basic Role"
        role_proxbox_slug = 'proxbox-basic-role'

        # Verify if basic role is already created
        role_proxbox = nb.dcim.device_roles.get(
            name = role_proxbox_name,
            slug = role_proxbox_slug
        )

        # Create a basic Proxbox VM/Node Role if not created yet.
        if role_proxbox == None:

            try:
                role = nb.dcim.device_roles.create(
                    name = role_proxbox_name,
                    slug = role_proxbox_slug,
                    color = 'ff5722',
                    vm_role = True
                )
            except:
                return "Error creating the '{0}' role. Possible errors: the name '{0}' or slug '{1}' is already used.".format(role_proxbox_name, role_proxbox_slug)
        
        # If basic role already created, use it.
        else:
            role = role_proxbox

    else:
        return 'Role ID configured is invalid.'

    return role





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
                    tags = [tag().id]
                )
            except:
                return "Error creating the '{0}' site. Possible errors: the name '{0}' or slug '{1}' is already used.".format(site_proxbox_name, site_proxbox_slug)

        # If basic site already created, use it.
        else:
            site = site_proxbox

    else:
        return 'Site ID configured is invalid.'

    return site





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
                tags = [tag().id]
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
    # # Create VM/CT with basic information
    vm_json = {}
    vm_json["name"] = proxmox_vm['name']
    vm_json["status"] = 'active'
    vm_json["cluster"] = cluster()
    vm_json["role"] = role(role_id = NETBOX_VM_ROLE_ID)
    vm_json["tags"] = [tag().id]

    # Cria VM/CT com json criado
    try:
        netbox_obj = nb.virtualization.virtual_machines.create(vm_json)

    except:
        print("[proxbox.create.virtual_machine] Falha na criação da VM")
        netbox_obj = None

    else:
        return netbox_obj

    # Caso nada funcione, volte erro
    netbox_obj = None
    return netbox_obj