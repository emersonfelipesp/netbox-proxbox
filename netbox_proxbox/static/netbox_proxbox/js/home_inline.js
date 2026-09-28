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
    var HOME_REQUEST_CONCURRENCY = 4;
    var HOME_CARD_MAX_RETRIES = 3;
    var homeRequestQueue = [];
    var homeRequestsInFlight = 0;
    var cardRetryState = new WeakMap();

    function setBadgeState(element, status, detail) {
        if (!element) {
            return;
        }
        var styles = {
            success: "badge text-bg-green",
            error: "badge text-bg-red",
            throttled: "badge text-bg-secondary",
            disabled: "badge text-bg-secondary",
            unknown: "badge text-bg-grey",
        };
        var labels = {
            success: "Successful!",
            error: "Error!",
            throttled: "Throttled",
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
            var requestError = new Error(
                payload.detail || ("Request failed with status " + response.status),
            );
            requestError.status = response.status;
            requestError.payload = payload;
            requestError.retryAfter = response.headers.get("Retry-After");
            throw requestError;
        }
        return payload;
    }

    function drainHomeRequestQueue() {
        while (
            homeRequestsInFlight < HOME_REQUEST_CONCURRENCY &&
            homeRequestQueue.length > 0
        ) {
            var queued = homeRequestQueue.shift();
            homeRequestsInFlight += 1;
            Promise.resolve()
                .then(queued.task)
                .then(queued.resolve, queued.reject)
                .finally(function () {
                    homeRequestsInFlight -= 1;
                    drainHomeRequestQueue();
                });
        }
    }

    function scheduleHomeRequest(task) {
        return new Promise(function (resolve, reject) {
            homeRequestQueue.push({ task: task, resolve: resolve, reject: reject });
            drainHomeRequestQueue();
        });
    }

    function runBounded(tasks) {
        if (tasks.length === 0) {
            return Promise.resolve();
        }
        return new Promise(function (resolve, reject) {
            var completed = 0;
            tasks.forEach(function (task) {
                scheduleHomeRequest(task).then(function () {
                    completed += 1;
                    if (completed === tasks.length) {
                        resolve();
                    }
                }, reject);
            });
        });
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
            container.replaceChildren();
            return;
        }

        var alert = document.createElement("div");
        alert.className =
            "alert " +
            (payload.status === "error" ? "alert-danger" : "alert-warning") +
            " py-2 px-3 mb-0";
        alert.textContent = detail;
        container.replaceChildren(alert);
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
        await runBounded(
            fastapiElements.map(function (element) {
                return async function () {
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
                };
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
        await runBounded(
            dependentElements.map(function (element) {
                return async function () {
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
                };
            }),
        );
        return true;
    }

    function renderProxmoxField(card, fieldName, value) {
        var cell = card.querySelector('[data-proxmox-field="' + fieldName + '"]');
        if (!cell) {
            return;
        }
        var badge = document.createElement("span");
        badge.className = "badge " + (fieldName === "mode" && value ? "text-bg-purple" : "text-bg-grey");
        if (!value) {
            badge.textContent = "Empty";
        } else if (fieldName === "mode") {
            badge.textContent = value === "cluster" ? "Cluster (Multiple Nodes)" : "Standalone";
        } else {
            var strong = document.createElement("strong");
            strong.textContent = String(value);
            badge.appendChild(strong);
        }
        cell.replaceChildren(badge);
    }

    function renderProxmoxAlert(container, style, detail) {
        if (!container || !detail) {
            if (container) {
                container.replaceChildren();
            }
            return;
        }
        var alert = document.createElement("div");
        alert.className = "alert " + style + " py-2 px-3 mb-0";
        alert.textContent = detail;
        container.replaceChildren(alert);
    }

    function retryDetail(payload) {
        var detail = payload.detail || "Backend capacity is temporarily limited; retrying.";
        if (payload.retry_after) {
            return detail + " Retrying after " + payload.retry_after + " seconds.";
        }
        return detail;
    }

    function retryDelayMs(retryAfter) {
        var seconds = Number(retryAfter);
        if (Number.isFinite(seconds)) {
            return Math.max(0, seconds * 1000);
        }
        var retryAt = Date.parse(retryAfter);
        return Number.isFinite(retryAt) ? Math.max(0, retryAt - Date.now()) : null;
    }

    function scheduleCardRetry(card, retryAfter) {
        var delay = retryDelayMs(retryAfter);
        var state = cardRetryState.get(card) || { retries: 0, timer: null };
        if (delay === null || state.timer !== null || state.retries >= HOME_CARD_MAX_RETRIES) {
            return;
        }
        state.retries += 1;
        state.timer = window.setTimeout(function () {
            state.timer = null;
            scheduleHomeRequest(function () {
                return hydrateProxmoxCard(card);
            });
        }, delay);
        cardRetryState.set(card, state);
    }

    async function hydrateProxmoxCard(card) {
        var cardId = card.dataset.proxmoxCardId;
        var errorContainer = cardId
            ? document.getElementById("proxmox-connection-error-" + cardId)
            : null;
        try {
            var payload = await fetchJson(card.dataset.proxmoxCardUrl);
            var clusterData = payload.cluster_data || {};
            renderProxmoxField(card, "mode", clusterData.mode);
            renderProxmoxField(card, "version", clusterData.version);
            renderProxmoxField(card, "repoid", clusterData.repoid);
            if (errorContainer) {
                renderProxmoxAlert(
                    errorContainer,
                    "alert-warning",
                    payload.status === "throttled" ? retryDetail(payload) : payload.detail,
                );
            }
            if (payload.status === "throttled" && payload.retry_after) {
                scheduleCardRetry(card, payload.retry_after);
            }
        } catch (error) {
            renderProxmoxField(card, "mode", null);
            renderProxmoxField(card, "version", null);
            renderProxmoxField(card, "repoid", null);
            if (errorContainer) {
                var throttled = error.status === 429 || error.status === 503;
                renderProxmoxAlert(
                    errorContainer,
                    throttled ? "alert-warning" : "alert-danger",
                    throttled
                        ? retryDetail({
                            detail: error.message,
                            retry_after: error.retryAfter,
                        })
                        : error.message || "Unable to load Proxmox card data.",
                );
            }
            if ((error.status === 429 || error.status === 503) && error.retryAfter) {
                scheduleCardRetry(card, error.retryAfter);
            }
        }
    }

    async function hydrateProxmoxCards() {
        var cards = Array.prototype.slice.call(
            document.querySelectorAll("[data-proxmox-card-url]"),
        );
        await runBounded(cards.map(function (card) {
            return function () {
                return hydrateProxmoxCard(card);
            };
        }));
    }

    document.addEventListener("DOMContentLoaded", async function () {
        wireSelectAllCheckboxes();
        var fastapiConnected = await refreshStatusBadges();
        if (fastapiConnected) {
            await hydrateProxmoxCards();
        }
    });
})();
