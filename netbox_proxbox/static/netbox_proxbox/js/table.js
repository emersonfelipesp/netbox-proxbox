function normalizeText(value) {
    return value === undefined || value === null ? "" : String(value)
}

function createUndefinedBadge() {
    const badge = document.createElement("span")
    badge.className = "badge text-bg-grey"
    badge.title = "Proxmox VM ID"

    const label = document.createElement("strong")
    label.textContent = "undefined"
    badge.appendChild(label)
    return badge
}

function replaceCellContents(cell, value, showUndefinedBadge) {
    if (showUndefinedBadge) {
        cell.replaceChildren(createUndefinedBadge())
        return
    }
    cell.textContent = normalizeText(value)
}

function updateCounter(counterId) {
    const counter = document.getElementById(counterId)
    if (!counter) {
        return
    }
    counter.textContent = String(Number.parseInt(counter.textContent, 10) + 1)
}

function updatePercentage(totalId, completedId, percentageId) {
    const total = document.getElementById(totalId)
    const completed = document.getElementById(completedId)
    const percentage = document.getElementById(percentageId)
    if (!total || !completed || !percentage) {
        return
    }
    const totalCount = Number.parseInt(total.textContent, 10)
    const completedCount = Number.parseInt(completed.textContent, 10)
    const ratio = totalCount > 0 ? (completedCount / totalCount) * 100 : 0
    percentage.textContent = `${ratio.toFixed(2)}%`
}

export function populateTable({tableType, jsonMessage, tableDivId, tableId, defaultRowId}) {
    if (!jsonMessage || !jsonMessage.data) {
        return
    }

    const tableDiv = document.getElementById(tableDivId)
    const table = document.getElementById(tableId)
    if (!table || !tableDiv) {
        return
    }
    tableDiv.style.display = "block"

    try {
        const defaultRow = document.getElementById(defaultRowId)
        if (defaultRow) {
            defaultRow.style.display = "none"
        }

        const rowId = normalizeText(jsonMessage.data.rowid)
        if (!rowId) {
            return
        }
        let row = document.getElementById(rowId)
        if (!row) {
            row = document.createElement("tr")
            row.id = rowId
        }

        function createTdElement({field, value, showUndefinedBadge = false}) {
            const dataId = `${rowId}-${field}-data`
            let dataElement = document.getElementById(dataId)
            if (!dataElement) {
                dataElement = document.createElement("td")
                dataElement.id = dataId
                row.appendChild(dataElement)
                table.appendChild(row)
            }
            replaceCellContents(dataElement, value, showUndefinedBadge)
        }

        if (tableType === "device" && jsonMessage.object === "device") {
            createTdElement({field: "status", value: jsonMessage.data.sync_status})
            createTdElement({field: "netbox-id", value: jsonMessage.data.netbox_id})
            createTdElement({field: "node-id", showUndefinedBadge: true})
            createTdElement({field: "name", value: jsonMessage.data.name})
            createTdElement({field: "manufacturer", value: jsonMessage.data.manufacturer})
            createTdElement({field: "type", value: jsonMessage.data.device_type})
            createTdElement({field: "vm-ct-count", showUndefinedBadge: true})
            createTdElement({field: "ip-address", showUndefinedBadge: true})
            createTdElement({field: "role", value: jsonMessage.data.role})
            createTdElement({field: "virtual-cpus", showUndefinedBadge: true})
            createTdElement({field: "cluster", value: jsonMessage.data.cluster})
            createTdElement({field: "disk-space", showUndefinedBadge: true})

            if (jsonMessage.data.completed === false) {
                updateCounter("total-device-count")
            }
            if (jsonMessage.data.completed === true && jsonMessage.data.increment_count === "yes") {
                updateCounter("synced-device-count")
            }
            updatePercentage(
                "total-device-count",
                "synced-device-count",
                "device-sync-percentage-ratio",
            )
        }

        if (tableType === "virtual_machine" && jsonMessage.object === "virtual_machine") {
            createTdElement({field: "sync_status", value: jsonMessage.data.sync_status})
            createTdElement({field: "netbox-id", value: jsonMessage.data.netbox_id})
            createTdElement({field: "name", value: jsonMessage.data.name})
            createTdElement({field: "status", value: jsonMessage.data.status})
            createTdElement({field: "device", value: jsonMessage.data.device})
            createTdElement({field: "cluster", value: jsonMessage.data.cluster})
            createTdElement({field: "vm-interfaces", value: jsonMessage.data.vm_interfaces})
            createTdElement({field: "role", value: jsonMessage.data.role})
            createTdElement({field: "vcpus", value: jsonMessage.data.vcpus})
            createTdElement({field: "memory", value: jsonMessage.data.memory})
            createTdElement({field: "disk-space", value: jsonMessage.data.disk})
            createTdElement({field: "ip-address", showUndefinedBadge: true})

            if (jsonMessage.data.completed === false) {
                updateCounter("total-vm-count")
            }
            if (jsonMessage.data.completed === true && jsonMessage.data.increment_count === "yes") {
                updateCounter("synced-vm-count")
            }
            updatePercentage("total-vm-count", "synced-vm-count", "sync-percentage-ratio")
        }
    } catch (error) {
        console.log(`ERROR: ${error}`)
    }
}
