const FINGERPRINT_PATTERN = /^[0-9a-f]{64}$/;
const AUTHORITY_REQUEST_DEADLINE_MS = 15000;
const TARGET_FIELDS = [
    "kind",
    "domain",
    "ip_address",
    "port",
    "verify_ssl",
    "username",
    "token_name",
    "token_version",
];

const FETCH_OPTIONS = {
    credentials: "same-origin",
    redirect: "error",
    cache: "no-store",
};

function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

function safeDetailMessage(payload) {
    if (!isPlainObject(payload)) {
        return "";
    }
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) {
        return detail.trim();
    }
    return "";
}

function validateTarget(target) {
    if (!isPlainObject(target)) {
        return null;
    }
    for (const field of TARGET_FIELDS) {
        if (!(field in target)) {
            return null;
        }
    }
    if (typeof target.kind !== "string") {
        return null;
    }
    if (typeof target.domain !== "string") {
        return null;
    }
    if (typeof target.ip_address !== "string") {
        return null;
    }
    if (typeof target.port !== "number" || !Number.isFinite(target.port)) {
        return null;
    }
    if (typeof target.verify_ssl !== "boolean") {
        return null;
    }
    if (typeof target.username !== "string") {
        return null;
    }
    if (typeof target.token_name !== "string") {
        return null;
    }
    if (typeof target.token_version !== "string") {
        return null;
    }
    return target;
}

function validateAuthorityPayload(payload) {
    if (!isPlainObject(payload)) {
        return null;
    }
    const target = validateTarget(payload.target);
    if (!target) {
        return null;
    }
    if (typeof payload.approved !== "boolean") {
        return null;
    }
    const fingerprint = payload.target_fingerprint;
    if (typeof fingerprint !== "string" || !FINGERPRINT_PATTERN.test(fingerprint)) {
        return null;
    }
    return {
        target,
        approved: payload.approved,
        target_fingerprint: fingerprint,
    };
}

function formatFieldValue(field, target) {
    if (field === "verify_ssl") {
        return target.verify_ssl ? "Yes" : "No";
    }
    if (field === "port") {
        return String(target.port);
    }
    const value = target[field];
    return value === "" ? "—" : String(value);
}

function readCsrfToken(panel) {
    const input = panel.querySelector("input[name='csrfmiddlewaretoken']");
    return input && input.value ? input.value : "";
}

function setText(element, text) {
    if (element) {
        element.textContent = text;
    }
}

function setApprovedBadge(badge, { endpointEnabled, approved, reviewed }) {
    if (!badge) {
        return;
    }
    badge.classList.remove("text-bg-secondary", "text-bg-success", "text-bg-warning");
    if (!endpointEnabled) {
        badge.classList.add("text-bg-secondary");
        setText(badge, "Endpoint disabled");
        return;
    }
    if (!reviewed) {
        badge.classList.add("text-bg-secondary");
        setText(badge, "Not reviewed");
        return;
    }
    if (approved) {
        badge.classList.add("text-bg-success");
        setText(badge, "Approved");
        return;
    }
    badge.classList.add("text-bg-warning");
    setText(badge, "Reviewed, not approved");
}

function permissionDeniedMessage() {
    return (
        "Approval was refused. Grant sensitive-data access to your account, ensure you " +
        "have independent view and change permission on this endpoint, and use a " +
        "write-enabled login or API token before approving again."
    );
}

function conflictMessage(payload) {
    const detail = safeDetailMessage(payload);
    if (detail) {
        return detail;
    }
    return (
        "The connection target changed since review. Select Review again, verify the " +
        "updated target, then approve the new fingerprint."
    );
}

function clearTargetFields(panel) {
    for (const field of TARGET_FIELDS) {
        const cell = panel.querySelector(`[data-proxbox-connection-authority-field="${field}"]`);
        setText(cell, "—");
    }
}

function renderTarget(panel, target) {
    for (const field of TARGET_FIELDS) {
        const cell = panel.querySelector(`[data-proxbox-connection-authority-field="${field}"]`);
        setText(cell, formatFieldValue(field, target));
    }
}

function canEnableApprove(panel, state) {
    return (
        state.endpointEnabled &&
        state.canChange &&
        state.reviewedFingerprint !== null &&
        !state.serverApproved &&
        !state.reviewInFlight &&
        !state.approveInFlight
    );
}

function syncApproveButton(panel, state) {
    const approveButton = panel.querySelector("[data-proxbox-connection-authority-approve]");
    if (!approveButton) {
        return;
    }
    approveButton.disabled = !canEnableApprove(panel, state);
}

function createAuthorityRequestDeadline(deadlineMs) {
    let timeoutId;
    const deadline = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
            const error = new Error("connection-authority-deadline");
            error.name = "ConnectionAuthorityDeadlineError";
            reject(error);
        }, deadlineMs);
    });
    return {
        race(promise) {
            return Promise.race([promise, deadline]);
        },
        clear() {
            if (timeoutId !== undefined) {
                clearTimeout(timeoutId);
                timeoutId = undefined;
            }
        },
    };
}

async function readJsonResponse(response) {
    try {
        return await response.json();
    } catch (error) {
        return null;
    }
}

async function fetchAuthority(request, url, init, deadlineMs) {
    const controller = new AbortController();
    const deadline = createAuthorityRequestDeadline(deadlineMs);
    try {
        const response = await deadline.race(
            request(url, {
                ...FETCH_OPTIONS,
                ...init,
                signal: controller.signal,
                headers: {
                    Accept: "application/json",
                    ...(init.headers || {}),
                },
            }),
        );
        const payload = await deadline.race(readJsonResponse(response));
        return { response, payload };
    } finally {
        deadline.clear();
        controller.abort();
    }
}

export function initConnectionAuthority(panel, request = fetch, options = {}) {
    if (!panel || !panel.dataset.authorityUrl) {
        return;
    }

    const requestDeadlineMs =
        typeof options.requestDeadlineMs === "number"
            ? options.requestDeadlineMs
            : AUTHORITY_REQUEST_DEADLINE_MS;

    const state = {
        endpointEnabled: panel.dataset.endpointEnabled === "true",
        canChange: panel.dataset.canChange === "true",
        reviewedFingerprint: null,
        serverApproved: false,
        reviewInFlight: false,
        approveInFlight: false,
    };

    const statusEl = panel.querySelector("[data-proxbox-connection-authority-status]");
    const badgeEl = panel.querySelector("[data-proxbox-connection-authority-approved-badge]");
    const reviewButton = panel.querySelector("[data-proxbox-connection-authority-review]");
    const approveButton = panel.querySelector("[data-proxbox-connection-authority-approve]");

    function resetReviewState() {
        state.reviewedFingerprint = null;
        state.serverApproved = false;
        clearTargetFields(panel);
        setApprovedBadge(badgeEl, {
            endpointEnabled: state.endpointEnabled,
            approved: false,
            reviewed: false,
        });
        syncApproveButton(panel, state);
    }

    function applySuccessfulReview(data) {
        state.reviewedFingerprint = data.target_fingerprint;
        state.serverApproved = data.approved;
        renderTarget(panel, data.target);
        setApprovedBadge(badgeEl, {
            endpointEnabled: state.endpointEnabled,
            approved: data.approved,
            reviewed: true,
        });
        syncApproveButton(panel, state);
    }

    async function runReview() {
        if (state.reviewInFlight || state.approveInFlight) {
            return;
        }
        state.reviewInFlight = true;
        if (reviewButton) {
            reviewButton.disabled = true;
        }
        syncApproveButton(panel, state);
        setText(statusEl, "Loading the current connection target…");

        try {
            const { response, payload } = await fetchAuthority(
                request,
                panel.dataset.authorityUrl,
                { method: "GET" },
                requestDeadlineMs,
            );
            if (!response.ok) {
                resetReviewState();
                if (response.status === 403) {
                    setText(statusEl, permissionDeniedMessage());
                } else {
                    setText(
                        statusEl,
                        safeDetailMessage(payload) ||
                            "Unable to load the connection target. Try again after refreshing the page.",
                    );
                }
                return;
            }
            const data = validateAuthorityPayload(payload);
            if (!data) {
                resetReviewState();
                setText(statusEl, "The server returned an invalid connection-target review payload.");
                return;
            }
            applySuccessfulReview(data);
            if (data.approved) {
                setText(
                    statusEl,
                    "The reviewed target matches the approved fingerprint. Credential transmission may proceed when other gates allow it.",
                );
            } else {
                setText(
                    statusEl,
                    "Review complete. Approve the reviewed target to authorize credential transmission.",
                );
            }
        } catch (error) {
            resetReviewState();
            setText(
                statusEl,
                "Unable to load the connection target. Check your network connection and try again.",
            );
        } finally {
            state.reviewInFlight = false;
            if (reviewButton) {
                reviewButton.disabled = false;
            }
            syncApproveButton(panel, state);
        }
    }

    function beginApproveAttempt() {
        state.approveInFlight = true;
        if (approveButton) {
            approveButton.disabled = true;
        }
        if (reviewButton) {
            reviewButton.disabled = true;
        }
        setText(statusEl, "Submitting approval for the reviewed target…");
    }

    function finishApproveAttempt() {
        state.approveInFlight = false;
        if (reviewButton) {
            reviewButton.disabled = false;
        }
        syncApproveButton(panel, state);
    }

    function handleApproveHttpFailure(response, payload) {
        if (response.status === 409) {
            resetReviewState();
            setText(statusEl, conflictMessage(payload));
            return true;
        }
        if (response.status === 403) {
            resetReviewState();
            setText(statusEl, permissionDeniedMessage());
            return true;
        }
        if (!response.ok) {
            resetReviewState();
            setText(
                statusEl,
                safeDetailMessage(payload) || "Approval failed. Review the target and try again.",
            );
            return true;
        }
        return false;
    }

    function handleApprovePayload(fingerprint, payload) {
        const data = validateAuthorityPayload(payload);
        if (!data || !data.approved || data.target_fingerprint !== fingerprint) {
            resetReviewState();
            setText(statusEl, "The server returned an invalid approval response. Review the target again.");
            return false;
        }
        applySuccessfulReview(data);
        setText(
            statusEl,
            "The reviewed target is approved. Credential transmission may proceed when other gates allow it.",
        );
        return true;
    }

    async function runApprove() {
        if (
            state.approveInFlight ||
            state.reviewInFlight ||
            !state.reviewedFingerprint ||
            !canEnableApprove(panel, state)
        ) {
            return;
        }
        const fingerprint = state.reviewedFingerprint;
        beginApproveAttempt();

        try {
            const csrfToken = readCsrfToken(panel);
            const { response, payload } = await fetchAuthority(
                request,
                panel.dataset.authorityUrl,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken,
                    },
                    body: JSON.stringify({ target_fingerprint: fingerprint }),
                },
                requestDeadlineMs,
            );
            if (handleApproveHttpFailure(response, payload)) {
                return;
            }
            handleApprovePayload(fingerprint, payload);
        } catch (error) {
            resetReviewState();
            setText(statusEl, "Approval could not be completed. Review the target and try again.");
        } finally {
            finishApproveAttempt();
        }
    }

    if (reviewButton) {
        reviewButton.addEventListener("click", () => {
            runReview();
        });
    }
    if (approveButton) {
        approveButton.addEventListener("click", () => {
            runApprove();
        });
    }

    setApprovedBadge(badgeEl, {
        endpointEnabled: state.endpointEnabled,
        approved: false,
        reviewed: false,
    });
    syncApproveButton(panel, state);
}

if (typeof document !== "undefined") {
    document.querySelectorAll("[data-proxbox-connection-authority-panel]").forEach((panel) => {
        initConnectionAuthority(panel);
    });
}

export { AUTHORITY_REQUEST_DEADLINE_MS };
