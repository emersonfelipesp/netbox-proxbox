from proxmoxer import ProxmoxAPI
import pynetbox
import requests
import json

from netbox_proxbox import proxbox_api

# Global variables
proxmox = proxbox_api.PROXMOX_SESSION
nb = proxbox_api.NETBOX_SESSION
PROXMOX = proxbox_api.PROXMOX
PROXMOX_PORT = proxbox_api.PROXMOX_PORT
PROXMOX_USER = proxbox_api.PROXMOX_USER
PROXMOX_PASSWORD = proxbox_api.PROXMOX_PASSWORD
PROXMOX_SSL = proxbox_api.PROXMOX_SSL
NETBOX = proxbox_api.NETBOX
NETBOX_TOKEN = proxbox_api.NETBOX_TOKEN

# Altera nome da Netbox caso tenha [] no nome (modo antigo)
# Objetivo: fazer com que o nome no Proxmox e no Netbox sejam iguais
# Atualiza campo "name" no Netbox
def name():
    vms = nb.virtualization.virtual_machines.all()
    
    for vm in vms:
        if '[' in vm.name:
            print('Change VM name: {}'.format(vm.name))
            vm.name = vm.name[6:]
            vm.save()
        else:
            print('Doesn\'t need to change: {}'.format(vm.name))

# Atualiza campo "status" no Netbox baseado no Proxmox
def status(netbox_vm, proxmox_vm):
    # False = status alterado no netbox
    # True  = status alterado no netbox
    status_updated = False

    # [ running, stopped ]
    proxmox_status = proxmox_vm['status']

    # [ offline, active, planned, staged, failed, decommissioning ]
    netbox_status = netbox_vm.status.value

    if proxmox_status == 'running' and netbox_status == 'active' or proxmox_status == 'stopped' and netbox_status == 'offline':
        # Status não atualizado
        status_updated = False
    
    # Change status to active on Netbox if it's offline
    elif proxmox_status == 'stopped' and netbox_status == 'active':
        netbox_vm.status.value = 'offline'
        netbox_vm.save()

        # Status atualizado
        status_updated = True

    # Change status to offline on Netbox if it's active
    elif proxmox_status == 'running' and netbox_status == 'offline':
        netbox_vm.status.value = 'active'
        netbox_vm.save()
        
        # Status atualizado
        status_updated = True

    # Status not expected
    else:
        # Status doesn't need to change
        status_updated = False
    
    return status_updated

# Função que altera campo 'custom_field' da máquina virtual no Netbox
# Utiliza HTTP request e não pynetbox (não consegui através do pynetbox)
def http_update_custom_fields(url, token, vm_id, vm_name, vm_cluster, custom_fields):
        # requisição http do tipo patch (atualização parcial)
        url = '{}/api/virtualization/virtual-machines/{}/'.format(url, vm_id)
        headers = {
            "Authorization": "Token {}".format(token),
            "Content-Type" : "application/json"
        }    
        body = {
            "name": vm_name,
            "cluster": vm_cluster,
            "custom_fields": custom_fields
        }

        r = requests.patch(url, data = json.dumps(body), headers = headers)

        # salva resposta da requisição em dict
        json_dict = json.loads(r.text)

        # Retorna HTTP Status Code
        return r.status_code

# Atualiza campo "custom_fields" no Netbox baseado no Proxmox
def custom_fields(netbox_vm, proxmox_vm):
    # Cria novo custom_field com informações vinda do Proxmox
    custom_fields_update = {'proxmox_id': proxmox_vm['vmid'], 'proxmox_node': proxmox_vm['node'], 'proxmox_type': proxmox_vm['type']}

    # Verifica se valores do Proxmox e Netbox são iguais
    if netbox_vm.custom_fields == custom_fields_update:
        # VM existe no Netbox, mas não precisou ser atualizada
        return False

    # Caso sejam diferentes, pega valores do Proxmox e atualiza no Netbox
    else:
        # Função que atualiza campo 'custom_field' no Netbox
        custom_field_update = http_update_custom_fields(NETBOX, NETBOX_TOKEN, netbox_vm.id, netbox_vm.name, netbox_vm.cluster.id, custom_fields_update)

        # Analisa se resposta HTTP da API obteve sucesso
        if custom_field_update != 200:
            print('[ERROR] Ocorreu um erro na requisição -> {}'.format(netbox_vm.name))
            return False

        else:
            # Caso nada tenha ocorrido, considera VM atualizada.
            return True

    return False

# Atualiza campo "local_context_data" no Netbox baseado no Proxmox
def local_context_data(netbox_vm, proxmox_vm):
    local_context_updated = False

    current_local_context = netbox_vm.local_context_data

    proxmox_values = {}

    # Adiciona e altera valores do Proxmox
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
    
    
    # Verifica se local_context está vazio e então cria os valores iniciais
    if current_local_context == None:
        netbox_vm.local_context_data = {"proxmox" : proxmox_values}
        netbox_vm.save()
        return True

    # Compara valores atuais com dados do Proxmox
    elif current_local_context.get('proxmox') != proxmox_values: 
        # Atualiza valores do 'proxmox'
        current_local_context.update(proxmox = proxmox_values)

        netbox_vm.local_context_data = current_local_context
        netbox_vm.save()   
        return True

    # Se igual
    else:
        # local_context_data já estava atualizado
        return False

    return False

# Atualiza campos "vcpus", "memory", "disk" no Netbox baseado no Proxmox
def resources(netbox_vm, proxmox_vm):
    resources_updated = False

    cr_json = {}
    cr_json["vcpus"] = proxmox_vm["maxcpu"]
    cr_json["memory"] = proxmox_vm["maxmem"]
    cr_json["disk"] = proxmox_vm["maxdisk"]

    memory_mb = cr_json["memory"]
    memory_mb = int(memory_mb / 1000000)       # Convert bytes to megabytes and then convert float to integer

    disk_gb = cr_json["disk"]
    disk_gb = int(disk_gb / 1000000000)       # Convert bytes to gigabytes and then convert float to integer

    cr_json.update(memory = memory_mb)
    cr_json.update(disk = disk_gb)

    # Analisa valores e conforme necessário
    # Compara CPU do Proxmox com Netbox
    if netbox_vm.vcpus == None or netbox_vm.vcpus != cr_json["vcpus"]:
        netbox_vm.vcpus = cr_json["vcpus"]
        netbox_vm.save()

        resources_updated = True

    # Compara Memory do Proxmox com Netbox
    if netbox_vm.memory == None or netbox_vm.memory != cr_json["memory"]:
        netbox_vm.memory = cr_json["memory"]
        netbox_vm.save()

        resources_updated = True

    # Compara Disk do Proxmox com Netbox
    if netbox_vm.disk == None or netbox_vm.disk != cr_json["disk"]:
        netbox_vm.disk = cr_json["disk"]
        netbox_vm.save()

        resources_updated = True
    
    return resources_updated