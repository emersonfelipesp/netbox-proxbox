import { createTdElement } from './common.js'

export function populateDevicesTable(jsonMessage) {
    // Populate Nodes Table with data from Websocket JSON message
    if (!jsonMessage) {
        return
    }

    // Get Device Table
    let deviceTable = document.getElementById('device-table-data')
    console.log('Device Table: ', deviceTable)

    let nodesDiv = document.getElementById('device-div')
    nodesDiv.style.display = "block"

    if (!deviceTable) {
        return
    }
    
    let jsonDataName = undefined

    let nodeTableDefaultTd = document.getElementById('device-table-default-td')
    nodeTableDefaultTd.style.display = "none"
    
    // Create Table Row
    let deviceTableRowID = jsonMessage.data.rowid
    let deviceTableRow = document.getElementById(deviceTableRowID)

    if (!deviceTableRow) {
        deviceTableRow = document.createElement('tr')
        deviceTableRow.id = deviceTableRowID
    }

    else {
        // Clear Table Row
        deviceTableRow.innerHTML = ""
    }


    try {
        jsonDataName = jsonMessage.data.name
    } catch (error) {
        console.log(`ERROR: ${error}`)
    }

    let undefinedHtml = `<span class='badge text-bg-grey'><strong></strong>undefined</strong></span>`

    try {
        // Populate Table Row with Table Data parsed from Websocket JSON message
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `status`, jsonMessage.data.sync_status))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `netbox-id`, jsonMessage.data.netbox_id))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `node-id`, undefinedHtml))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `name`, jsonMessage.data.name))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `manufacturer`, jsonMessage.data.manufacturer))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `type`, jsonMessage.data.device_type))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `vm-ct-count`, undefinedHtml))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `ip-address`, undefinedHtml))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `role`, jsonMessage.data.role))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `virtual-cpus`, undefinedHtml))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `cluster`, jsonMessage.data.cluster))
        deviceTableRow.appendChild(createTdElement(jsonMessage.object, jsonDataName, `disk-space`, undefinedHtml))
        
        deviceTable.appendChild(deviceTableRow)

    } catch (error) {
        console.log(`ERROR: ${error}`)
    }
}
