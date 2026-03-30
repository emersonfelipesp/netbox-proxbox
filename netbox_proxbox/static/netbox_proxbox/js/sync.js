export function createTdElement(type, name, field, innerHTML) {
    const cell = document.createElement("td");
    cell.dataset.objectType = type;
    cell.dataset.objectName = name ?? "";
    cell.dataset.field = field;
    cell.innerHTML = innerHTML ?? "";
    return cell;
}

export function setBadgeState(element, status, detail = "") {
    if (!element) {
        return;
    }

    const styles = {
        success: "badge text-bg-green",
        error: "badge text-bg-red",
        unknown: "badge text-bg-grey",
    };
    const labels = {
        success: "Successful!",
        error: "Error!",
        unknown: "Unknown",
    };

    element.className = styles[status] ?? styles.unknown;
    element.textContent = labels[status] ?? labels.unknown;

    const tooltip = typeof detail === "string" ? detail.trim() : "";
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

export async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            Accept: "application/json",
            ...options.headers,
        },
        ...options,
    });

    let payload = {};
    try {
        payload = await response.json();
    } catch (error) {
        payload = {};
    }

    if (!response.ok) {
        throw new Error(payload.detail || `Request failed with status ${response.status}`);
    }

    return payload;
}

export function getCsrfToken() {
    const csrfInput = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (csrfInput?.value) {
        return csrfInput.value;
    }

    const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrftoken="));
    return csrfCookie ? csrfCookie.split("=", 2)[1] : "";
}

export function parseSSEFrame(rawFrame) {
    const lines = rawFrame.split("\n");
    let event = "message";
    let data = null;
    for (const line of lines) {
        if (line.startsWith("event:")) {
            event = line.slice(6).trim();
            continue;
        }
        if (line.startsWith("data:")) {
            const raw = line.slice(5).trim();
            try {
                data = JSON.parse(raw);
            } catch {
                data = { message: raw };
            }
        }
    }
    return { event, data };
}

export function normalizeSSEMessage(sseData) {
    if (!sseData || typeof sseData !== "object") {
        return null;
    }
    const payload = sseData.payload;
    if (!payload || typeof payload !== "object") {
        return null;
    }
    return {
        object: payload.object || sseData.step,
        data: {
            ...payload.data,
            rowid: sseData.rowid || payload.data?.rowid || payload.data?.name,
        },
        end: sseData.status === "completed",
    };
}
