/**
 * Backend Logs page JavaScript
 * - Non-blocking fetch with AbortController (cancels stale requests)
 * - SSE live streaming via EventSource (falls back to polling)
 * - Incremental DOM updates — no full re-render during live mode
 */

class LogsPage {
    constructor() {
        this.config = window.proxboxLogsConfig || {};
        this.logsApiUrl = this.config.logsApiUrl || "";
        this.sseStreamUrl = this.config.sseStreamUrl || "";
        this.saveLogPathUrl = this.config.saveLogPathUrl || "";
        this.backendLogFilePath = this.config.backendLogFilePath || "/var/log/proxbox.log";

        this.displayedLogs = [];
        this.currentTab = "all";
        this.currentLevel = "";
        this.currentOperationId = "";
        this.currentFromDate = "";
        this.currentToDate = "";

        // Fetch state — AbortController replaces isLoading mutex
        this.currentFetchController = null;
        this.operationIdFetchTimer = null;

        // Auto-refresh (polling fallback)
        this.autoRefreshInterval = 5000;
        this.autoRefreshTimer = null;
        this.isAutoRefreshEnabled = true;

        // Cursor-based pagination
        this.newestLoadedId = null;
        this.oldestLoadedId = null;
        this.canLoadMoreOlder = false;
        this.limit = 200;
        this.total = 0;

        // SSE
        this.sseSource = null;
        this.connectionMode = "disconnected"; // "live" | "polling" | "disconnected"

        this.init();
    }

    init() {
        this.bindEvents();
        this.hydrateBackendLogPathInput();
        this.updateTabState();
        this.updateLevelFilterState();
        this.fetchLogs({ reset: true }).then(() => {
            if (this.isAutoRefreshEnabled) {
                this.connectSSE();
            }
        });
    }

    bindEvents() {
        document.querySelectorAll("[data-log-tab]").forEach((button) => {
            button.addEventListener("click", () => this.setTab(button.dataset.logTab || "all"));
        });

        document.getElementById("refreshBtn")?.addEventListener("click", () => {
            this.disconnectSSE();
            this.fetchLogs({ reset: true }).then(() => {
                if (this.isAutoRefreshEnabled) this.connectSSE();
            });
        });

        document.getElementById("copyLogsBtn")?.addEventListener("click", () => this.copyLogsToClipboard());

        document.getElementById("autoRefreshToggle")?.addEventListener("change", (e) => {
            this.isAutoRefreshEnabled = e.target.checked;
            if (this.isAutoRefreshEnabled) {
                this.connectSSE();
            } else {
                this.disconnectSSE();
                this.stopAutoRefresh();
                this.setConnectionMode("disconnected");
            }
        });

        document.getElementById("levelFilter")?.addEventListener("change", (e) => {
            this.currentLevel = e.target.value;
            if (this.currentTab !== "all") this.setTab("all", { refetch: false });
            this._resetAndReconnect();
        });

        document.getElementById("fromDateFilter")?.addEventListener("change", (e) => {
            this.currentFromDate = e.target.value;
            this._resetAndReconnect();
        });

        document.getElementById("toDateFilter")?.addEventListener("change", (e) => {
            this.currentToDate = e.target.value;
            this._resetAndReconnect();
        });

        document.getElementById("operationIdFilter")?.addEventListener("input", (e) => {
            this.currentOperationId = e.target.value.trim();
            this.scheduleOperationFetch();
        });

        document.getElementById("clearFiltersBtn")?.addEventListener("click", () => this.clearFilters());

        document.getElementById("loadMoreBtn")?.addEventListener("click", () => this.loadMore());

        document.getElementById("saveBackendLogFilePathBtn")?.addEventListener("click", () =>
            this.saveBackendLogFilePath()
        );
    }

    /** Reset logs and reconnect SSE after a filter/tab change. */
    _resetAndReconnect() {
        this.disconnectSSE();
        this.stopAutoRefresh();
        this.fetchLogs({ reset: true }).then(() => {
            if (this.isAutoRefreshEnabled) this.connectSSE();
        });
    }

    hydrateBackendLogPathInput() {
        const input = document.getElementById("backendLogFilePathInput");
        if (input && !input.value) input.value = this.backendLogFilePath;
    }

    // ── Tab management ──────────────────────────────────────────────────────

    setTab(tabKey, options = {}) {
        const nextTab = tabKey === "errors" ? "errors" : "all";
        if (this.currentTab === nextTab) return;
        this.currentTab = nextTab;
        this.updateTabState();
        this.updateLevelFilterState();
        if (options.refetch !== false) this._resetAndReconnect();
    }

    updateTabState() {
        document.querySelectorAll("[data-log-tab]").forEach((button) => {
            const isActive = (button.dataset.logTab || "all") === this.currentTab;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
            button.tabIndex = isActive ? 0 : -1;
        });
    }

    updateLevelFilterState() {
        const levelFilter = document.getElementById("levelFilter");
        if (!levelFilter) return;
        const disabled = this.isErrorsTab();
        levelFilter.disabled = disabled;
        levelFilter.setAttribute("aria-disabled", disabled ? "true" : "false");
    }

    isErrorsTab() {
        return this.currentTab === "errors";
    }

    // ── Request helpers ──────────────────────────────────────────────────────

    buildRequestParams({ direction = "initial" } = {}) {
        const params = new URLSearchParams();
        if (this.isErrorsTab()) {
            params.append("errors_only", "true");
        } else if (this.currentLevel) {
            params.append("level", this.currentLevel);
        }
        if (this.currentOperationId) params.append("operation_id", this.currentOperationId);
        if (this.currentFromDate) {
            params.append("since", new Date(this.currentFromDate).toISOString());
        }
        if (direction === "newer" && this.newestLoadedId) {
            params.append("newer_than_id", this.newestLoadedId);
        }
        if (direction === "older" && this.oldestLoadedId) {
            params.append("older_than_id", this.oldestLoadedId);
        }
        params.append("limit", this.limit.toString());
        return params;
    }

    applyClientSideFilters(logs) {
        if (!this.currentToDate) return logs;
        const toDate = new Date(this.currentToDate).getTime();
        if (Number.isNaN(toDate)) return logs;
        return logs.filter((log) => new Date(log.timestamp).getTime() <= toDate);
    }

    // ── Cursor helpers ───────────────────────────────────────────────────────

    setLoadedWindowFromLogs(rawLogs) {
        if (!rawLogs.length) { this.newestLoadedId = null; this.oldestLoadedId = null; return; }
        this.newestLoadedId = rawLogs[0].id || null;
        this.oldestLoadedId = rawLogs[rawLogs.length - 1].id || null;
    }

    extendNewestCursor(rawLogs) {
        if (rawLogs.length) this.newestLoadedId = rawLogs[0].id || this.newestLoadedId;
    }

    extendOldestCursor(rawLogs) {
        if (rawLogs.length) this.oldestLoadedId = rawLogs[rawLogs.length - 1].id || this.oldestLoadedId;
    }

    sortLogsDescending(logs) {
        return [...logs].sort((a, b) => {
            const idA = Number.parseInt(a.id || "", 10);
            const idB = Number.parseInt(b.id || "", 10);
            if (!Number.isNaN(idA) && !Number.isNaN(idB) && idA !== idB) return idB - idA;
            return new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime();
        });
    }

    // ── Fetch (HTTP polling) ─────────────────────────────────────────────────

    async fetchLogs({ reset = true, isAutoRefresh = false } = {}) {
        if (!this.logsApiUrl) {
            this.showError("Logs API URL not configured");
            return;
        }

        // Cancel any in-flight request
        if (this.currentFetchController) {
            this.currentFetchController.abort();
        }
        this.currentFetchController = new AbortController();

        this.stopOperationFetch();

        // Only show full-page spinner on initial empty load
        if (reset && this.displayedLogs.length === 0) {
            this.showLoadingRow();
        }
        this.hideError();

        try {
            const direction = isAutoRefresh ? "newer" : "initial";
            const params = this.buildRequestParams({ direction });
            const response = await fetch(`${this.logsApiUrl}?${params.toString()}`, {
                headers: { Accept: "application/json" },
                signal: this.currentFetchController.signal,
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

            const data = await response.json();
            const rawLogs = data.logs || [];
            const filteredLogs = this.applyClientSideFilters(rawLogs);

            if (reset) {
                this.displayedLogs = filteredLogs;
                this.setLoadedWindowFromLogs(rawLogs);
                this.canLoadMoreOlder = Boolean(data.has_more);
                this.total = data.total || this.displayedLogs.length;
                this.renderLogs();
            } else if (isAutoRefresh) {
                if (rawLogs.length > 0) {
                    this.displayedLogs = [...filteredLogs, ...this.displayedLogs];
                    this.extendNewestCursor(rawLogs);
                    this.total += rawLogs.length;
                    this.renderNewEntries(filteredLogs);
                }
            } else {
                this.displayedLogs = filteredLogs;
                this.setLoadedWindowFromLogs(rawLogs);
                this.canLoadMoreOlder = Boolean(data.has_more);
                this.total = data.total || this.displayedLogs.length;
                this.renderLogs();
            }

            this.updateLogCount();
            this.updateFilterIndicator(data.active_filters);
            this.updateLoadMoreState();

            if (this.isAutoRefreshEnabled && !this.sseSource) {
                this.startAutoRefresh();
            }
        } catch (error) {
            if (error.name === "AbortError") return; // request was intentionally cancelled
            console.error("Failed to fetch logs:", error);
            this.showError(error.message || "Failed to fetch logs");
        } finally {
            this.currentFetchController = null;
            this.hideLoadingRow();
        }
    }

    async loadMore() {
        if (!this.canLoadMoreOlder || !this.oldestLoadedId) return;
        if (!this.logsApiUrl) return;

        if (this.currentFetchController) this.currentFetchController.abort();
        this.currentFetchController = new AbortController();
        this.hideError();

        try {
            const params = this.buildRequestParams({ direction: "older" });
            const response = await fetch(`${this.logsApiUrl}?${params.toString()}`, {
                headers: { Accept: "application/json" },
                signal: this.currentFetchController.signal,
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

            const data = await response.json();
            const rawLogs = data.logs || [];
            const filteredLogs = this.applyClientSideFilters(rawLogs);

            this.displayedLogs = [...this.displayedLogs, ...filteredLogs];
            this.extendOldestCursor(rawLogs);
            this.canLoadMoreOlder = Boolean(data.has_more);
            this.total = data.total || this.displayedLogs.length;

            this.renderLogs();
            this.updateLogCount();
            this.updateFilterIndicator(data.active_filters);
            this.updateLoadMoreState();
        } catch (error) {
            if (error.name === "AbortError") return;
            console.error("Failed to load more logs:", error);
            this.showError(error.message || "Failed to load more logs");
        } finally {
            this.currentFetchController = null;
        }
    }

    // ── SSE live streaming ───────────────────────────────────────────────────

    connectSSE() {
        if (!this.sseStreamUrl || this.sseSource) return;

        const params = new URLSearchParams();
        if (this.isErrorsTab()) {
            params.set("errors_only", "true");
        } else if (this.currentLevel) {
            params.set("level", this.currentLevel);
        }
        if (this.currentOperationId) params.set("operation_id", this.currentOperationId);
        if (this.newestLoadedId) params.set("newer_than_id", this.newestLoadedId);

        const url = `${this.sseStreamUrl}?${params.toString()}`;
        this.sseSource = new EventSource(url);

        this.sseSource.addEventListener("log", (e) => {
            try {
                const entry = JSON.parse(e.data);
                const filtered = this.applyClientSideFilters([entry]);
                if (filtered.length > 0) {
                    this.displayedLogs = [...filtered, ...this.displayedLogs];
                    try {
                        const entryId = String(entry.id);
                        if (!this.newestLoadedId || Number(entryId) > Number(this.newestLoadedId)) {
                            this.newestLoadedId = entryId;
                        }
                    } catch (_) { /* ignore */ }
                    this.total += 1;
                    this.renderNewEntries(filtered);
                    this.updateLogCount();
                }
            } catch (err) {
                console.warn("Failed to parse SSE log entry:", err);
            }
        });

        this.sseSource.addEventListener("open", () => {
            this.setConnectionMode("live");
            this.stopAutoRefresh();
        });

        this.sseSource.addEventListener("error", () => {
            this.disconnectSSE();
            if (this.isAutoRefreshEnabled) {
                this.setConnectionMode("polling");
                this.startAutoRefresh();
            } else {
                this.setConnectionMode("disconnected");
            }
        });
    }

    disconnectSSE() {
        if (this.sseSource) {
            this.sseSource.close();
            this.sseSource = null;
        }
    }

    setConnectionMode(mode) {
        this.connectionMode = mode;
        const badge = document.getElementById("connectionStatus");
        const label = document.getElementById("connectionModeLabel");
        if (!badge || !label) return;

        badge.className = `badge logs-status-badge ${mode}`;
        const labels = { live: "Live", polling: "Polling", disconnected: "Disconnected" };
        label.textContent = labels[mode] || mode;
    }

    // ── Auto-refresh (polling fallback) ──────────────────────────────────────

    startAutoRefresh() {
        this.stopAutoRefresh();
        if (this.isAutoRefreshEnabled) {
            this.autoRefreshTimer = window.setInterval(() => {
                this.fetchLogs({ reset: false, isAutoRefresh: true });
            }, this.autoRefreshInterval);
        }
    }

    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    scheduleOperationFetch() {
        if (this.operationIdFetchTimer) clearTimeout(this.operationIdFetchTimer);
        this.operationIdFetchTimer = window.setTimeout(() => {
            this.operationIdFetchTimer = null;
            this._resetAndReconnect();
        }, 300);
    }

    stopOperationFetch() {
        if (this.operationIdFetchTimer) {
            clearTimeout(this.operationIdFetchTimer);
            this.operationIdFetchTimer = null;
        }
    }

    // ── Rendering ────────────────────────────────────────────────────────────

    renderLogs() {
        const tbody = document.getElementById("logsTableBody");
        const noLogsMessage = document.getElementById("noLogsMessage");
        if (!tbody) return;

        tbody.innerHTML = "";
        if (this.displayedLogs.length === 0) {
            if (noLogsMessage) noLogsMessage.style.display = "block";
            this.updateCopyButtonState();
            return;
        }
        if (noLogsMessage) noLogsMessage.style.display = "none";

        const sorted = this.sortLogsDescending(this.displayedLogs);
        const frag = document.createDocumentFragment();
        for (const log of sorted) frag.appendChild(this.buildLogRow(log));
        tbody.appendChild(frag);

        this.updateCopyButtonState();
    }

    /** Prepend new entries to the existing tbody without a full re-render. */
    renderNewEntries(entries) {
        if (!entries.length) return;
        const tbody = document.getElementById("logsTableBody");
        const noLogsMessage = document.getElementById("noLogsMessage");
        if (!tbody) return;

        if (noLogsMessage) noLogsMessage.style.display = "none";

        // New entries arrive newest-first; insert in reverse to keep chronological order at top
        const sorted = this.sortLogsDescending(entries);
        const firstExisting = tbody.firstChild;
        for (const log of sorted) {
            const row = this.buildLogRow(log);
            row.classList.add("log-entry-new");
            tbody.insertBefore(row, firstExisting);
        }
        this.updateCopyButtonState();
    }

    buildLogRow(log) {
        const row = document.createElement("tr");
        const levelClass = String(log.level || "info").toLowerCase();
        row.className = `log-entry log-level-${levelClass}`;
        if (log.expandable) {
            row.classList.add("expandable");
            row.dataset.expanded = "false";
        }

        row.innerHTML = `
            <td class="log-timestamp">${this.escapeHtml(this.formatTimestamp(log.timestamp))}</td>
            <td class="log-level">
                <span class="badge bg-${this.getLevelBadgeColor(log.level)}">${this.escapeHtml(log.level || "-")}</span>
            </td>
            <td class="log-module">${this.escapeHtml(log.module)}</td>
            <td class="log-message">
                <span class="log-message-text">${this.escapeHtml(log.message)}</span>
                ${log.expandable ? '<i class="mdi mdi-chevron-down expand-icon"></i>' : ""}
            </td>
            <td class="log-operation">
                ${log.operation_id ? `<code class="operation-id">${this.escapeHtml(log.operation_id.substring(0, 8))}</code>` : "-"}
            </td>
        `;

        if (log.expandable) {
            row.addEventListener("click", () => this.toggleExpand(row, log));
            row.style.cursor = "pointer";
        }
        return row;
    }

    toggleExpand(row, log) {
        const existingDetail = row.nextElementSibling;
        if (existingDetail && existingDetail.classList.contains("log-detail-row")) {
            existingDetail.remove();
            row.dataset.expanded = "false";
            row.classList.remove("expanded");
            row.querySelector(".expand-icon")?.classList.replace("mdi-chevron-up", "mdi-chevron-down");
            return;
        }

        const detailRow = document.createElement("tr");
        detailRow.className = "log-detail-row";
        detailRow.innerHTML = `
            <td colspan="5" class="p-0">
                <div class="log-detail-content">
                    <div class="p-3 bg-light border-top">
                        ${log.expandable?.traceback ? `
                            <h6 class="mb-2">Traceback:</h6>
                            <pre class="mb-0 small"><code>${this.escapeHtml(log.expandable.traceback)}</code></pre>
                        ` : ""}
                        ${log.operation ? `<div class="mb-2"><strong>Operation:</strong> ${this.escapeHtml(log.operation)}</div>` : ""}
                        ${log.phase ? `<div class="mb-2"><strong>Phase:</strong> ${this.escapeHtml(log.phase)}</div>` : ""}
                        ${log.resource_type && log.resource_id != null ? `<div class="mb-2"><strong>Resource:</strong> ${this.escapeHtml(log.resource_type)}#${this.escapeHtml(String(log.resource_id))}</div>` : ""}
                    </div>
                </div>
            </td>
        `;
        row.after(detailRow);
        row.dataset.expanded = "true";
        row.classList.add("expanded");
        row.querySelector(".expand-icon")?.classList.replace("mdi-chevron-down", "mdi-chevron-up");
    }

    // ── Clipboard ────────────────────────────────────────────────────────────

    copyLogsToClipboard() {
        const text = this.sortLogsDescending(this.displayedLogs)
            .map((log) => this.formatLogForClipboard(log))
            .filter(Boolean)
            .join("\n\n");
        if (!text) return;

        const copyBtn = document.getElementById("copyLogsBtn");
        const copyLabel = copyBtn?.dataset.labelCopy || "Copy to clipboard";
        const copiedLabel = copyBtn?.dataset.labelCopied || "Copied";
        const ok = () => {
            this.setCopyButtonLabel(copiedLabel);
            window.setTimeout(() => this.setCopyButtonLabel(copyLabel), 2000);
        };

        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text).then(ok).catch(() => this.fallbackCopy(text, ok));
        } else {
            this.fallbackCopy(text, ok);
        }
    }

    fallbackCopy(text, onSuccess) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(textarea);
        textarea.select();
        try { if (document.execCommand("copy")) onSuccess(); }
        catch (err) { console.error("Failed to copy logs:", err); }
        finally { document.body.removeChild(textarea); }
    }

    formatLogForClipboard(log) {
        if (!log) return "";
        const header = `[${this.formatTimestamp(log.timestamp)}] ${log.level || "-"} ${log.module || "-"}`;
        const operationId = log.operation_id ? ` op=${log.operation_id}` : "";
        const message = log.message || "";
        const summary = message ? `${header}${operationId} - ${message}` : `${header}${operationId}`;
        const details = [];
        if (log.operation) details.push(`Operation: ${log.operation}`);
        if (log.phase) details.push(`Phase: ${log.phase}`);
        if (log.resource_type && log.resource_id != null) details.push(`Resource: ${log.resource_type}#${log.resource_id}`);
        if (log.expandable?.traceback) details.push(log.expandable.traceback.trim());
        return [summary, ...details].join("\n");
    }

    // ── UI state helpers ─────────────────────────────────────────────────────

    showLoadingRow() {
        const row = document.getElementById("loadingRow");
        if (row) row.style.display = "";
    }

    hideLoadingRow() {
        const row = document.getElementById("loadingRow");
        if (row) row.style.display = "none";
    }

    showError(message) {
        const el = document.getElementById("errorMessage");
        const text = document.getElementById("errorText");
        if (el) el.style.display = "block";
        if (text) text.textContent = message;
        this.hideLoadMore();
        this.updateCopyButtonState();
        this.hideLoadingRow();
    }

    hideError() {
        const el = document.getElementById("errorMessage");
        if (el) el.style.display = "none";
    }

    showLoadMore() {
        const btn = document.getElementById("loadMoreBtn");
        if (btn) btn.style.display = "";
    }

    hideLoadMore() {
        const btn = document.getElementById("loadMoreBtn");
        if (btn) btn.style.display = "none";
    }

    updateLoadMoreState() {
        if (this.canLoadMoreOlder && Boolean(this.oldestLoadedId)) this.showLoadMore();
        else this.hideLoadMore();
    }

    updateLogCount() {
        const countEl = document.getElementById("logCount");
        const totalEl = document.getElementById("totalCount");
        if (countEl) countEl.textContent = this.displayedLogs.length;
        if (totalEl) {
            if (this.total !== this.displayedLogs.length) {
                totalEl.textContent = ` (${this.total} total)`;
                totalEl.style.display = "inline";
            } else {
                totalEl.textContent = "";
                totalEl.style.display = "none";
            }
        }
    }

    updateFilterIndicator(activeFilters) {
        const badge = document.getElementById("activeFiltersBadge");
        if (!badge) return;
        const filters = [];
        if (this.isErrorsTab() || activeFilters?.errors_only) filters.push("Errors");
        if (!this.isErrorsTab() && this.currentLevel) filters.push(`Client: level=${this.currentLevel}`);
        if (this.currentOperationId) filters.push(`Backend: operation=${this.currentOperationId.substring(0, 8)}`);
        else if (activeFilters?.operation_id) filters.push(`Backend: operation=${String(activeFilters.operation_id).substring(0, 8)}`);

        if (filters.length > 0) {
            badge.textContent = filters.join(" | ");
            badge.style.display = "inline";
        } else {
            badge.style.display = "none";
        }
    }

    updateCopyButtonState() {
        const btn = document.getElementById("copyLogsBtn");
        if (btn) btn.disabled = this.displayedLogs.length === 0;
    }

    setCopyButtonLabel(label) {
        const btn = document.getElementById("copyLogsBtn");
        if (!btn) return;
        const el = btn.querySelector("[data-copy-label]") || btn;
        el.textContent = label;
    }

    clearFilters() {
        this.currentLevel = "";
        this.currentOperationId = "";
        this.currentFromDate = "";
        this.currentToDate = "";
        const ids = ["levelFilter", "operationIdFilter", "fromDateFilter", "toDateFilter"];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) el.value = "";
        }
        this.updateLevelFilterState();
        this._resetAndReconnect();
    }

    // ── Formatting ───────────────────────────────────────────────────────────

    formatTimestamp(timestamp) {
        if (!timestamp) return "-";
        try {
            const d = new Date(timestamp);
            return Number.isNaN(d.getTime()) ? timestamp : d.toLocaleString();
        } catch { return timestamp; }
    }

    getLevelBadgeColor(level) {
        const colors = { DEBUG: "secondary", INFO: "primary", WARNING: "warning", ERROR: "danger", CRITICAL: "danger" };
        return colors[level] || "secondary";
    }

    escapeHtml(text) {
        if (text === null || text === undefined) return "";
        const div = document.createElement("div");
        div.textContent = String(text);
        return div.innerHTML;
    }

    // ── Log path save ────────────────────────────────────────────────────────

    getCsrfToken() {
        const csrfInput = document.querySelector("input[name='csrfmiddlewaretoken']");
        if (csrfInput?.value) return csrfInput.value;
        const cookie = document.cookie.split(";").map((p) => p.trim()).find((p) => p.startsWith("csrftoken="));
        return cookie ? cookie.split("=", 2)[1] : "";
    }

    setBackendLogFilePathStatus(message, level = "muted") {
        const el = document.getElementById("backendLogFilePathStatus");
        if (!el) return;
        el.className = `small mt-1 text-${level}`;
        el.textContent = message;
    }

    async saveBackendLogFilePath() {
        const input = document.getElementById("backendLogFilePathInput");
        const saveBtn = document.getElementById("saveBackendLogFilePathBtn");
        if (!input || !saveBtn) return;

        const candidatePath = input.value.trim();
        if (!candidatePath) {
            this.setBackendLogFilePathStatus("Backend log file path is required.", "danger");
            return;
        }
        if (!candidatePath.startsWith("/")) {
            this.setBackendLogFilePathStatus(
                "Backend log file path must be absolute (for example /var/log/proxbox.log).",
                "danger"
            );
            return;
        }
        if (!this.saveLogPathUrl) {
            this.setBackendLogFilePathStatus("Save endpoint is not configured.", "danger");
            return;
        }

        saveBtn.disabled = true;
        this.setBackendLogFilePathStatus("Saving…", "muted");

        try {
            const payload = new URLSearchParams();
            payload.set("backend_log_file_path", candidatePath);

            const response = await fetch(this.saveLogPathUrl, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": this.getCsrfToken(),
                },
                body: payload.toString(),
            });

            let data = {};
            try { data = await response.json(); } catch { data = {}; }

            if (!response.ok || data.ok !== true) {
                throw new Error(data.error || data.detail || `Failed (HTTP ${response.status}).`);
            }
            this.backendLogFilePath = data.backend_log_file_path || candidatePath;
            input.value = this.backendLogFilePath;
            this.setBackendLogFilePathStatus(
                data.message || "Saved. Changes apply after proxbox-api restart.",
                "success"
            );
        } catch (error) {
            this.setBackendLogFilePathStatus(error.message || "Failed to save.", "danger");
        } finally {
            saveBtn.disabled = false;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new LogsPage();
});
