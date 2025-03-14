async function poll(objectType) {
    const data = []
    while (true) {
        // Fetch the data from the FastAPI endpoint and save it to a variable
        try {
            if (objectType === 'virtual-machine' || objectType === 'device' || objectType === 'full-update') {
                const response = await fetch(`/plugins/proxbox/websocket/${objectType}?json_response=true`)
                console.log('response', response)
                data = await response.json()
            }
        } catch (error) {
            console.error('Error:', error);
            break;
        }

        if (data.length == 0) {
            break;
        }
        
        if (data.length > 0) {
            for (const jsonMessage of data) {
                if (jsonMessage.object == 'virtual_machine') {
                    // Populate Virtual Machines Table with data from Websocket JSON message
                    populateTable({
                        tableType: 'virtual_machine',
                        jsonMessage: jsonMessage,
                        tableDivId: 'virtual-machines-div',
                        tableId: 'virtual-machine-table-data',
                        defaultRowId: 'virtual-machines-table-default-td'
                    });

                    if (jsonMessage.end == true) {
                        break;
                    }

                } else if (jsonMessage.object == 'device') {
                    // Populate Devices Table with data from Websocket JSON message
                    populateTable({
                        tableType: 'device',
                        jsonMessage: jsonMessage,
                        tableDivId: 'device-div',
                        tableId: 'device-table-data',
                        defaultRowId:'device-table-default-td'
                    });

                    if (jsonMessage.end == true) {
                        break;
                    }
                }
            }
        }
    }
}

export { poll }
