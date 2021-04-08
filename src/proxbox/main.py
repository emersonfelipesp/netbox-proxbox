import os
from os.path import join, dirname
from dotenv import load_dotenv, find_dotenv

# take enviroment variables from .env
load_dotenv(find_dotenv()) 

from proxmoxer import ProxmoxAPI
import pynetbox

from __init__ import netbox as nb, proxmox, PROXMOX, PROXMOX_PORT

import create
import remove

from update import *


# Chama todas as funções de atualização
def vm_full_update(netbox_vm, proxmox_vm):
    status_updated = status(netbox_vm, proxmox_vm)                     # Função compara 'status' e retorna se precisou ser atualizado no Netbox ou não
    custom_fields_updated = custom_fields(netbox_vm, proxmox_vm)           # Função compara 'custom_fields' e retorna se precisou ser atualizado no Netbox ou não
    local_context_updated = local_context_data(netbox_vm, proxmox_vm)     # Função compara 'local_context_data' e retorna se precisou ser atualizado no Netbox ou não
    resources_update = resources(netbox_vm, proxmox_vm)                   # Função compara 'resources' e retorna se precisou ser atualizado no Netbox ou não

    return [custom_fields_updated, status_updated, local_context_updated, resources_update]

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
        netbox_vm = create.virtual_machine(proxmox_vm)

        # VM criada com as informações básicas
        if netbox_vm != None:
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
        vm_updated = vm(px_vm_each)



if __name__ == "__main__":
    print('#\n# COMPARA PROXMOX COM NETBOX\n#')
    update_all()
    print('____________________________________\n')
    print('#\n# COMPARA NETBOX COM PROXMOX\n#')
    remove.virtual_machine()
    
    
