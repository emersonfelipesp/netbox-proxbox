import { populateTable } from "./table.js";

function updateSyncButtons(connected) {
    for (const button of document.querySelectorAll("[data-sync-url][data-sync-kind]")) {
        button.classList.toggle("btn-primary", connected);
        button.classList.toggle("btn-danger", !connected);
    }
}

export default class WebSocketClient {
    constructor(websocketEndpoint, apiKey = null) {
        this.websocketURL = websocketEndpoint;
        this.apiKey = apiKey;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.syncEndListeners = new Set();
        this.connect();
    }

    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    connect() {
        if (this.ws) {
            this.ws.close();
        }

        try {
            this.ws = new WebSocket(this.websocketURL);
            this.ws.onopen = () => {
                this.reconnectAttempts = 0;
                if (this.apiKey) {
                    this.ws.send(JSON.stringify({ api_key: this.apiKey }));
                }
                updateSyncButtons(true);
            };
            this.ws.onmessage = (event) => this.handleMessage(event);
            this.ws.onerror = () => updateSyncButtons(false);
            this.ws.onclose = (event) => this.handleClose(event);
        } catch (error) {
            console.error("Failed to create WebSocket connection:", error);
            updateSyncButtons(false);
        }
    }

    handleMessage(event) {
        let jsonMessage;
        try {
            jsonMessage = JSON.parse(event.data);
        } catch (error) {
            this.displayMessage(event.data);
            return;
        }

        if (jsonMessage.object === "virtual_machine") {
            populateTable({
                tableType: "virtual_machine",
                jsonMessage,
                tableDivId: "virtual-machines-div",
                tableId: "virtual-machine-table-data",
                defaultRowId: "virtual-machines-table-default-td",
            });
        } else if (jsonMessage.object === "device") {
            populateTable({
                tableType: "device",
                jsonMessage,
                tableDivId: "device-div",
                tableId: "device-table-data",
                defaultRowId: "device-table-default-td",
            });
        }

        if (jsonMessage.end === true) {
            this.notifySyncEnd(jsonMessage.object);
        }

        this.displayMessage(event.data);
    }

    handleClose(event) {
        updateSyncButtons(false);
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts += 1;
            const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
            setTimeout(() => this.connect(), delay);
        }
    }

    displayMessage(data) {
        const messages = document.getElementById("messages");
        if (!messages) {
            return;
        }

        const message = document.createElement("li");
        message.style.lineHeight = "170%";
        message.textContent = data;
        messages.appendChild(message);

        const scrollableDiv = document.getElementById("scrollable-div");
        if (scrollableDiv) {
            scrollableDiv.scrollTop = scrollableDiv.scrollHeight;
        }
    }

    send(payload) {
        if (this.isConnected()) {
            this.ws.send(payload);
        }
    }

    onSyncEnd(listener) {
        this.syncEndListeners.add(listener);
        return () => this.syncEndListeners.delete(listener);
    }

    notifySyncEnd(syncObject) {
        for (const listener of this.syncEndListeners) {
            listener(syncObject);
        }
    }

    syncNodes() {
        this.send("Sync Nodes");
    }

    syncVirtualMachines() {
        this.send("Sync Virtual Machines");
    }

    sendFullUpdate() {
        this.send("Full Update Sync");
    }
}
