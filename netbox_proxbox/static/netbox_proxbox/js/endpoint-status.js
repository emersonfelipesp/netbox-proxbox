import { fetchJson, setBadgeState } from "./common.js";

// Keepalive badges are refreshed by a single self-rescheduling loop rather
// than a fixed interval timer. Each round refreshes the badges one at a time
// and the next round is armed only after the previous one has settled, so a
// slow backend can never stack overlapping requests. Every keepalive request
// that reaches NetBox can land on a freshly spawned WSGI worker thread with
// its own persistent database connection, so bounding the request rate and
// concurrency here is what keeps the PostgreSQL connection count flat.
const REFRESH_INTERVAL_MS = 30000;

let refreshTimer = null;
let refreshInFlight = false;

function statusDetail(payload) {
    if (payload.detail) {
        return payload.detail;
    }
    if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
        return payload.warnings.join(" ");
    }
    return "";
}

function pageIsHidden() {
    return typeof document.hidden === "boolean" && document.hidden;
}

async function refreshBadge(element) {
    try {
        const payload = await fetchJson(element.dataset.serviceStatusUrl);
        setBadgeState(element, payload.status, statusDetail(payload));
    } catch (error) {
        setBadgeState(element, "error", error.message || "Unknown error");
    }
}

async function refreshServiceBadges() {
    if (refreshInFlight) {
        return;
    }
    refreshInFlight = true;
    try {
        const badges = Array.from(document.querySelectorAll("[data-service-status-url]"));
        for (const element of badges) {
            if (pageIsHidden()) {
                break;
            }
            await refreshBadge(element);
        }
    } finally {
        refreshInFlight = false;
    }
}

function cancelScheduledRefresh() {
    if (refreshTimer !== null) {
        window.clearTimeout(refreshTimer);
        refreshTimer = null;
    }
}

function scheduleNextRefresh() {
    cancelScheduledRefresh();
    if (pageIsHidden()) {
        return;
    }
    refreshTimer = window.setTimeout(runRefreshCycle, REFRESH_INTERVAL_MS);
}

async function runRefreshCycle() {
    refreshTimer = null;
    if (pageIsHidden()) {
        return;
    }
    await refreshServiceBadges();
    scheduleNextRefresh();
}

function handleVisibilityChange() {
    if (pageIsHidden()) {
        cancelScheduledRefresh();
        return;
    }
    if (refreshTimer === null && !refreshInFlight) {
        runRefreshCycle();
    }
}

const badgesExist = document.querySelectorAll("[data-service-status-url]").length > 0;
if (badgesExist) {
    document.addEventListener("visibilitychange", handleVisibilityChange);
    runRefreshCycle();
}
