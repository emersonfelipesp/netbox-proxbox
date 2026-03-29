import { createTdElement } from './common.js'

export function populateDevicesTable(jsonMessage) {
    if (!jsonMessage) {
        return;
    }

    const deviceTable = document.getElementById('device-table-data');
    if (!deviceTable) {
        return;
    }

    const nodesDiv = document.getElementById('device-div');
    if (nodesDiv) {
        nodesDiv.style.display = "block";
    }

    const deviceTableDefaultTd = document.getElementById('device-table-default-td');
    if (deviceTableDefaultTd) {
        deviceTableDefaultTd.style.display = "none";
    }

    const data = jsonMessage.data || {};
    const rowId = data.rowid || data.name;
    if (!rowId) {
        return;
    }

    let row = document.getElementById(rowId);
    if (!row) {
        row = document.createElement('tr');
        row.id = rowId;
    } else {
        row.innerHTML = "";
    }

    const jsonDataName = data.name;
    const undefinedHtml = '<span class="badge text-bg-grey"><strong>undefined</strong></span>';

    const status = data.sync_status || data.status || 'unknown';
    const statusClass = getStatusClass(status);

    row.appendChild(createTdElement('device', jsonDataName, 'status', `<span class="badge text-bg-${statusClass}">${status}</span>`));
    row.appendChild(createTdElement('device', jsonDataName, 'netbox-id', data.netbox_id || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'name', data.name || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'device-status', `<span class="badge text-bg-${statusClass}">${status}</span>`));
    row.appendChild(createTdElement('device', jsonDataName, 'role', data.role || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'manufacturer', data.manufacturer || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'type', data.device_type || data.type || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'site', data.site || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'cluster', data.cluster || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'tenant', data.tenant || undefinedHtml));
    row.appendChild(createTdElement('device', jsonDataName, 'actions', ''));

    deviceTable.appendChild(row);
}

function getStatusClass(status) {
    const statusMap = {
        active: 'green',
        offline: 'red',
        planned: 'blue',
        staged: 'yellow',
        failed: 'red',
        inventory: 'grey',
        reserved: 'yellow',
    };
    return statusMap[status] || 'grey';
}

export function handleDeviceSSEEvent(sseData) {
    const normalized = normalizeDeviceMessage(sseData);
    if (normalized) {
        populateDevicesTable(normalized);
    }
}

function normalizeDeviceMessage(sseData) {
    if (!sseData || typeof sseData !== 'object') {
        return null;
    }
    const payload = sseData.payload;
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    const payloadData = payload.data || {};
    return {
        object: payload.object || 'device',
        data: {
            ...payloadData,
            rowid: sseData.rowid || payloadData.rowid || payloadData.name,
            netbox_id: payloadData.netbox_id,
            name: payloadData.name,
            sync_status: payloadData.sync_status || sseData.status,
            status: payloadData.status,
            role: payloadData.role,
            manufacturer: payloadData.manufacturer,
            device_type: payloadData.device_type,
            site: payloadData.site,
            cluster: payloadData.cluster,
            tenant: payloadData.tenant,
        },
    };
}
