import { createTdElement } from './common.js'

export function populateVirtualMachinesTable(jsonMessage) {
    // Populate Virtual Machines Table with data from Websocket JSON message
    if (!jsonMessage) {
        return
    }

    // Get Virtual Machine Table
    let virtualMachineTable = document.getElementById('virtual-machine-table-data')

    let virtualMachinesDiv = document.getElementById('virtual-machines-div')
    virtualMachinesDiv.style.display = "block"

    if (!virtualMachineTable) {
        return
    }

    let jsonDataName = undefined

    try {
        jsonDataName = jsonMessage.data.name
    } catch (error) {
        console.log(`ERROR: ${error}`)
    }

    // JSON message is parsed. Now, let's check if it's a Virtual Machine message.
    try {
        let undefinedHtml = `<span class='badge text-bg-grey' title='Proxmox VM ID'><strong></strong>undefined</strong></span>`

        virtualMachinesDiv.style.display = "block"

        let vmTableDefaultTd = document.getElementById('virtual-machines-table-default-td')
        vmTableDefaultTd.style.display = "none"
        
        // Create Table Row
        let vmTableRowID = jsonMessage.data.rowid
        let vmTableRow = document.getElementById(vmTableRowID)
        
        if (!vmTableRow) {
            vmTableRow = document.createElement('tr')
            vmTableRow.id = vmTableRowID
        } else {
            // Clear Table Row
            vmTableRow.innerHTML = ""
        }
        

        let vmStatusDataHtml = undefinedHtml

        // Populate Table Row with Table Data parsed from Websocket JSON message
        vmTableRow.appendChild(createTdElement(type=jsonMessage.object, name=jsonDataName, field=`status`, jsonMessage.data.sync_status))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `netbox-id`, jsonMessage.data.netbox_id))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `name`, jsonMessage.data.name))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `status`, jsonMessage.data.status))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `device`, jsonMessage.data.device))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `cluster`, jsonMessage.data.cluster))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `vm-interfaces`, jsonMessage.data.vm_interfaces))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `role`, jsonMessage.data.role))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `vcpus`, jsonMessage.data.vcpus))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `memory`, jsonMessage.data.memory))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `disk-space`, jsonMessage.data.disk))
        vmTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `ip-address`, undefinedHtml))
        
        virtualMachineTable.appendChild(vmTableRow)

        } catch (error) {
        console.log(`ERROR: ${error}`)
    }
}
