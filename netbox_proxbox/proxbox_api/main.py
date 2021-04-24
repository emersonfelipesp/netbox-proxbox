from proxmoxer import ProxmoxAPI
import pynetbox

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

# Chama todas as funções de atualização
def vm_full_update(netbox_vm, proxmox_vm):
    changes = {}

    status_updated = proxbox_api.updates.status(netbox_vm, proxmox_vm)                     # Função compara 'status' e retorna se precisou ser atualizado no Netbox ou não
    custom_fields_updated = proxbox_api.updates.custom_fields(netbox_vm, proxmox_vm)           # Função compara 'custom_fields' e retorna se precisou ser atualizado no Netbox ou não
    local_context_updated = proxbox_api.updates.local_context_data(netbox_vm, proxmox_vm)     # Função compara 'local_context_data' e retorna se precisou ser atualizado no Netbox ou não
    resources_update = proxbox_api.updates.resources(netbox_vm, proxmox_vm)                   # Função compara 'resources' e retorna se precisou ser atualizado no Netbox ou não

    #changes = [custom_fields_updated, status_updated, local_context_updated, resources_update]
    changes = {
        "status" : status_updated,
        "custom_fields" : custom_fields_updated,
        "local_context" : local_context_updated,
        "resources" : resources_update  
    }

    return changes

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

def search_by_proxmox_id(proxmox_id):
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    for px_vm in all_proxmox_vms:
        px_id = px_vm.get("vmid")
        
        if px_id == proxmox_id:
            proxmox_vm = px_vm
            return proxmox_vm
    
    # Caso JSON não encontrado, volta nulo.
    return None

def search_by_proxmox_name(proxmox_name):
    all_proxmox_vms = proxmox.cluster.resources.get(type='vm')

    for px_vm in all_proxmox_vms:
        px_name = px_vm.get("name")

        if proxmox_name == px_name:
            proxmox_vm = px_vm
            return proxmox_vm

    # Caso JSON não encontrado, volta nulo.
    return None

def search_by_id(id):
    # Salva objeto da VM vindo do Netbox
    netbox_obj = nb.virtualization.virtual_machines.get(id)

    proxmox_name = netbox_obj.name

    # Busca Proxmox ID do Netbox
    local_context = netbox_obj.local_context_data
    if local_context != None:
        proxmox_json = local_context.get("proxmox")

        if proxmox_json != None:
            proxmox_id = proxmox_json.get("id")
            
            if proxmox_id != None:
                return proxmox_id

            #else:
            #    print("[ERROR] Não foi possível obter ID da VM do Proxmox no Netbox -> {}".format(proxmox_name))

    # Retorna NOME caso ID não seja encontrado
    return proxmox_name

# Faz todas as verificações necessárias para que a VM/CT exista no Netbox
def virtual_machine(**kwargs):
    # JSON containing the result of the VM changes
    json_vm = {}

    # args:
    # proxmox_json
    # id
    # proxmox_id
    # name
    #
    # Salva argumentos e valida o tipo
    #
    # Salva argumento
    proxmox_id = kwargs.get('proxmox_id')

    # Valida o tipo
    if proxmox_id != None:
        proxmox_id_type = type(proxmox_id)
        if 'int' not in str(proxmox_id_type):
            print('[ERROR] "proxmox_id" MUST be integer. Type used: {}'.format(proxmox_id_type))
            #return False
            json_vm["result"] = False

    # Salva argumento
    id = kwargs.get('id')

    # Valida o tipo
    if id != None:
        id_type = type(id)
        if 'int' not in str(id_type):
            print('[ERROR] "id" MUST be integer. Type used: {}'.format(id_type))
            #return False
            json_vm["result"] = False
            
    
    # Salva argumento
    name = kwargs.get('name')

    # Valida o tipo
    if name != None:
        name_type = type(name)
        if 'str' not in str(name_type):
            print('[ERROR] "name" MUST be string. Type used: {}'.format(name_type))
            #return False
            json_vm["result"] = False

    # Salva argumento
    proxmox_json = kwargs.get('proxmox_json')

    proxmox_vm_name = None

    # Decide se utilizará proxmox_json ou outros argumentos passados (id, proxmox_id e proxmox_name)
    if proxmox_json != None:
        proxmox_vm_name = proxmox_json['name']
        json_vm["name"] = proxmox_json['name']

    # Se 'proxmox_json' não foi passado como argumento, usa os outros argumentos
    else:    
        #
        # Com os argumentos passado na função, busca pelo json da VM no Proxmox
        # Prioridade de busca: 1° = id | 2° = proxmox_id | 3° = proxmox_name
        #
        # Busca JSON da VM do Proxmox pelo argumento "id"
        if id != None:
            # Search result returns Proxmox ID or Proxmox Name, if ID doesn't exist
            search_result = search_by_id(id)

            # Busca tipo do resultado. 'int' = Proxmox ID | 'str' = Proxmox Name
            search_result_type = type(search_result)

            # Busca pelo Proxmox ID
            if 'int' in str(search_result_type):
                proxmox_json = search_by_proxmox_id(search_result)

                # Analisa retorno da busca e retorna erro, caso valor nulo
                if proxmox_json == None:
                    print("[ERROR] Erro ao buscar VM no Proxmox utilizando argumento 'proxmox_id'")
                    #return False
                    json_vm["result"] = False            

                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

            # Busca pelo Proxmox NAME
            elif 'str' in str(search_result_type):
                proxmox_json = search_by_proxmox_name(search_result)

                # Analisa retorno da busca e retorna erro, caso valor nulo
                if proxmox_json == None:
                    print("[ERROR] Erro ao buscar VM no Proxmox utilizando argumento 'proxmox_id'")
                    #return False
                    json_vm["result"] = False
                
                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

        else:
            # Busca JSON do Proxmox pelo argumento 'proxmox_id'
            if proxmox_id != None:
                proxmox_json = search_by_proxmox_id(proxmox_id)

                # Analisa retorno da busca e retorna erro, caso valor nulo
                if proxmox_json == None:
                    print("[ERROR] Erro ao buscar VM no Proxmox utilizando argumento 'proxmox_id'")
                    #return False
                    json_vm["result"] = False      

                proxmox_vm_name = proxmox_json['name']
                json_vm["name"] = proxmox_json['name']

            else:
                # Busca JSON do Proxmox pelo argumento 'name''
                if name != None:
                    proxmox_json = search_by_proxmox_name(name)

                    # Analisa retorno da busca e retorna erro, caso valor nulo
                    if proxmox_json == None:
                        print("[ERROR] Erro ao buscar VM no Proxmox utilizando argumento 'proxmox_id'")
                        #return False
                        json_vm["result"] = False
                    
                    proxmox_vm_name = proxmox_json['name']
                    json_vm["name"] = proxmox_json['name']

    if proxmox_vm_name == None:
        return False

    # Busca objeto no Netbox pelo nome vindo do Proxmox
    netbox_vm = nb.virtualization.virtual_machines.get(name = proxmox_vm_name)

    # Analisa existência do registro da VM no Netbox
    # Se VM/CT já existe no Proxmox, realiza atualização das informações, se necessário
    vm_on_netbox = is_vm_on_netbox(netbox_vm)

    if vm_on_netbox == True:
        # Atualiza informações no Netbox
        full_update = vm_full_update(netbox_vm, proxmox_json)  
        json_vm["changes"] = full_update

        full_update_list = list(full_update.values())

        # Analisa se a VM precisou ser atualizada no Netbox
        if True in full_update_list:
            print('[OK] VM atualizada -> {}'.format(proxmox_vm_name))
            
            # VM atualizada
            #return True
            json_vm["result"] = True
        else:
            print('[OK] VM já estava atualizada -> {}'.format(proxmox_vm_name))

            # VM já atualizada
            #return True
            json_vm["result"] = True

        # Caso nenhuma das condições funcione, volte True de qualquer maneira, pois a VM existe
        #return True
        json_vm["result"] = True

    # Se VM não existe, cria-a no Netbox
    elif vm_on_netbox == False:
        print('[OK] VM não existe no Netbox -> {}'.format(proxmox_vm_name))

        # Analisa se VM foi criada com sucesso
        netbox_vm = proxbox_api.create.virtual_machine(proxmox_json)

        # VM criada com as informações básicas
        if netbox_vm != None:
            # Realiza resto da atualização das configurações
            full_update = vm_full_update(netbox_vm, proxmox_json)  
            json_vm["changes"] = full_update

            full_update_list = list(full_update.values())

            # Analisa se atualização das informações ocorreu com sucesso
            if True in full_update_list:
                print('[OK] VM criada com sucesso -> {}'.format(proxmox_vm_name))

                # VM atualizada completamente
                #return True
                json_vm["result"] = True

            else:
                print('[OK] VM criada, mas atualização completa ocorreu erro -> {}'.format(proxmox_vm_name))

                # VM criada com informações básicas
                #return True
                json_vm["result"] = True
        
        else:
            print('[ERROR] Erro na criação da VM -> {}'.format(proxmox_vm_name))

            # VM não criada
            #return False
            json_vm["result"] = False

    else:
        print("[ERROR] Erro inesperado -> {}".format(proxmox_vm_name))

        # Erro inesperado
        #return False
        json_vm["result"] = False

    return json_vm

# Atualiza informações de status, 'custom_fields' e 'local_context'
def all():
    results = []

    # Get all VM/CTs from Proxmox
    for px_vm_each in proxmox.cluster.resources.get(type='vm'):     
        vm_updated = virtual_machine(proxmox_json = px_vm_each)

        results.append(vm_updated)

    return results

# Runs if script executed directly
if __name__ == "__main__":
    print('#\n# COMPARA PROXMOX COM NETBOX\n#')
    all()

    print('____________________________________\n')
    print('#\n# COMPARA NETBOX COM PROXMOX\n#')
    proxbox_api.remove.all()





    
    
