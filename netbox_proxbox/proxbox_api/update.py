# PLUGIN_CONFIG variables
from .plugins_config import (
    PROXMOX,
    PROXMOX_PORT,
    PROXMOX_USER,
    PROXMOX_PASSWORD,
    PROXMOX_SSL,
    NETBOX,
    NETBOX_TOKEN,
    PROXMOX_SESSION as proxmox,
    NETBOX_SESSION as nb,
)

from . import (
    updates,
    create,
    remove,
)



# Call all functions to update Virtual Machine
def vm_full_update(netbox_vm, proxmox_vm):
    changes = {}

    # Update 'status' field, if necessary.
    status_updated = updates.virtual_machine.status(netbox_vm, proxmox_vm)
                
    # Update 'custom_fields' field, if necessary.
    custom_fields_updated = updates.virtual_machine.custom_fields(netbox_vm, proxmox_vm)

    # Update 'local_context_data' json, if necessary.
    local_context_updated = updates.virtual_machine.local_context_data(netbox_vm, proxmox_vm)

    # Update 'resources', like CPU, Memory and Disk, if necessary.
    resources_updated = updates.virtual_machine.resources(netbox_vm, proxmox_vm)

    tag_updated = updates.extras.tag(netbox_vm)

    #changes = [custom_fields_updated, status_updated, local_context_updated, resources_updated]
    changes = {
        "status" : status_updated,
        "custom_fields" : custom_fields_updated,
        "local_context" : local_context_updated,
        "resources" : resources_updated,
        "tag" : tag_updated
    }

    return changes



def node_full_update(netbox_node, proxmox_json, proxmox_cluster):
    changes = {}

    status_updated = updates.node.status(netbox_node, proxmox_json)
    cluster_updated = updates.node.cluster(netbox_node, proxmox_json, proxmox_cluster)

    changes = {
        "status" : status_updated,
        "cluster" : cluster_updated
    }

    return changes



# Verify if VM/CT exist on Netbox
def is_vm_on_netbox(netbox_vm):
    # Search VM on Netbox by using VM Name gotten from Proxmox
    # VM doesn't exist on Netbox
    if netbox_vm == None:
        vm_on_netbox = False

    # VM already exist on Netbox
    else:
        vm_on_netbox = True

    return vm_on_netbox



def search_by_proxmox_id(proxmox_id):
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    for px_vm in all_proxmox_vms:
        px_id = px_vm.get("vmid")
        
        if px_id == proxmox_id:
            proxmox_vm = px_vm
            return proxmox_vm
    
    # If JSON not found, return None.
    return None



def search_by_proxmox_name(proxmox_name):
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    for px_vm in all_proxmox_vms:
        px_name = px_vm.get("name")

        if proxmox_name == px_name:
            proxmox_vm = px_vm
            return proxmox_vm

    # If JSON not found, return None.
    return None



def search_by_id(id):
    # Save Netbox VirtualMachine object
    netbox_obj = nb.virtualization.virtual_machines.get(id)

    proxmox_name = netbox_obj.name

    # Search Proxmox ID on Netbox
    local_context = netbox_obj.local_context_data
    if local_context != None:
        proxmox_json = local_context.get("proxmox")

        if proxmox_json != None:
            proxmox_id = proxmox_json.get("id")
            
            if proxmox_id != None:
                return proxmox_id

    # Return Proxmox Name in case ID not found.
    return proxmox_name



# Makes all necessary checks so that VM/CT exist on Netbox.
def virtual_machine(**kwargs):
    # JSON containing the result of the VM changes
    json_vm = {}

    # args:
    # proxmox_json
    # id
    # proxmox_id
    # name
    #
    # Save args and validate types
    #
    # Save arg
    proxmox_id = kwargs.get('proxmox_id')

    # Validate type
    if proxmox_id != None:
        proxmox_id_type = type(proxmox_id)
        if 'int' not in str(proxmox_id_type):
            print('[ERROR] "proxmox_id" MUST be integer. Type used: {}'.format(proxmox_id_type))
            #return False
            json_vm["result"] = False

    # Save arg
    id = kwargs.get('id')

    # Validate type
    if id != None:
        id_type = type(id)
        if 'int' not in str(id_type):
            print('[ERROR] "id" MUST be integer. Type used: {}'.format(id_type))
            #return False
            json_vm["result"] = False
            
    
    # Save arg
    name = kwargs.get('name')

    # Validate type
    if name != None:
        name_type = type(name)
        if 'str' not in str(name_type):
            print('[ERROR] "name" MUST be string. Type used: {}'.format(name_type))
            #return False
            json_vm["result"] = False

    # Save arg
    proxmox_json = kwargs.get('proxmox_json')

    proxmox_vm_name = None

    # Decide whether 'proxmox_json' or other args (id, proxmox_id and proxmox_name) will be used
    if proxmox_json != None:
        proxmox_vm_name = proxmox_json['name']
        json_vm["name"] = proxmox_json['name']

    # If 'proxmox_json' was not passed as argument, use other args
    else:    
        #
        # With arguments passed on the function, search for JSON of VM on Proxmox
        # Searching priorirty:
        # 1° = id
        # 2° = proxmox_id
        # 3° = proxmox_name
        #
        # Search JSON of VM on Proxmox by using "id" argument
        if id != None:
            # Search result returns Proxmox ID or Proxmox Name, if ID doesn't exist
            search_result = search_by_id(id)

            # Verify type of the result:
            # If 'int' = Proxmox ID
            # If 'str' = Proxmox Name
            search_result_type = type(search_result)

            # Search using Proxmox ID
            if 'int' in str(search_result_type):
                proxmox_json = search_by_proxmox_id(search_result)

                # Analyze search result and returns error, if null value.
                if proxmox_json == None:
                    print("[ERROR] Error to get Proxmox Virtual Machine using 'proxmox_id'")
                    json_vm["result"] = False            

                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

            # Search using Proxmox NAME
            elif 'str' in str(search_result_type):
                proxmox_json = search_by_proxmox_name(search_result)

                # Analyze search result and returns error, if null value.
                if proxmox_json == None:
                    print("[ERROR] Error to get Proxmox Virtual Machine using 'proxmox_name'")
                    json_vm["result"] = False
                
                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

        else:
            # Search VM JSON of Proxmox using argument 'proxmox_id'
            if proxmox_id != None:
                proxmox_json = search_by_proxmox_id(proxmox_id)

                # Analyze search result and returns error, if null value.
                if proxmox_json == None:
                    print("[ERROR] Error to get Proxmox Virtual Machine using 'proxmox_id'")
                    json_vm["result"] = False      

                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

            else:
                # Search using Proxmox NAME
                if name != None:
                    proxmox_json = search_by_proxmox_name(name)

                    # Analyze search result and returns error, if null value.
                    if proxmox_json == None:
                        print("[ERROR] Error to get Proxmox Virtual Machine using 'proxmox_name'")
                        json_vm["result"] = False
                    
                    proxmox_vm_name = proxmox_json['name']
                    json_vm["name"] = proxmox_json['name']

    if proxmox_vm_name == None:
        return False

    # Search Netbox object by name gotten from Proxmox
    netbox_vm = nb.virtualization.virtual_machines.get(name = proxmox_vm_name)

    # Analyze if VM exist on Netbox
    # If VM/CT already exist on Proxmox, check VM and update it, if necessary.
    vm_on_netbox = is_vm_on_netbox(netbox_vm)

    if vm_on_netbox == True:
        # Update Netbox information
        full_update = vm_full_update(netbox_vm, proxmox_json)  
        json_vm["changes"] = full_update

        full_update_list = list(full_update.values())

        # Analyze if VM needed to be updated on Netbox
        if True in full_update_list:
            print('[OK] VM updated. -> {}'.format(proxmox_vm_name))
        else:
            print('[OK] VM already updated. -> {}'.format(proxmox_vm_name))

        # In case none of condition works, return True anyway, since VM already exist.
        json_vm["result"] = True

    # If VM does not exist, create it on Netbox
    elif vm_on_netbox == False:
        print('[OK] VM does not exist on Netbox -> {}'.format(proxmox_vm_name))


        # Analyze if VM was sucessfully created.
        netbox_vm = create.virtualization.virtual_machine(proxmox_json)

        # VM created with basic information
        if netbox_vm != None:
            # Update rest of configuration
            full_update = vm_full_update(netbox_vm, proxmox_json)  
            json_vm["changes"] = full_update

            full_update_list = list(full_update.values())

            # Analyze if update was successful
            if True in full_update_list:
                print('[OK] VM created -> {}'.format(proxmox_vm_name))


                # VM fully updated
                json_vm["result"] = True

            else:
                print('[OK] VM created, but full update failed -> {}'.format(proxmox_vm_name))               

                # VM created with basic information
                json_vm["result"] = True
        
        else:
            print('[ERROR] VM not created. -> {}'.format(proxmox_vm_name))

            # VM not created
            json_vm["result"] = False

    else:
        print("[ERROR] Unexpected error -> {}".format(proxmox_vm_name))
        
        # Unexpected error
        json_vm["result"] = False

    return json_vm



def nodes(**kwargs):
    proxmox_cluster = kwargs.get('proxmox_cluster')
    proxmox_json = kwargs.get('proxmox_json')

    proxmox_node_name = proxmox_json.get("name")

    json_node = {}

    # Search netbox using VM name
    netbox_search = nb.dcim.devices.get(name = proxmox_node_name)

    # Search node on Netbox with Proxmox node name gotten
    if nb.dcim.devices.get(name = proxmox_node_name) == None:
        # If node does not exist, create it.
        netbox_node = create.dcim.node(proxmox_json)

        # Node created
        if netbox_node != None:
            print("[OK] Node created! -> {}".format(proxmox_node_name))

            # Update rest of configuration
            full_update = node_full_update(netbox_node, proxmox_json, proxmox_cluster)  
            json_node["changes"] = full_update

            full_update_list = list(full_update.values())

            # Analyze if update was successful
            if True in full_update_list:
                print('[OK] NODE updated. -> {}'.format(proxmox_node_name))
            else:
                print('[OK] NODE already updated. -> {}'.format(proxmox_node_name))

            # return True as the node was successfully created.
            json_node["result"] = True

        # Error with node creation
        else:
            print('[ERROR] Something went wrong when creating the node.-> {}'.format(proxmox_node_name))
            json_node["result"] = False

    else:
        # If node already exist, try updating it.
        netbox_node = netbox_search

        # Update Netbox node information, if necessary.
        full_update = node_full_update(netbox_node, proxmox_json, proxmox_cluster)  
        json_node["changes"] = full_update

        full_update_list = list(full_update.values())

        # Analyze if update was successful
        if True in full_update_list:
            print('[OK] NODE updated. -> {}'.format(proxmox_node_name))
        else:
            print('[OK] NODE already updated. -> {}'.format(proxmox_node_name))

        # return True as the node was successfully created.
        json_node["result"] = True
        

        
    return json_node



# Makes everything needed so that VIRTUAL MACHINES / CONTAINERS, NODES and CLUSTER exists on Netbox
def all(**kwargs):
    print("[Proxbox - Netbox plugin | Update All]")
    cluster_all = proxmox.cluster.status.get()

    #
    # CLUSTER
    #
    cluster = create.virtualization.cluster()
    print('\n\n\nCLUSTER...')
    print('[OK] CLUSTER created. -> {}'.format(cluster.name))

    proxmox_cluster = cluster_all[0]
    #
    # NODES
    #
    print('\n\n\nNODES...')
    nodes_list = []
    proxmox_nodes = cluster_all[1:]

    # Get all NODES from Proxmox
    for px_node_each in proxmox_nodes:
        node_updated = nodes(proxmox_json = px_node_each, proxmox_cluster = proxmox_cluster)

        nodes_list.append(node_updated)


    #
    # VIRTUAL MACHINES / CONTAINERS
    #
    print('\n\n\nVIRTUAL MACHINES...')
    virtualmachines_list = []

    print('\nUPDATE ALL...')
    # Get all VM/CTs from Proxmox
    for px_vm_each in proxmox.cluster.resources.get(type='vm'):     
        vm_updated = virtual_machine(proxmox_json = px_vm_each)

        virtualmachines_list.append(vm_updated)

    # Get "remove_unused" passed on function call
    remove_unused = kwargs.get("remove_unused", False)

    # Remove Netbox's old data
    if remove_unused == True:
        print('\nREMOVE UNUSED DATA...')
        remove_info = remove.all()
    else:
        remove_info = False
    #
    # BUILD JSON RESULT
    #
    result = {}
    result["virtualmachines"] = virtualmachines_list
    result["nodes"] = nodes_list
    result["remove_unused"] = remove_info

    return result


# Runs if script executed directly
if __name__ == "__main__":
    print('#\n# COMPARE PROXMOX WITH NETBOX\n#')
    all()

    print('____________________________________\n')
    print('#\n# COMPARE PROXMOX WITH NETBOX\n#')
    remove.all()