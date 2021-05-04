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



# Chama todas as funções de atualização
def vm_full_update(netbox_vm, proxmox_vm):
    changes = {}

    # Função compara 'status' e retorna se precisou ser atualizado no Netbox ou não
    status_updated = updates.virtual_machine.status(netbox_vm, proxmox_vm)
                
    # Função compara 'custom_fields' e retorna se precisou ser atualizado no Netbox ou não
    custom_fields_updated = updates.virtual_machine.custom_fields(netbox_vm, proxmox_vm)

    # Função compara 'local_context_data' e retorna se precisou ser atualizado no Netbox ou não 
    local_context_updated = updates.virtual_machine.local_context_data(netbox_vm, proxmox_vm)

    # Função compara 'resources' e retorna se precisou ser atualizado no Netbox ou não
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
            print('[OK] VM updated. -> {}'.format(proxmox_vm_name))
        else:
            print('[OK] VM already updated. -> {}'.format(proxmox_vm_name))

        # Caso nenhuma das condições funcione, volte True de qualquer maneira, pois a VM existe
        json_vm["result"] = True

    # Se VM não existe, cria-a no Netbox
    elif vm_on_netbox == False:
        print('[OK] VM não existe no Netbox -> {}'.format(proxmox_vm_name))

        # Analisa se VM foi criada com sucesso
        netbox_vm = create.virtual_machine(proxmox_json)

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
        netbox_node = create.node(proxmox_json)

        # Node created
        if netbox_node != None:
            print("[OK] Node created! -> {}".format(proxmox_node_name))

            # Realiza resto da atualização das configurações
            full_update = node_full_update(netbox_node, proxmox_json, proxmox_cluster)  
            json_node["changes"] = full_update

            full_update_list = list(full_update.values())

            # Analisa se atualização das informações ocorreu com sucesso
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
        # Transform comparisons below into functions and pull it together into node_full_update() function
        full_update = node_full_update(netbox_node, proxmox_json, proxmox_cluster)  
        json_node["changes"] = full_update

        full_update_list = list(full_update.values())

        # Analisa se atualização das informações ocorreu com sucesso
        if True in full_update_list:
            print('[OK] NODE updated. -> {}'.format(proxmox_node_name))
        else:
            print('[OK] NODE already updated. -> {}'.format(proxmox_node_name))

        # return True as the node was successfully created.
        json_node["result"] = True
        

        
    return json_node



# Atualiza informações de status, 'custom_fields' e 'local_context'
def all():
    print("[Proxbox - Netbox plugin | Update All]")
    cluster_all = proxmox.cluster.status.get()
    #
    # CLUSTER
    #
    cluster = cluster_all[0]
    #
    # NODES
    #
    print('\n\n\nNODES...')
    nodes_list = []
    proxmox_nodes = cluster_all[1:]

    # Get all NODES from Proxmox
    for px_node_each in proxmox_nodes:
        node_updated = nodes(proxmox_json = px_node_each, proxmox_cluster = cluster)

        nodes_list.append(node_updated)


    #
    # VIRTUAL MACHINES / CONTAINERS
    #
    print('\n\n\nVIRTUAL MACHINES...')
    virtualmachines_list = []

    # Get all VM/CTs from Proxmox
    for px_vm_each in proxmox.cluster.resources.get(type='vm'):     
        vm_updated = virtual_machine(proxmox_json = px_vm_each)

        virtualmachines_list.append(vm_updated)


    #
    # BUILD JSON RESULT
    #
    result = {}
    result["virtualmachines"] = virtualmachines_list
    result["nodes"] = nodes_list

    return result



# Runs if script executed directly
if __name__ == "__main__":
    print('#\n# COMPARA PROXMOX COM NETBOX\n#')
    all()

    print('____________________________________\n')
    print('#\n# COMPARA NETBOX COM PROXMOX\n#')
    remove.all()





    
    
