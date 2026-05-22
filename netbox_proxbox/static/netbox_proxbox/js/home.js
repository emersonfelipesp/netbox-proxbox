import { fetchJson, setBadgeState } from "./common.js";
import WebSocketClient from "./websocket.js";

function wireSelectAllCheckboxes() {
    for (const selectAll of document.querySelectorAll("[data-proxbox-select-all]")) {
        if (selectAll.dataset.proxboxBound === "true") {
            continue;
        }
        selectAll.dataset.proxboxBound = "true";
        selectAll.addEventListener("change", () => {
            const targetSelector = selectAll.dataset.proxboxSelectAll;
            if (!targetSelector) {
                return;
            }
            for (const checkbox of document.querySelectorAll(targetSelector)) {
                if (checkbox instanceof HTMLInputElement) {
                    checkbox.checked = selectAll.checked;
                }
            }
        });
    }
}

function initializeWebSocket() {
    const websocketEndpoint = window.proxboxConfig?.websocketEndpoint;
    const websocketApiKey = window.proxboxConfig?.websocketApiKey;
    const syncContainer = document.querySelector("[data-use-websocket='true'][data-server-side-websocket='false']");
    if (!websocketEndpoint || !syncContainer) {
        return null;
    }

    return new WebSocketClient(websocketEndpoint, websocketApiKey || null);
}

function isFastapiStatusElement(element) {
    const statusUrl = element.dataset.serviceStatusUrl || "";
    return statusUrl.includes("/keepalive-status/fastapi/");
}

function statusDetail(payload) {
    if (payload.detail) {
        return payload.detail;
    }
    if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
        return payload.warnings.join(" ");
    }
    return "";
}

function statusMessageContainer(element) {
    const statusUrl = element.dataset.serviceStatusUrl || "";
    const match = statusUrl.match(/\/keepalive-status\/([^/]+)\/(\d+)\//);
    if (!match) {
        return null;
    }
    return document.getElementById(`${match[1]}-connection-error-${match[2]}`);
}

function renderServiceStatusMessage(element, payload) {
    const container = statusMessageContainer(element);
    if (!container) {
        return;
    }

    const detail = statusDetail(payload).trim();
    const shouldRender = detail && (payload.status !== "success" || payload.warnings?.length);
    if (!shouldRender) {
        container.innerHTML = "";
        return;
    }

    const alert = document.createElement("div");
    alert.className = `alert ${payload.status === "error" ? "alert-danger" : "alert-warning"} py-2 px-3 mb-0`;
    alert.textContent = detail;
    container.innerHTML = "";
    container.appendChild(alert);
}

async function refreshStatusBadges() {
    const elements = Array.from(document.querySelectorAll("[data-service-status-url]"));
    const fastapiElements = elements.filter(isFastapiStatusElement);
    const dependentElements = elements.filter((element) => !isFastapiStatusElement(element));

    let fastapiConnected = fastapiElements.length === 0;

    await Promise.all(
        fastapiElements.map(async (element) => {
            try {
                const payload = await fetchJson(element.dataset.serviceStatusUrl);
                setBadgeState(element, payload.status, statusDetail(payload));
                renderServiceStatusMessage(element, payload);
                if (payload.status === "success") {
                    fastapiConnected = true;
                }
            } catch (error) {
                setBadgeState(element, "error", error.message || "Unknown error");
                renderServiceStatusMessage(element, {
                    status: "error",
                    detail: error.message || "Unknown error",
                });
            }
        }),
    );

    if (!fastapiConnected) {
        for (const element of dependentElements) {
            setBadgeState(
                element,
                "error",
                "Skipped because FastAPI backend keepalive is not successful.",
            );
            renderServiceStatusMessage(element, {
                status: "error",
                detail: "Skipped because FastAPI backend keepalive is not successful.",
            });
        }
        return false;
    }

    await Promise.all(
        dependentElements.map(async (element) => {
            try {
                const payload = await fetchJson(element.dataset.serviceStatusUrl);
                setBadgeState(element, payload.status, statusDetail(payload));
                renderServiceStatusMessage(element, payload);
            } catch (error) {
                setBadgeState(element, "error", error.message || "Unknown error");
                renderServiceStatusMessage(element, {
                    status: "error",
                    detail: error.message || "Unknown error",
                });
            }
        }),
    );

    return true;
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
    wireSelectAllCheckboxes();

    const fastapiConnected = await refreshStatusBadges();
    if (fastapiConnected) {
        await hydrateProxmoxCards();
    }
});
