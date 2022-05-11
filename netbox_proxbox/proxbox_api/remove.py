from . import updates

# PLUGIN_CONFIG variables
from .plugins_config import (
    PROXMOX_SESSION as proxmox,
    NETBOX_SESSION as nb,
)

# Verify if VM/CT exists on Proxmox
def is_vm_on_proxmox(netbox_vm):
    # Get json of all virtual machines from Proxmox
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    # Netbox name
    netbox_name = netbox_vm.name

    # Search Netbox local_context
    local_context = netbox_vm.local_context_data

    # Analyze local_context of VM
    if local_context == None:
        print('[WARNING] "local_context_data" not filled. -> {}'.format(netbox_name))

    else:
        # "proxmox" key of "local_context_data"
        proxmox_json = local_context.get("proxmox")
    
        # If null value, returns error
        if proxmox_json == None:
            print("[WARNING] 'local_context_data' does not have 'proxmox' json key -> {}".format(netbox_name))   

        else:
            # Netbox VM/CT ID
            netbox_id = proxmox_json.get("id")

            # If null value, returns error
            if netbox_id == None:
                print("[WARNING] 'proxmox' doest not have 'id' key -> {}".format(netbox_name))


    # List names of VM/CT's from Proxmox
    names = []

    # List ID's of VM/CT's from Proxmox
    vmids = []

    # Compare Netbox VM with all Proxmox VMs and verify if Netbox VM exist on Proxmox.
    for i in range(len(all_proxmox_vms)):
        name = all_proxmox_vms[i].get("name")
        names.append(name)

        vm_id = all_proxmox_vms[i].get("vmid")
        vmids.append(vm_id)
    

    name_on_px = False
    id_on_px = False

    # Search VM on Proxmox by using name
    try:
        name_index = names.index(netbox_name)      
    except:
        name_on_px = False
    else:
        # NAME exists on Proxmox
        name_on_px = True
        
        # If 'local_context' is null, try updating it to be able to get ID from VM
        if local_context == None:
            local_context_updated = updates.local_context_data(netbox_vm, all_proxmox_vms[name_index])

            if local_context_updated == True:
                local_context = netbox_vm.local_context_data

                if local_context != None:
                    print("[OK] 'local_context' updated' -> {}".format(netbox_name))
                    proxmox_json = local_context.get("proxmox")
                    netbox_id = proxmox_json.get("id")

                else:
                    print("[ERROR] 'local_context' is empty -> {}".format(netbox_name))
            else:
                print("[WARNING] 'local_context' was not updated (error or already updated) -> {}".format(netbox_name))


    # Search VM on Proxmox by using ID
    try:
        id_index = vmids.index(netbox_id)
    except:
        id_on_px = False
    else:
        # NAME exists on Proxmox
        id_on_px = True

    # Verify if VM exists
    if name_on_px == True:
        if id_on_px == True:
            return True
        else:
            print("[WARNING] NAME exists on Proxmox, but ID does not. -> {}".format(netbox_name))
        return True
    
    # Comparison failed, not able to find VM on Proxmox
    return False

def all():
    json_vm_all = []
    
    # Get all VM/CTs from Netbox
    netbox_all_vms = nb.virtualization.virtual_machines.all()

    for nb_vm_each in netbox_all_vms:
        json_vm = {}
        log = []

        netbox_obj = nb_vm_each
        netbox_name = netbox_obj.name
        json_vm["name"] = netbox_name

        # Verify if VM exists on Proxmox
        vm_on_proxmox = is_vm_on_proxmox(nb_vm_each)

        if vm_on_proxmox == True:
            log_message = '[OK] VM exists on both systems (Netbox and Proxmox) -> {}'.format(netbox_name)
            print(log_message)
            log.append(log_message)

            json_vm["result"] = False
        
        # If VM does not exist on Proxmox, delete VM on Netbox.
        elif vm_on_proxmox == False:
            log_message = "[WARNING] VM exists on Netbox, but not on Proxmox. Delete it!  -> {}".format(netbox_name)
            print(log_message)
            log.append(log_message)

            # Only delete VM that has proxbox tag registered
            delete_vm = False

            if len(netbox_obj.tags) > 0:
                for tag in netbox_obj.tags:

                    if tag.name == 'Proxbox' and tag.slug == 'proxbox':
                        
                        #
                        # DELETE THE VM/CT
                        #
                        delete_vm = netbox_obj.delete()
                    
                    else:
                        log_message = "[ERROR] VM will not be removed because the 'Proxbox' tag was not found. -> {}".format(netbox_name)
                        print(log_message)
                        log.append(log_message)

            elif len(netbox_obj.tags) == 0:
                log_message = "[ERROR] VM will not be removed because the 'Proxbox' tag was not found. There is no tag configured.-> {}".format(netbox_name)
                print(log_message)
                log.append(log_message)                


            if delete_vm == True:
                log_message = "[OK] VM successfully removed from Netbox."
                print(log_message)
                log.append(log_message)

                json_vm["result"] = True

        else:
            log_message = '[ERROR] Unexpected error trying to verify if VM exist on Proxmox'
            print(log_message)
            log.append(log_message)

            json_vm["result"] = False

        json_vm["log"] = log
        
        json_vm_all.append(json_vm)
    
    return json_vm_all

    