import { fetchJson, setBadgeState } from "./common.js";
import { poll } from "./polling.js";
import WebSocketClient from "./websocket.js";

function initializeWebSocket() {
    const websocketEndpoint = window.proxboxConfig?.websocketEndpoint;
    const syncContainer = document.querySelector("[data-use-websocket='true'][data-server-side-websocket='false']");
    if (!websocketEndpoint || !syncContainer) {
        return null;
    }

    return new WebSocketClient(websocketEndpoint);
}

async function refreshStatusBadges() {
    const elements = document.querySelectorAll("[data-service-status-url]");
    await Promise.all(
        Array.from(elements).map(async (element) => {
            try {
                const payload = await fetchJson(element.dataset.serviceStatusUrl);
                setBadgeState(element, payload.status, payload.detail || "");
            } catch (error) {
                setBadgeState(element, "error", error.message || "Unknown error");
            }
        }),
    );
}

function renderProxmoxField(card, fieldName, value) {
    const cell = card.querySelector(`[data-proxmox-field="${fieldName}"]`);
    if (!cell) {
        return;
    }

    if (!value) {
        cell.innerHTML = '<span class="badge text-bg-grey">Empty</span>';
        return;
    }

    if (fieldName === "mode") {
        const label = value === "cluster" ? "Cluster (Multiple Nodes)" : "Standalone";
        cell.innerHTML = `<span class="badge text-bg-purple">${label}</span>`;
        return;
    }

    cell.innerHTML = `<span class="badge text-bg-grey"><strong>${value}</strong></span>`;
}

async function hydrateProxmoxCards() {
    const cards = document.querySelectorAll("[data-proxmox-card-url]");
    await Promise.all(
        Array.from(cards).map(async (card) => {
            try {
                const payload = await fetchJson(card.dataset.proxmoxCardUrl);
                const clusterData = payload.cluster_data ?? {};
                renderProxmoxField(card, "mode", clusterData.mode);
                renderProxmoxField(card, "version", clusterData.version);
                renderProxmoxField(card, "repoid", clusterData.repoid);
            } catch (error) {
                renderProxmoxField(card, "mode", null);
                renderProxmoxField(card, "version", null);
                renderProxmoxField(card, "repoid", null);
            }
        }),
    );
}

function appendLogMessage(message) {
    const messages = document.getElementById("messages");
    if (!messages) {
        return;
    }

    const item = document.createElement("li");
    item.style.lineHeight = "170%";
    item.textContent = typeof message === "string" ? message : JSON.stringify(message);
    messages.appendChild(item);

    const scrollableDiv = document.getElementById("scrollable-div");
    if (scrollableDiv) {
        scrollableDiv.scrollTop = scrollableDiv.scrollHeight;
    }
}

function wireSyncButtons(websocketClient) {
    const syncButtons = document.querySelectorAll("[data-sync-url][data-sync-kind]");
    for (const button of syncButtons) {
        button.addEventListener("click", async (event) => {
            event.preventDefault();
            const { syncUrl, syncKind } = button.dataset;
            button.disabled = true;

            try {
                const payload = await fetchJson(syncUrl);
                appendLogMessage(`${syncKind}: request accepted`);

                if (syncKind === "devices" || syncKind === "virtual-machines" || syncKind === "full-update") {
                    if (websocketClient && websocketClient.isConnected()) {
                        if (syncKind === "devices") {
                            websocketClient.syncNodes();
                        } else if (syncKind === "virtual-machines") {
                            websocketClient.syncVirtualMachines();
                        } else {
                            websocketClient.sendFullUpdate();
                        }
                    } else {
                        const pollingKind = syncKind === "virtual-machines" ? "virtual-machines" : syncKind;
                        poll(pollingKind);
                    }
                }

                if (payload?.detail) {
                    appendLogMessage(payload.detail);
                }
            } catch (error) {
                appendLogMessage(`${syncKind}: ${error.message}`);
            } finally {
                button.disabled = false;
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    const websocketClient = initializeWebSocket();
    wireSyncButtons(websocketClient);
    await Promise.all([refreshStatusBadges(), hydrateProxmoxCards()]);
});
