import os
from os.path import join, dirname
from dotenv import load_dotenv, find_dotenv

# take enviroment variables from .env
load_dotenv(find_dotenv()) 

from proxmoxer import ProxmoxAPI
import pynetbox
import base64
import time
import json

from __init__ import netbox as nb, proxmox, PROXMOX, PROXMOX_PORT

from create import virtual_machine
from update import *

# Altera nome da Netbox caso tenha [] no nome (modo antigo)
# Objetivo: fazer com que o nome no Proxmox e no Netbox sejam iguais
"""
def nb_update_vm_name():
    vms = nb.virtualization.virtual_machines.all()
    
    for vm in vms:
        if '[' in vm.name:
            print('Change VM name: {}'.format(vm.name))
            vm.name = vm.name[6:]
            vm.save()
        else:
            print('Doesn\'t need to change: {}'.format(vm.name)) 
"""

"""
# Função que altera campo 'custom_field' da máquina virtual no Netbox
# Utiliza HTTP request e não pynetbox (não consegui através do pynetbox)
def nb_change_custom_field(url, token, vm_id, vm_name, vm_cluster, custom_fields):
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

"""




"""
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
        custom_field_update = nb_change_custom_field(NETBOX, NETBOX_TOKEN, netbox_vm.id, netbox_vm.name, netbox_vm.cluster.id, custom_fields_update)

        # Analisa se resposta HTTP da API obteve sucesso
        if custom_field_update != 200:
            print('[ERROR] Ocorreu um erro na requisição -> {}'.format(netbox_vm.name))
            return False

        else:
            # Caso nada tenha ocorrido, considera VM atualizada.
            return True

    return False

# Atualiza status da VM no Netbox baseado no Proxmox
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

# Atualiza informações de hardware
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

# Atualiza json de local_context_data da VM/CT
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
"""

# Chama todas as funções de atualização
def vm_full_update(netbox_vm, proxmox_vm):
    status_updated = status(netbox_vm, proxmox_vm)                     # Função compara 'status' e retorna se precisou ser atualizado no Netbox ou não
    custom_fields_updated = custom_fields(netbox_vm, proxmox_vm)           # Função compara 'custom_fields' e retorna se precisou ser atualizado no Netbox ou não
    local_context_updated = local_context_data(netbox_vm, proxmox_vm)     # Função compara 'local_context_data' e retorna se precisou ser atualizado no Netbox ou não
    resources_update = resources(netbox_vm, proxmox_vm)                   # Função compara 'resources' e retorna se precisou ser atualizado no Netbox ou não

    return [custom_fields_updated, status_updated, local_context_updated, resources_update]

"""
# Cria VM/CT
def virtual_machine(proxmox_vm):
    # Salva VM/CT com informações básicas
    vm_json = {}
    vm_json["name"] = proxmox_vm['name']
    vm_json["status"] = 'active'
    vm_json["cluster"] = 1      # Proxmox cluster
    vm_json["role"] = 12        # Aplicacao
    
    # Cria VM/CT com json criado
    nb.virtualization.virtual_machines.create(vm_json)

    # Busca objeto da VM criada para fazer o resto das atualizações
    netbox_vm = nb.virtualization.virtual_machines.get(name = vm_json["name"])
    
    # Analisa se VM foi criada com sucesso com as informações básicas
    if netbox_vm == False:
        return False

    # Realiza resto da atualização das configurações
    full_update = vm_full_update(netbox_vm, proxmox_vm)

    # Analisa se atualização das informações ocorreu com sucesso
    if True in full_update:
        return True
    else:
        return False

    # Caso nada funcione, volte erro
    return False
"""

# Verifica se VM/CT existe Netbox
def is_vm_on_netbox(netbox_vm):
    # Search VM on Netbox by using VM Name gotten from Proxmox
    # VM doesn't exist on Netbox
    if netbox_vm == None:
        vm_on_netbox = False

    # VM already exist on Netbox
    else:
        vm_on_netbox = True

    return vm_on_netbox

# Verifica se VM/CT existe no Proxmox
def is_vm_on_proxmox(netbox_vm):
    # Obtém o json de todas as máquinas virtuais do Proxmox
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    # Netbox name
    netbox_name = netbox_vm.name

    # Busca json local_context do Netbox
    local_context = netbox_vm.local_context_data

    if local_context == None:
        print('[WARNING] "local_context_data" não preenchido -> {}'.format(netbox_name))

    else:
        # chave "proxmox" do "local_context_data"
        proxmox_json = local_context.get("proxmox")
    
        # Se valor nulo, volta erro
        if proxmox_json == None:
            print('[WARNING] local_context_data não possui a chave "proxmox" -> {}'.format(netbox_name))   

        else:
            # Netbox VM/CT ID
            netbox_id = proxmox_json.get("id")

            # Se valor nulo, volta erro
            if netbox_id == None:
                print('[WARNING] chave "proxmox" não possui chave " -> {}'.format(netbox_name))


    # Lista de nomes das VM/CTs do Proxmox
    names = []

    # Lista de IDs das VM/CTs do Proxmox
    vmids = []

    # Compara VM do Netbox com todas as VMs do Proxmox e verifica se existe no Proxmox
    for i in range(len(all_proxmox_vms)):
        name = all_proxmox_vms[i].get("name")
        names.append(name)

        vm_id = all_proxmox_vms[i].get("vmid")
        vmids.append(vm_id)
    

    name_on_px = False
    id_on_px = False

    # Busca VM no Proxmox pelo nome
    try:
        name_index = names.index(netbox_name)      
    except:
        name_on_px = False
    else:
        # ID existe no Proxmox
        name_on_px = True
        
        # Se local_context é nulo, tenta preenchê-lo para obter ID da VM
        if local_context == None:
            local_context_updated = local_context_data(netbox_vm, all_proxmox_vms[name_index])

            if local_context_updated == True:
                local_context = netbox_vm.local_context_data

                if local_context != None:
                    print("[OK] local_context atualizado -> {}".format(netbox_name))
                    proxmox_json = local_context.get("proxmox")
                    netbox_id = proxmox_json.get("id")

                else:
                    print("[ERROR] local_context está vazio -> {}".format(netbox_name))
            else:
                print("[WARNING] local_context não foi atualizado (erro ou já estava atualizado) -> {}".format(netbox_name))


    # Busca VM no Proxmox pelo ID
    try:
        id_index = vmids.index(netbox_id)
    except:
        id_on_px = False
        #print('[ERROR] VM não existe no Proxmox -> {}'.format(netbox_name))
    else:
        # NAME existe no Proxmox
        id_on_px = True


    
    # Analisa se VM existe
    if name_on_px == True:
        if id_on_px == True:
            return True
        else:
            print("[WARNING] NOME existe no Proxmox, mas ID não -> {}".format(netbox_name))
        return True
    
    # Comparação não deu certo, não possíve achar VM no Proxmox
    return False

def netbox_part():
    # Get all VM/CTs from Netbox
    netbox_all_vms = nb.virtualization.virtual_machines.all()
    for nb_vm_each in netbox_all_vms:
        netbox_obj = nb_vm_each
        netbox_name = netbox_obj.name

        # Verifica se VM existe ou não no Proxmox
        vm_on_proxmox = is_vm_on_proxmox(nb_vm_each)

        if vm_on_proxmox == True:
            print('[OK] VM existe em ambos sistemas -> {}'.format(netbox_name))
        
        # Se VM não existe no Proxmox, deleta a VM no Netbox
        elif vm_on_proxmox == False:
            print("[OK] VM existe no Netbox, mas não no Proxmox. Deletar a VM! -> {}".format(netbox_name))
            delete_vm = netbox_obj.delete()

            if delete_vm == True:
                print("[OK] VM removida do Netbox com sucesso")

        else:
            print('[ERROR] Erro inesperado ao verificar se VM existe no Proxmox')




# Faz todas as verificações necessárias para que a VM/CT exista no Netbox
def vm(proxmox_vm):
    proxmox_vm_name = proxmox_vm['name']
 
    #
    # NETBOX PART
    #
    # Busca objeto no Netbox pelo nome vindo do Proxmox
    netbox_vm = nb.virtualization.virtual_machines.get(name = proxmox_vm_name)

    # Analisa existência do registro da VM no Netbox
    # Se VM/CT já existe no Proxmox, realiza atualização das informações, se necessário
    vm_on_netbox = is_vm_on_netbox(netbox_vm)


    
    #print('vm_on_netbox', vm_on_netbox)



    if vm_on_netbox == True:
        # Atualiza informações no Netbox
        full_update = vm_full_update(netbox_vm, proxmox_vm)  

        # Analisa se a VM precisou ser atualizada no Netbox
        if True in full_update:
            print('[OK] VM atualizada -> {}'.format(proxmox_vm_name))
            
            # VM atualizada
            return True
            
        else:
            print('[OK] VM já estava atualizada -> {}'.format(proxmox_vm_name))

            # VM já atualizada
            return True

        # Caso nenhuma das condições funcione, volte True de qualquer maneira, pois a VM existe
        return True

    # Se VM não existe, cria-a no Netbox
    elif vm_on_netbox == False:
        print('[OK] VM não existe no Netbox -> {}'.format(proxmox_vm_name))

        # Analisa se VM foi criada com sucesso
        vm_created = virtual_machine(proxmox_vm)

        # VM criada com as informações básicas
        if vm_created == True:
                
            # Realiza resto da atualização das configurações
            full_update = vm_full_update(netbox_vm, proxmox_vm)

            # Analisa se atualização das informações ocorreu com sucesso
            if True in full_update:
                print('[OK] VM criada com sucesso -> {}'.format(proxmox_vm_name))

                # VM atualizada completamente
                return True

            else:
                return False
                print('[OK] VM criada, mas atualização completa ocorreu erro -> {}'.format(proxmox_vm_name))

                # VM criada com informações básicas
                return True
        
        else:
            print('[ERROR] Erro na criação da VM -> {}'.format(proxmox_vm_name))

            # VM não criada
            return False

    else:
        print("[ERROR] Erro inesperado -> {}".format(proxmox_vm_name))

        # Erro inesperado
        return False
    
   

    
# Atualiza informações de status, 'custom_fields' e 'local_context'
def update_all():
    # Get all VM/CTs from Proxmox
    for px_vm_each in proxmox.cluster.resources.get(type='vm'):
        #print('\n\n')
        #print('\n\nMÁQUINA VIRTUAL:')        
        vm_updated = vm(px_vm_each)



if __name__ == "__main__":
    print('#\n# COMPARA PROXMOX COM NETBOX\n#')
    update_all()
    print('____________________________________\n')
    print('#\n# COMPARA NETBOX COM PROXMOX\n#')
    netbox_part()
    
    
