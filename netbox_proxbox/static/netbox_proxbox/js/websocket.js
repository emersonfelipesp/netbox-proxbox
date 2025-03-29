//import { populateDevicesTable } from "./device.js";
//import { populateVirtualMachinesTable } from "./virtual_machine.js";
import { populateTable } from "./table.js";

function changeSyncButtonState(status) {
    // Change Connection Status Badge to Green
    console.log('changeSyncButtonState', status);
    let buttonMapping = [
        {
            "button": document.getElementById('sync-nodes-button'),
            "form": document.getElementById('sync-nodes-form')
        },
        {
            "button": document.getElementById('sync-virtual-machines-button'),
            "form": document.getElementById('sync-virtual-machines-form')
        },
        {
            "button": document.getElementById('sync-full-update-button'),
            "form": document.getElementById('sync-full-update-form')
        }
    ]

    for (let element of buttonMapping) {
        // Sync Nodes Button

        if (element.button) {
            element.button.className = status == 'connected' ? "btn btn-primary" : "btn btn-danger";
            element.button.disabled = status == 'connected' ? false : true;
            element.button.style.cursor = status == 'connected' ? "pointer" : "not-allowed";
        }

        if (element.form) {
            element.form.style.cursor = status == 'connected' ? "pointer" : "not-allowed";
        }
    }
    console.log('buttonMapping', buttonMapping);
}

// WebSocket Connection Management
export default class WebSocketClient {
    constructor(websocketEndpoint) {
        this.websocketURL = websocketEndpoint
        this.ws = null;
        this.reconnectAttemps = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000; // Start with 2s delay
        this.initialize()
    }

    

    initialize() {
        this.connect();
        // Add event listeners for page visibility changes to handle reconnection
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && 
                (!this.ws || this.ws.readyState === WebSocket.CLOSED)) {
                this.reconnectAttempts = 0;
                this.connect();
            }
        });
    }

    connect() {
        if (this.ws) {
            this.ws.close();
        }

        try {
            // Create WebSocket connection.
            this.ws = new WebSocket(this.websocketURL);

            this.setupEventHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.handleConnectionError({
                type: 'connection_error',
                message: 'Failed to establish WebSocket communication',
                detail: error.message
            })
        }
    }

    setupEventHandlers() {
        this.ws.onopen = this.handleOpen.bind(this);
        this.ws.onmessage = this.handleMessage.bind(this);
        this.ws.onerror = this.handleError.bind(this);
        this.ws.onclose = this.handleClose.bind(this);
    }

    handleOpen(event) {
        console.log('WebSocket connection established.');
        this.reconnectAttempts = 0;

        changeSyncButtonState('connected');
    }

    handleMessage(event) {
        console.log('WebSocket message received:', event.data);
        let jsonMessage;

        changeSyncButtonState('connected');

        try {
            // Parse websocket received message to JSON.
            jsonMessage = JSON.parse(event.data);
        } catch (error) {
            console.warn('Could not parse JSON message:', event.data);
        }

        if (jsonMessage) {
            if (jsonMessage.object == 'virtual_machine') {
                // Populate Virtual Machines Table with data from Websocket JSON message
                populateTable({
                    tableType: 'virtual_machine',
                    jsonMessage: jsonMessage,
                    tableDivId: 'virtual-machines-div',
                    tableId: 'virtual-machine-table-data',
                    defaultRowId: 'virtual-machines-table-default-td'
                });
            } else if (jsonMessage.object == 'device') {
                // Populate Devices Table with data from Websocket JSON message
                populateTable({
                    tableType: 'device',
                    jsonMessage: jsonMessage,
                    tableDivId: 'device-div',
                    tableId: 'device-table-data',
                    defaultRowId:'device-table-default-td'
                });
            }
        }

        this.displayMessage(event.data);
        console.log(event.data);
    }

    handleError(event) {
        console.error('WebSocket error observed:', event.error);
        // this.updateConnectionStatus(false, error);

        changeSyncButtonState('disconnected');
    }

    handleClose(event) {
        console.log(`WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason}`);
        // this.updateConnectionStatus(false);

        // Attemps to reconnect if not a normal closure (unexpected close)
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        }

        changeSyncButtonState('disconnected');
    }

    scheduleReconnect() {
        console.log('Trying to reconnect...');
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts -1); // Exponential backoff
        console.log(`Scheduling reconnect attempt (${this.reconnectAttempts} in ${delay}ms`);

        setTimeout(() => {
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            this.connect();
        }, delay);
    }

    displayMessage(data) {
        // Add WebSockets Messages came from FastAPI backend on GUI at Logs Messages
        const messages = document.getElementById('messages');
        if (!messages) return;

        // Create <li> element and put the websocket data received on it.
        const message = document.createElement('li');
        message.style.lineHeight = '170%';
        message.innerHTML = data;
        messages.appendChild(message);

        const scrollableDiv = document.getElementById('scrollable-div');
        if (scrollableDiv) {
            scrollableDiv.scrollTop = scrollableDiv.scrollHeight
        }
    }

    // Public methods for sending commands to the WebSocket Server
    sendMessage(message) {
        try {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(message);
                return true;
            }
        } catch (error) {
            console.error('Failed to send message over WebSocket:', error);
        }
        return false;
    }

    sendFullUpdate() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send('Full Update');
            return true;
        }
    }

    syncNodes() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {{
            this.ws.send('Sync Nodes');
            return true;
        }}

        console.warn('Cannot Sync Nodes: WebSocket not connected.');
        return false;
    }

    syncVirtualMachines() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send('Sync Virtual Machines');
            return true;
        }

        console.warn('Cannot Sync Virtual Machines: WebSocket not connected.');
        return false;
    }
 }


/*
ws.onmessage = function(event) {
    // Add WebSockets Messages came from FasstAPI backend on GUI
    console.log(event.data)

    let jsonMessage = undefined

    try {
        jsonMessage = JSON.parse(event.data)
    } catch (error) {
        // do nothing
        console.log("Could not parse JSON message.")
    }

    if (jsonMessage) {
        if (jsonMessage.object == "virtual_machine") {
            populateVirtualMachinesTable(jsonMessage)
        } else if (jsonMessage.object == "device") {
            populateDevicesTable(jsonMessage)
        }
    }

    let messages = document.getElementById('messages')
    let message = document.createElement('li')

    message.style.lineHeight = '170%'
    
    message.innerHTML = event.data
    messages.appendChild(message)

    let test = document.getElementById('scrollable-div')
    test.scrollTop = test.scrollHeight

};

ws.addEventListener('error', (event) => {
    console.log("WebSocket error observed: ", event)
})

ws.onerror = function(error) {
    console.log("WebSocket error observed: ", error);
    console.log("error.url", error.url)

    fullUpdateButton = document.getElementById('full-update-button')
    fullUpdateButton.className = "btn btn-red"

    fullUpdateMessage = document.getElementById('full-update-error-message')
    fullUpdateMessage.className = "text-red"

    let errorMessage = `
        <p align=center>
            <strong>WebSocket</strong> communication failed with <strong>${error.currentTarget.url}</strong>
            <br>The most probably cause is <strong>Proxbox Backend not running</strong> properly.<br><br>
            Check if Proxbox is running using following command: <code>systemctl status proxbox</code>.<br>If not, just issue the <code>systemctl start proxbox</code> command..<br>Otherwise, check <a href="https://github.com/netdevopsbr/netbox-proxbox#15-systemd-setup-proxbox-backend" target="_target">Proxbox Documentation</a>.
        </p>`

    let errorButtonFix = `
        <a href="{% url 'plugins:netbox_proxbox:fix-proxbox-backend' %}">
            <button class="btn btn-primary m-2" id="error-button-fix" class="btn btn-primary">
                Let Proxbox try to fix it.
            </button>
        </a><hr>
    `

    let errorDiv = `
    <div>
        ${errorMessage}${errorButtonFix}
    </div>
    `

    fullUpdateMessage.innerHTML = errorDiv
    

    let statusBadgeError = document.getElementById('fastapi-connection-status')
    statusBadgeError.className = "text-bg-red badge p-1"
    statusBadgeError.textContent = "Connection Failed!"

    let statusErrorMessage = document.getElementById('fastapi-connection-error')
    statusErrorMessage.className = "text-bg-red p-2"
    statusErrorMessage.innerHTML = errorMessage


}
*/


/*
function useWebsocket(event) {
    // Send Websocket Message
    ws.send("Hello, World!")
    event.preventDefault()
}

function fullUpdate(event) {
    // Send Websocket Message
    ws.send("Start")
    event.preventDefault()
}

function syncNodes(event) {
    ws.send("Sync Nodes")
    event.preventDefault()
}

function syncVirtualMachines(event) {
    ws.send("Sync Virtual Machines")
    event.preventDefault()
}
*/

//export default new WebSocketClient(websocketEndpoint);