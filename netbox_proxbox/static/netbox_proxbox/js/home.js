import { fetchJson, getCsrfToken, setBadgeState } from "./common.js";
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

function syncLabel(syncKind) {
    if (syncKind === "devices") {
        return "Sync Nodes";
    }
    if (syncKind === "virtual-machines") {
        return "Sync Virtual Machines";
    }
    if (syncKind === "full-update") {
        return "Full Update Sync";
    }
    return "Sync";
}

function startSyncProgress(syncKind) {
    const progressContainer = document.getElementById("sync-progress-container");
    const progressLabel = document.getElementById("sync-progress-label");
    const progressState = document.getElementById("sync-progress-state");
    if (!progressContainer || !progressLabel || !progressState) {
        return;
    }

    progressLabel.textContent = `${syncLabel(syncKind)} in progress`;
    progressState.textContent = "Working...";
    progressContainer.classList.remove("d-none");
}

function stopSyncProgress(status = "idle", detail = "") {
    const progressContainer = document.getElementById("sync-progress-container");
    const progressLabel = document.getElementById("sync-progress-label");
    const progressState = document.getElementById("sync-progress-state");
    if (!progressContainer || !progressLabel || !progressState) {
        return;
    }

    if (status === "error") {
        progressLabel.textContent = "Sync failed";
        progressState.textContent = detail || "The backend returned an error.";
    } else {
        progressLabel.textContent = "Sync complete";
        progressState.textContent = detail || "Finished.";
    }

    window.setTimeout(() => {
        progressContainer.classList.add("d-none");
        progressLabel.textContent = "Sync in progress";
        progressState.textContent = "Working...";
    }, 1200);
}

function wireSyncForms() {
    const syncForms = document.querySelectorAll("form[data-sync-url][data-sync-kind]");
    for (const form of syncForms) {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const { syncUrl, syncKind } = form.dataset;
            const button = form.querySelector("button[type='submit']");
            if (!button) {
                return;
            }
            button.disabled = true;
            startSyncProgress(syncKind);
            appendLogMessage(`${syncKind}: request started`);

            try {
                const payload = await fetchJson(syncUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                appendLogMessage(`${syncKind}: request completed`);

                if (payload?.detail) {
                    appendLogMessage(payload.detail);
                }
                if (payload?.response?.status) {
                    appendLogMessage(`${syncKind}: ${payload.response.status}`);
                }
                await Promise.all([refreshStatusBadges(), hydrateProxmoxCards()]);
                stopSyncProgress("success", payload?.detail || "");
            } catch (error) {
                appendLogMessage(`${syncKind}: ${error.message}`);
                stopSyncProgress("error", error.message || "Request failed.");
            } finally {
                button.disabled = false;
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    initializeWebSocket();
    wireSyncForms();
    await Promise.all([refreshStatusBadges(), hydrateProxmoxCards()]);
});
