/*
 * Self-contained dashboard hydration script.
 *
 * The home view inlines this file via the {% inline_static_script %} template
 * tag so the dashboard renders correctly even when ``manage.py
 * collectstatic`` was not run after installing or upgrading the plugin
 * (issue #355). Because the template tag reads it straight off the package
 * directory, this script must NOT use ES module imports/exports — it has to
 * be a regular IIFE that runs inline in the page.
 *
 * Functionality mirrors home.js + the helpers from common.js it depends on.
 * If you change behavior here, mirror it in home.js (loaded as a module by
 * the other dashboard-style pages) or vice-versa.
 */
(function () {
    "use strict";

    function setBadgeState(element, status, detail) {
        if (!element) {
            return;
        }
        var styles = {
            success: "badge text-bg-green",
            error: "badge text-bg-red",
            disabled: "badge text-bg-secondary",
            unknown: "badge text-bg-grey",
        };
        var labels = {
            success: "Successful!",
            error: "Error!",
            disabled: "Disabled",
            unknown: "Unknown",
        };
        element.className = styles[status] || styles.unknown;
        element.textContent = labels[status] || labels.unknown;
        var tooltip = typeof detail === "string" ? detail.trim() : "";
        if (tooltip) {
            element.title = tooltip;
            element.dataset.bsToggle = "tooltip";
            element.dataset.bsTitle = tooltip;
        } else {
            element.removeAttribute("title");
            element.removeAttribute("data-bs-toggle");
            element.removeAttribute("data-bs-title");
        }
    }

    async function fetchJson(url, options) {
        options = options || {};
        var response = await fetch(url, Object.assign({
            headers: Object.assign({ Accept: "application/json" }, options.headers || {}),
        }, options));
        var payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }
        if (!response.ok) {
            throw new Error(payload.detail || ("Request failed with status " + response.status));
        }
        return payload;
    }

    function wireSelectAllCheckboxes() {
        var selectAlls = document.querySelectorAll("[data-proxbox-select-all]");
        for (var i = 0; i < selectAlls.length; i++) {
            var selectAll = selectAlls[i];
            if (selectAll.dataset.proxboxBound === "true") {
                continue;
            }
            selectAll.dataset.proxboxBound = "true";
            (function (el) {
                el.addEventListener("change", function () {
                    var targetSelector = el.dataset.proxboxSelectAll;
                    if (!targetSelector) {
                        return;
                    }
                    var targets = document.querySelectorAll(targetSelector);
                    for (var j = 0; j < targets.length; j++) {
                        if (targets[j] instanceof HTMLInputElement) {
                            targets[j].checked = el.checked;
                        }
                    }
                });
            })(selectAll);
        }
    }

    function isFastapiStatusElement(element) {
        var statusUrl = element.dataset.serviceStatusUrl || "";
        return statusUrl.indexOf("/keepalive-status/fastapi/") !== -1;
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
        var statusUrl = element.dataset.serviceStatusUrl || "";
        var match = statusUrl.match(/\/keepalive-status\/([^/]+)\/(\d+)\//);
        if (!match) {
            return null;
        }
        return document.getElementById(match[1] + "-connection-error-" + match[2]);
    }

    function renderServiceStatusMessage(element, payload) {
        var container = statusMessageContainer(element);
        if (!container) {
            return;
        }

        var detail = statusDetail(payload).trim();
        var hasWarnings = Array.isArray(payload.warnings) && payload.warnings.length > 0;
        var shouldRender = detail && (payload.status !== "success" || hasWarnings);
        if (!shouldRender) {
            container.innerHTML = "";
            return;
        }

        var alert = document.createElement("div");
        alert.className =
            "alert " +
            (payload.status === "error" ? "alert-danger" : "alert-warning") +
            " py-2 px-3 mb-0";
        alert.textContent = detail;
        container.innerHTML = "";
        container.appendChild(alert);
    }

    async function refreshStatusBadges() {
        var elements = Array.prototype.slice.call(
            document.querySelectorAll("[data-service-status-url]"),
        );
        var fastapiElements = elements.filter(isFastapiStatusElement);
        var dependentElements = elements.filter(function (element) {
            return !isFastapiStatusElement(element);
        });
        var fastapiConnected = fastapiElements.length === 0;
        await Promise.all(
            fastapiElements.map(async function (element) {
                try {
                    var payload = await fetchJson(element.dataset.serviceStatusUrl);
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
            for (var i = 0; i < dependentElements.length; i++) {
                setBadgeState(
                    dependentElements[i],
                    "error",
                    "Skipped because FastAPI backend keepalive is not successful.",
                );
                renderServiceStatusMessage(dependentElements[i], {
                    status: "error",
                    detail: "Skipped because FastAPI backend keepalive is not successful.",
                });
            }
            return false;
        }
        await Promise.all(
            dependentElements.map(async function (element) {
                try {
                    var payload = await fetchJson(element.dataset.serviceStatusUrl);
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
        var cell = card.querySelector('[data-proxmox-field="' + fieldName + '"]');
        if (!cell) {
            return;
        }
        if (!value) {
            cell.innerHTML = '<span class="badge text-bg-grey">Empty</span>';
            return;
        }
        if (fieldName === "mode") {
            var label = value === "cluster" ? "Cluster (Multiple Nodes)" : "Standalone";
            cell.innerHTML = '<span class="badge text-bg-purple">' + label + "</span>";
            return;
        }
        cell.innerHTML = '<span class="badge text-bg-grey"><strong>' + value + "</strong></span>";
    }

    async function hydrateProxmoxCards() {
        var cards = document.querySelectorAll("[data-proxmox-card-url]");
        await Promise.all(
            Array.prototype.slice.call(cards).map(async function (card) {
                var cardId = card.dataset.proxmoxCardId;
                var badge = cardId ? document.getElementById("proxmox-status-badge-" + cardId) : null;
                var errorContainer = cardId
                    ? document.getElementById("proxmox-connection-error-" + cardId)
                    : null;
                try {
                    var payload = await fetchJson(card.dataset.proxmoxCardUrl);
                    var clusterData = payload.cluster_data || {};
                    renderProxmoxField(card, "mode", clusterData.mode);
                    renderProxmoxField(card, "version", clusterData.version);
                    renderProxmoxField(card, "repoid", clusterData.repoid);
                    if (payload.detail && badge) {
                        setBadgeState(badge, "error", payload.detail);
                    }
                    if (errorContainer) {
                        if (payload.detail) {
                            errorContainer.innerHTML =
                                '<div class="alert alert-warning py-2 px-3 mb-0">' + payload.detail + "</div>";
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
                        errorContainer.innerHTML =
                            '<div class="alert alert-danger py-2 px-3 mb-0">' +
                            (error.message || "Unable to load Proxmox card data.") +
                            "</div>";
                    }
                }
            }),
        );
    }

    document.addEventListener("DOMContentLoaded", async function () {
        wireSelectAllCheckboxes();
        var fastapiConnected = await refreshStatusBadges();
        if (fastapiConnected) {
            await hydrateProxmoxCards();
        }
    });
})();
