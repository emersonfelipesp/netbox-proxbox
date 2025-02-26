import { createTdElement } from './common.js'

export function populateTable({jsonMessage, tableDivId, tableId, defaultRowId}) {
    // Populate Table with data from Websocket JSON message
    if (!jsonMessage) {
        return
    }

    // Get whole table div element
    let tableDiv = document.getElementById(tableId)

    // Get Virtual Machine Table <table> element
    let table = document.getElementById(tableDivId)

    if (!table) {
        // If table not found, return.
        return
    } else {
        // If table found, display it.
        tableDiv.style.display = "block"
        table.style.display = "block"
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

        let defaultRow = document.getElementById(defaultRowId)
        defaultRow.style.display = "none"
        
        // Create Table Row
        let rowID = jsonMessage.data.rowid

        let row = undefined
        if (rowID) {
            row = document.getElementById(rowID)
        }
        
        if (!row) {
            row = document.createElement('tr')
            row.id = rowID
        } else {
            // Clear Table Row
            row.innerHTML = ""
        }
        
        let vmStatusDataHtml = undefinedHtml

        // Populate Table Row with Table Data parsed from Websocket JSON message
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `status`, jsonMessage.data.sync_status))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `netbox-id`, jsonMessage.data.netbox_id))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `name`, jsonMessage.data.name))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `status`, jsonMessage.data.status))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `device`, jsonMessage.data.device))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `cluster`, jsonMessage.data.cluster))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `vm-interfaces`, jsonMessage.data.vm_interfaces))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `role`, jsonMessage.data.role))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `vcpus`, jsonMessage.data.vcpus))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `memory`, jsonMessage.data.memory))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `disk-space`, jsonMessage.data.disk))
        row.appendChild(createTdElement(jsonMessage.object, jsonDataName, `ip-address`, undefinedHtml))
        
        table.appendChild(row)

        } catch (error) {
        console.log(`ERROR: ${error}`)
    }
}
