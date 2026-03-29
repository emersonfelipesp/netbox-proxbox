import { populateTable } from "./table.js";

export async function poll(objectType, callbacks = {}) {
    const { onComplete = () => {}, onError = () => {} } = callbacks;

    while (true) {
        let data = [];
        try {
            const response = await fetch(`/plugins/proxbox/websocket/${objectType}?json_response=true`, {
                headers: { Accept: "application/json" },
            });
            data = await response.json();
        } catch (error) {
            console.error("Polling failed:", error);
            onError(error);
            break;
        }

        if (!Array.isArray(data) || data.length === 0) {
            onComplete();
            break;
        }

        for (const jsonMessage of data) {
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
        }

        await new Promise((resolve) => setTimeout(resolve, 1000));
    }
}
