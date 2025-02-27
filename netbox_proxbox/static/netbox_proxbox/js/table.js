export function populateTable({tableType, jsonMessage, tableDivId, tableId, defaultRowId}) {
    // Populate Table with data from Websocket JSON message
    if (!jsonMessage) {
        return
    }

    // Get whole table div element
    let tableDiv = document.getElementById(tableDivId)

    // Get Virtual Machine Table <table> element
    let table = document.getElementById(tableId)

    if (!table) {
        // If table not found, return.
        return
    } else {
        // If table found, display it.
        tableDiv.style.display = "block"
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
        if (defaultRow) {
            defaultRow.style.display = "none"
        }
        
        
        let vmStatusDataHtml = undefinedHtml

        function createTdElement({table_element, row_element, rowID, field, innerHTML}) {
            let dataId = `${rowID}-${field}-data`

            let data_element = document.getElementById(dataId)
            if (data_element) {
                // If data element found, update it.
                data_element.innerHTML = innerHTML
            } else {
                // If data element not found, create it.
                data_element = document.createElement('td')
                data_element.id = dataId
                data_element.innerHTML = innerHTML

                row_element.appendChild(data_element)
                table_element.appendChild(row)
            }
        }


        // Create Table Row
        let rowID = jsonMessage.data.rowid

        let row = undefined
        if (rowID) {
            row = document.getElementById(rowID)
        }
        
        if (!row) {
            row = document.createElement('tr')
            row.id = rowID
        }

        if (tableType == 'device' && jsonMessage.object == 'device') {
            // Populate Table Row with Table Data parsed from Websocket JSON message
            createTdElement({table_element: table, row_element: row, rowID, field: `status`, innerHTML: jsonMessage.data.sync_status})
            createTdElement({table_element: table, row_element: row, rowID, field: `netbox-id`, innerHTML: jsonMessage.data.netbox_id})
            createTdElement({table_element: table, row_element: row, rowID, field: `node-id`, innerHTML: undefinedHtml})
            createTdElement({table_element: table, row_element: row, rowID, field: `name`, innerHTML: jsonMessage.data.name})
            createTdElement({table_element: table, row_element: row, rowID, field: `manufacturer`, innerHTML: jsonMessage.data.manufacturer})
            createTdElement({table_element: table, row_element: row, rowID, field: `type`, innerHTML: jsonMessage.data.device_type})
            createTdElement({table_element: table, row_element: row, rowID, field: `vm-ct-count`, innerHTML: undefinedHtml})
            createTdElement({table_element: table, row_element: row, rowID, field: `ip-address`, innerHTML: undefinedHtml})
            createTdElement({table_element: table, row_element: row, rowID, field: `role`, innerHTML: jsonMessage.data.role})
            createTdElement({table_element: table, row_element: row, rowID, field: `virtual-cpus`, innerHTML: undefinedHtml})
            createTdElement({table_element: table, row_element: row, rowID, field: `cluster`, innerHTML: jsonMessage.data.cluster})
            createTdElement({table_element: table, row_element: row, rowID, field: `disk-space`, innerHTML: undefinedHtml})
            
            let totalDeviceCountName = 'total-device-count'
            let syncedDeviceCountName = 'synced-device-count'
            let percentageDeviceCompletedName = 'device-sync-percentage-ratio'

            // Total VM Count
            if (jsonMessage.data.completed != undefined && jsonMessage.data.completed == false) {
                let totalVmCount = document.getElementById(totalDeviceCountName)
                if (totalVmCount) {
                    totalVmCount.innerHTML = parseInt(totalVmCount.innerHTML) + 1
                }
            }
            // Synced VM Count
            if (jsonMessage.data.completed != undefined && jsonMessage.data.completed == true && jsonMessage.data.increment_count == 'yes') {
                let currentCompletedCount = document.getElementById(syncedDeviceCountName)
                if (currentCompletedCount) {
                    currentCompletedCount.innerHTML = parseInt(currentCompletedCount.innerHTML) + 1
                }
            }
            // Update Sync Percentage
            let percentageCompleted = document.getElementById(percentageDeviceCompletedName)
            if (percentageCompleted) {
                let totalVmCount = parseInt(document.getElementById(totalDeviceCountName).innerHTML)
                let currentCompletedCount = parseInt(document.getElementById(syncedDeviceCountName).innerHTML)
                let percentage = (currentCompletedCount / totalVmCount) * 100

                percentageCompleted.innerHTML = `${percentage.toFixed(2)}%`
            }
        }
        if (tableType == 'virtual_machine' && jsonMessage.object == 'virtual_machine') {
            // Populate Table Row with Table Data parsed from Websocket JSON message
            createTdElement({table_element: table, row_element: row, rowID, field: `sync_status`, innerHTML: jsonMessage.data.sync_status})
            createTdElement({table_element: table, row_element: row, rowID, field: `netbox-id`, innerHTML: jsonMessage.data.netbox_id})
            createTdElement({table_element: table, row_element: row, rowID, field: `name`, innerHTML: jsonMessage.data.name})
            createTdElement({table_element: table, row_element: row, rowID, field: `status`, innerHTML: jsonMessage.data.status})
            createTdElement({table_element: table, row_element: row, rowID, field: `device`, innerHTML: jsonMessage.data.device})
            createTdElement({table_element: table, row_element: row, rowID, field: `cluster`, innerHTML: jsonMessage.data.cluster})
            createTdElement({table_element: table, row_element: row, rowID, field: `vm-interfaces`, innerHTML: jsonMessage.data.vm_interfaces})
            createTdElement({table_element: table, row_element: row, rowID, field: `role`, innerHTML: jsonMessage.data.role})
            createTdElement({table_element: table, row_element: row, rowID, field: `vcpus`, innerHTML: jsonMessage.data.vcpus})
            createTdElement({table_element: table, row_element: row, rowID, field: `memory`, innerHTML: jsonMessage.data.memory})
            createTdElement({table_element: table, row_element: row, rowID, field: `disk-space`, innerHTML: jsonMessage.data.disk})
            createTdElement({table_element: table, row_element: row, rowID, field: `ip-address`, innerHTML: undefinedHtml})
            
            let totalVmCountName = 'total-vm-count'
            let syncedVmCountName = 'synced-vm-count'
            let percentageVmCompletedName = 'sync-percentage-ratio'

            // Total VM Count
            if (jsonMessage.data.completed != undefined && jsonMessage.data.completed == false) {
                let totalVmCount = document.getElementById(totalVmCountName)
                if (totalVmCount) {
                    totalVmCount.innerHTML = parseInt(totalVmCount.innerHTML) + 1
                }
            }
            // Synced VM Count
            if (jsonMessage.data.completed != undefined && jsonMessage.data.completed == true && jsonMessage.data.increment_count == 'yes') {
                let currentCompletedCount = document.getElementById(syncedVmCountName)
                if (currentCompletedCount) {
                    currentCompletedCount.innerHTML = parseInt(currentCompletedCount.innerHTML) + 1
                }
            }
            // Update Sync Percentage
            let percentageCompleted = document.getElementById(percentageVmCompletedName)
            if (percentageCompleted) {
                let totalVmCount = parseInt(document.getElementById(totalVmCountName).innerHTML)
                let currentCompletedCount = parseInt(document.getElementById(syncedVmCountName).innerHTML)
                let percentage = (currentCompletedCount / totalVmCount) * 100

                percentageCompleted.innerHTML = `${percentage.toFixed(2)}%`
            }
        }

    } catch (error) {
        console.log(`ERROR: ${error}`)
    }
}
