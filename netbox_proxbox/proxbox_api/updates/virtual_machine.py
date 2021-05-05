import requests
import json

# PLUGIN_CONFIG variables
from ..plugins_config import (
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

from .. import (
    create,
)




# Update "status" field on Netbox Virtual Machine based on Proxmox information
def status(netbox_vm, proxmox_vm):
    # False = status not changed on Netbox
    # True  = status changed on Netbox
    status_updated = False

    # [ running, stopped ]
    proxmox_status = proxmox_vm['status']

    # [ offline, active, planned, staged, failed, decommissioning ]
    netbox_status = netbox_vm.status.value

    if (proxmox_status == 'running' and netbox_status == 'active') or (proxmox_status == 'stopped' and netbox_status == 'offline'):
        # Status not updated
        status_updated = False
    
    # Change status to active on Netbox if it's offline
    elif proxmox_status == 'stopped' and netbox_status == 'active':
        netbox_vm.status.value = 'offline'
        netbox_vm.save()

        # Status updated
        status_updated = True

    # Change status to offline on Netbox if it's active
    elif proxmox_status == 'running' and netbox_status == 'offline':
        netbox_vm.status.value = 'active'
        netbox_vm.save()
        
        # Status updated
        status_updated = True

    # Status not expected
    else:
        # Status doesn't need to change
        status_updated = False
    
    return status_updated



def site(**kwargs):
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)
    

# Function that modifies 'custom_field' of Netbox Virtual Machine.
# It uses HTTP Request and not Pynetbox (as I was not able to).
def http_update_custom_fields(**kwargs):
    # Saves kwargs variables
    domain_with_http = kwargs.get('domain_with_http')
    token = kwargs.get('token')
    vm_id = kwargs.get('vm_id', 0)
    vm_name = kwargs.get('vm_name')
    vm_cluster = kwargs.get('vm_cluster')
    custom_fields = kwargs.get('custom_fields')

    #
    # HTTP PATCH Request (partially update)
    #
    # URL 
    url = '{}/api/virtualization/virtual-machines/{}/'.format(domain_with_http, vm_id)
    
    # HTTP Request Headers
    headers = {
        "Authorization": "Token {}".format(token),
        "Content-Type" : "application/json"
    }    
    
    # HTTP Request Body
    body = {
        "name": vm_name,
        "cluster": vm_cluster,
        "custom_fields": custom_fields
    }

    # Makes the request and saves it to var
    r = requests.patch(url, data = json.dumps(body), headers = headers)

    # Return HTTP Status Code
    return r.status_code



# Update 'custom_fields' field on Netbox Virtual Machine based on Proxbox
def custom_fields(netbox_vm, proxmox_vm):
    # Create the new 'custom_field' with info from Proxmox
    custom_fields_update = {}

    # Check if there is 'custom_field' configured on Netbox
    if len(netbox_vm.custom_fields) == 0:
        print("[ERROR] There's no 'Custom Fields' registered by the Netbox Plugin user")

    # If any 'custom_field' configured, get it and update, if necessary.
    elif len(netbox_vm.custom_fields) > 0:

        # Get current configured custom_fields
        custom_fields_names = list(netbox_vm.custom_fields.keys())

        #
        # VERIFY IF CUSTOM_FIELDS EXISTS AND THEN UPDATE INFORMATION, IF NECESSARY.
        #
        # Custom Field 'proxmox_id'
        if 'proxmox_id' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_id") != proxmox_vm['vmid']:
                custom_fields_update["proxmox_id"] = proxmox_vm['vmid']
        else:
            print("[ERROR] 'proxmox_id' custom field not registered yet or configured incorrectly]")

        # Custom Field 'proxmox_node'
        if 'proxmox_node' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_node") != proxmox_vm['node']:
                custom_fields_update["proxmox_node"] = proxmox_vm['node']
        else:
            print("[ERROR] 'proxmox_node' custom field not registered yet or configured incorrectly")

        # Custom Field 'proxmox_type'
        if 'proxmox_type' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_type") != proxmox_vm['type']:
                custom_fields_update["proxmox_type"] = proxmox_vm['type']
        else:
            print("[ERROR] 'proxmox_type' custom field not registered yet or configured incorrectly")



        # Only updates information if changes found
        if len(custom_fields_update) > 0:

            # As pynetbox does not have a way to update custom_fields, use API HTTP request
            custom_field_updated = http_update_custom_fields(
                domain_with_http = NETBOX,
                token = NETBOX_TOKEN,
                vm_id = netbox_vm.id,
                vm_name = netbox_vm.name,
                vm_cluster = netbox_vm.cluster.id,
                custom_fields = custom_fields_update
            )

            # Verify HTTP reply CODE
            if custom_field_updated != 200:
                print("[ERROR] Some error occured trying to update 'custom_fields' through HTTP Request. HTTP Code: {}. -> {}".format(custom_field_updated, netbox_vm.name))
                return False

            else:
                # If none error occured, considers VM updated.
                return True

        return False





# Update 'local_context_data' field on Netbox Virtual Machine based on Proxbox
def local_context_data(netbox_vm, proxmox_vm):
    current_local_context = netbox_vm.local_context_data

    proxmox_values = {}

    # Add and change values from Proxmox
    proxmox_values["name"] = proxmox_vm["name"]
    proxmox_values["url"] = "https://{}:{}".format(PROXMOX, PROXMOX_PORT)      # URL
    proxmox_values["id"] = proxmox_vm["vmid"]      # VM ID
    proxmox_values["node"] = proxmox_vm["node"]
    proxmox_values["type"] = proxmox_vm["type"]

    maxmem = int(int(proxmox_vm["maxmem"]) / 1000000000)        # Convert bytes to gigabytes
    proxmox_values["memory"] = "{} {}".format(maxmem, 'GB')     # Add the 'GB' unit of measurement   

    maxdisk = int(int(proxmox_vm["maxdisk"]) / 1000000000)       # Convert bytes to gigabytes
    proxmox_values["disk"] = "{} {}".format(maxdisk, 'GB')      # Add the 'GB' unit of measurement 

    proxmox_values["vcpu"] = proxmox_vm["maxcpu"]       # Add the 'GB' unit of measurement
    
    
    # Verify if 'local_context' is empty and if true, creates initial values.
    if current_local_context == None:
        netbox_vm.local_context_data = {"proxmox" : proxmox_values}
        netbox_vm.save()
        return True

    # Compare current Netbox values with Porxmox values
    elif current_local_context.get('proxmox') != proxmox_values: 
        # Update 'proxmox' key on 'local_context_data'
        current_local_context.update(proxmox = proxmox_values)

        netbox_vm.local_context_data = current_local_context
        netbox_vm.save()   
        return True

    # If 'local_context_data' already updated
    else:
        return False

    return False







# Updates following fields based on Proxmox: "vcpus", "memory", "disk", if necessary.
def resources(netbox_vm, proxmox_vm):
    # Save values from Proxmox
    vcpus = float(proxmox_vm["maxcpu"])
    
    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm["maxmem"]
    memory_Mb = int(memory_Mb / 1000000)       

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm["maxdisk"]
    disk_Gb = int(disk_Gb / 1000000000)       

    # JSON with new resources info
    new_resources_json = {}

    
    
    # Compare VCPU
    if netbox_vm.vcpus != None:
        # Convert Netbox VCPUs to float, since it is coming as string from Netbox
        netbox_vm.vcpus = float(netbox_vm.vcpus)

        if netbox_vm.vcpus != vcpus:
            new_resources_json["vcpus"] = vcpus

    elif netbox_vm.vcpus == None:
        new_resources_json["vcpus"] = vcpus



    # Compare Memory
    if netbox_vm.memory != None:
        if netbox_vm.memory != memory_Mb:
            new_resources_json["memory"] = memory_Mb

    elif netbox_vm.memory == None:
        new_resources_json["memory"] = memory_Mb



    # Compare Disk
    if netbox_vm.disk != None:
        if netbox_vm.disk != disk_Gb:
            new_resources_json["disk"] = disk_Gb

    elif netbox_vm.disk == None:
        new_resources_json["disk"] = disk_Gb
    
    

    # If new information found, save it to Netbox object.
    if len(new_resources_json) > 0:
        resources_updated = netbox_vm.update(new_resources_json)

        if resources_updated == True:
            return True
        else:
            return False

