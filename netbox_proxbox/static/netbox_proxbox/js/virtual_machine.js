import { createTdElement } from './common.js'

export function populateVirtualMachinesTable(jsonMessage) {
    if (!jsonMessage) {
        return;
    }

    const virtualMachineTable = document.getElementById('virtual-machine-table-data');
    if (!virtualMachineTable) {
        return;
    }

    const virtualMachinesDiv = document.getElementById('virtual-machines-div');
    if (virtualMachinesDiv) {
        virtualMachinesDiv.style.display = "block";
    }

    const vmTableDefaultTd = document.getElementById('virtual-machines-table-default-td');
    if (vmTableDefaultTd) {
        vmTableDefaultTd.style.display = "none";
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

    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'status', `<span class="badge text-bg-${statusClass}">${status}</span>`));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'netbox-id', data.netbox_id || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'name', data.name || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'vm-status', `<span class="badge text-bg-${statusClass}">${status}</span>`));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'cluster', data.cluster || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'site', data.site || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'role', data.role || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'tenant', data.tenant || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'vcpus', data.vcpus || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'memory', data.memory || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'disk', data.disk || undefinedHtml));
    row.appendChild(createTdElement('virtual_machine', jsonDataName, 'actions', ''));

    virtualMachineTable.appendChild(row);
}

function getStatusClass(status) {
    const statusMap = {
        active: 'green',
        offline: 'red',
        planned: 'blue',
        staged: 'yellow',
        running: 'green',
        stopped: 'red',
        suspended: 'yellow',
        failed: 'red',
    };
    return statusMap[status] || 'grey';
}

export function handleVMSSEEvent(sseData) {
    const normalized = normalizeVMMessage(sseData);
    if (normalized) {
        populateVirtualMachinesTable(normalized);
    }
}

function normalizeVMMessage(sseData) {
    if (!sseData || typeof sseData !== 'object') {
        return null;
    }
    const payload = sseData.payload;
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    const payloadData = payload.data || {};
    return {
        object: payload.object || 'virtual_machine',
        data: {
            ...payloadData,
            rowid: sseData.rowid || payloadData.rowid || payloadData.name,
            netbox_id: payloadData.netbox_id,
            name: payloadData.name,
            sync_status: payloadData.sync_status || sseData.status,
            status: payloadData.status,
            cluster: payloadData.cluster,
            site: payloadData.site,
            role: payloadData.role,
            tenant: payloadData.tenant,
            vcpus: payloadData.vcpus,
            memory: payloadData.memory,
            disk: payloadData.disk,
        },
    };
}
