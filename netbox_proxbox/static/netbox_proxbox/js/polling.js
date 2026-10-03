import { getCsrfToken } from "./common.js";
import { populateTable } from "./table.js";

const WEBSOCKET_ROUTE = "/plugins/proxbox/websocket";
const NEXT_CURSOR_HEADER = "X-Proxbox-Next-Cursor";
const CURSOR_RESET_HEADER = "X-Proxbox-Cursor-Reset";
const CURSOR_GAP_HEADER = "X-Proxbox-Cursor-Gap";
const CURSOR_PATTERN = /^[0-9a-f]{16}\.\d{1,18}$/;
const POLL_INTERVAL_MS = 1000;
// Stop after this many consecutive empty polls with no terminal message.
const DEFAULT_MAX_IDLE_POLLS = 120;

// Backend message ``object`` whose ``end: true`` completes each sync kind.
// proxbox-api emits no aggregate full-update terminal: a full update runs the
// device stage and then the VM stage, so only the VM-stage terminal proves it
// finished. Silence after the device stage is never treated as success.
const TERMINAL_OBJECT = {
    "full-update": "virtual_machine",
    devices: "device",
    "virtual-machines": "virtual_machine",
};

const TABLES = {
    virtual_machine: {
        tableType: "virtual_machine",
        tableDivId: "virtual-machines-div",
        tableId: "virtual-machine-table-data",
        defaultRowId: "virtual-machines-table-default-td",
    },
    device: {
        tableType: "device",
        tableDivId: "device-div",
        tableId: "device-table-data",
        defaultRowId: "device-table-default-td",
    },
};

function syncUrl(objectType) {
    return `${WEBSOCKET_ROUTE}/${encodeURIComponent(objectType)}`;
}

async function readJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return null;
    }
}

/**
 * Ask the server-side WebSocket bridge to start one sync kind.
 *
 * Starting a sync is a state change, so it is a CSRF-protected POST. The
 * server answers with the message cursor at the time the sync was queued;
 * pass it to ``poll`` so only messages produced after the trigger are read.
 * A 409 means a sync of this kind is already running; its cursor is still
 * returned so the caller can follow it.
 */
export async function startSync(objectType) {
    const response = await fetch(syncUrl(objectType), {
        method: "POST",
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
    });
    const payload = (await readJson(response)) || {};
    if (!response.ok && response.status !== 409) {
        throw new Error(payload.error || `Sync request failed with status ${response.status}`);
    }
    return payload;
}

function parseMessage(rawMessage) {
    if (typeof rawMessage !== "string") {
        return rawMessage;
    }
    try {
        return JSON.parse(rawMessage);
    } catch (error) {
        return null;
    }
}

function renderMessage(message) {
    const table = message ? TABLES[message.object] : undefined;
    if (table) {
        populateTable({ ...table, jsonMessage: message });
    }
}

function endsObject(message, object) {
    return Boolean(message && message.end === true && message.object === object);
}

async function fetchPage(objectType, cursor) {
    const params = new URLSearchParams({ json_response: "true" });
    if (cursor) {
        params.set("after", cursor);
    }
    const response = await fetch(`${syncUrl(objectType)}?${params.toString()}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
    });
    const data = await readJson(response);
    if (!response.ok || !Array.isArray(data)) {
        throw new Error(`Polling failed with status ${response.status}`);
    }
    if (response.headers.get(CURSOR_RESET_HEADER) || response.headers.get(CURSOR_GAP_HEADER)) {
        // Another worker answered, or messages were evicted: earlier progress
        // and terminals cannot be attributed to this run.
        throw new Error("The sync message stream was interrupted; reload the page to see the current state.");
    }
    const headerCursor = response.headers.get(NEXT_CURSOR_HEADER);
    return { data, cursor: CURSOR_PATTERN.test(headerCursor || "") ? headerCursor : cursor };
}

function isComplete(objectType, messages) {
    return messages.some((message) => endsObject(message, TERMINAL_OBJECT[objectType]));
}

/**
 * Follow buffered backend messages with a per-client cursor.
 *
 * GET never starts a sync and never removes messages for other users. Empty
 * polls are normal while the backend works; polling completes only on the
 * terminal message for ``objectType`` (for a full update, the VM-stage
 * terminal). A cursor reset or gap is reported as an error, and polling gives
 * up with a timeout after ``maxIdlePolls`` consecutive empty polls.
 */
export async function poll(objectType, callbacks = {}) {
    const { onComplete = () => {}, onError = () => {}, cursor = null } = callbacks;
    const maxIdlePolls = callbacks.maxIdlePolls ?? DEFAULT_MAX_IDLE_POLLS;
    let nextCursor = cursor;
    let idlePolls = 0;

    while (idlePolls < maxIdlePolls) {
        let page;
        try {
            page = await fetchPage(objectType, nextCursor);
        } catch (error) {
            console.error("Polling failed:", error);
            onError(error);
            return;
        }
        nextCursor = page.cursor;
        idlePolls = page.data.length === 0 ? idlePolls + 1 : 0;
        const messages = page.data.map(parseMessage);
        messages.forEach(renderMessage);
        if (isComplete(objectType, messages)) {
            onComplete();
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    onError(new Error("Timed out waiting for the sync to finish."));
}
