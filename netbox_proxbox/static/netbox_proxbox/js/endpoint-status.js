import { fetchJson, setBadgeState } from "./common.js";

const REFRESH_INTERVAL_MS = 30000;

function statusDetail(payload) {
    if (payload.detail) {
        return payload.detail;
    }
    if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
        return payload.warnings.join(" ");
    }
    return "";
}

async function refreshServiceBadges() {
    const badges = document.querySelectorAll("[data-service-status-url]");
    if (!badges.length) {
        return;
    }

    await Promise.all(
        Array.from(badges).map(async (element) => {
            try {
                const payload = await fetchJson(element.dataset.serviceStatusUrl);
                setBadgeState(element, payload.status, statusDetail(payload));
            } catch (error) {
                setBadgeState(element, "error", error.message || "Unknown error");
            }
        }),
    );
}

const badgesExist = document.querySelectorAll("[data-service-status-url]").length > 0;
if (badgesExist) {
    refreshServiceBadges();
    window.setInterval(refreshServiceBadges, REFRESH_INTERVAL_MS);
}
