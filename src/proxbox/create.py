from proxmoxer import ProxmoxAPI
import pynetbox

#from main import vm_full_update

# Cria VM/CT
def virtual_machine(proxmox_vm):
    # Salva VM/CT com informações básicas
    vm_json = {}
    vm_json["name"] = proxmox_vm['name']
    vm_json["status"] = 'active'
    vm_json["cluster"] = 1      # Proxmox cluster
    vm_json["role"] = 12        # Aplicacao
    
    # Cria VM/CT com json criado
    new_vm = nb.virtualization.virtual_machines.create(vm_json)

    if new_vm == True:
        # Busca objeto da VM criada para fazer o resto das atualizações
        netbox_obj = nb.virtualization.virtual_machines.get(name = vm_json["name"])

        if netbox_obj == True: 
            print("[proxbox.create.virtual_machine] VM criada com sucesso")
            return True

        # Analisa se VM foi criada com sucesso com as informações básicas
        elif netbox_obj == False:
            return False

        else:
            print("[proxbox.create.virtual_machine] Falha ao consultar VM recém-criada no Netbox")
            return False  


    elif new_vm == False:
        print("[proxbox.create.virtual_machine] Falha na criação da VM")
        return False

    else:
        print("[proxbox.create.virtual_machine] Falha ao criar VM. Erro Inesperado.")
        return False
        
    # Caso nada funcione, volte erro
    return False


