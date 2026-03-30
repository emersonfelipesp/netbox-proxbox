import { fetchJson, setBadgeState } from "./common.js";
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
            const cardId = card.dataset.proxmoxCardId;
            const badge = cardId ? document.getElementById(`proxmox-status-badge-${cardId}`) : null;
            const errorContainer = cardId
                ? document.getElementById(`proxmox-connection-error-${cardId}`)
                : null;

            try {
                const payload = await fetchJson(card.dataset.proxmoxCardUrl);
                const clusterData = payload.cluster_data ?? {};
                renderProxmoxField(card, "mode", clusterData.mode);
                renderProxmoxField(card, "version", clusterData.version);
                renderProxmoxField(card, "repoid", clusterData.repoid);

                if (payload.detail && badge) {
                    setBadgeState(badge, "error", payload.detail);
                }

                if (errorContainer) {
                    if (payload.detail) {
                        errorContainer.innerHTML = `<div class="alert alert-warning py-2 px-3 mb-0">${payload.detail}</div>`;
                    } else {
                        errorContainer.innerHTML = "";
                    }
                }
            } catch (error) {
                renderProxmoxField(card, "mode", null);
                renderProxmoxField(card, "version", null);
                renderProxmoxField(card, "repoid", null);
                if (badge) {
                    setBadgeState(badge, "error", error.message || "Unknown error");
                }
                if (errorContainer) {
                    errorContainer.innerHTML = `<div class="alert alert-danger py-2 px-3 mb-0">${error.message || "Unable to load Proxmox card data."}</div>`;
                }
            }
        }),
    );
}

document.addEventListener("DOMContentLoaded", async () => {
    initializeWebSocket();
    await Promise.all([refreshStatusBadges(), hydrateProxmoxCards()]);
});
