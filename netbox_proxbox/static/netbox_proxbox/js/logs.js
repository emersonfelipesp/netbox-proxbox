/**
 * Backend Logs page JavaScript
 * Handles fetching, filtering, tab switching, cursor-based pagination, and copying logs.
 */

class LogsPage {
    constructor() {
        this.config = window.proxboxLogsConfig || {};
        this.logsApiUrl = this.config.logsApiUrl || "";
        this.displayedLogs = [];
        this.currentTab = "all";
        this.currentLevel = "";
        this.currentOperationId = "";
        this.currentFromDate = "";
        this.currentToDate = "";
        this.autoRefreshInterval = 5000;
        this.autoRefreshTimer = null;
        this.operationIdFetchTimer = null;
        this.isAutoRefreshEnabled = true;
        this.newestLoadedId = null;
        this.oldestLoadedId = null;
        this.canLoadMoreOlder = false;
        this.limit = 200;
        this.total = 0;
        this.isLoading = false;

        this.init();
    }

    init() {
        this.bindEvents();
        this.updateTabState();
        this.updateLevelFilterState();
        this.fetchLogs({ reset: true });
    }

    bindEvents() {
        const refreshBtn = document.getElementById("refreshBtn");
        const copyBtn = document.getElementById("copyLogsBtn");
        const autoRefreshToggle = document.getElementById("autoRefreshToggle");
        const levelFilter = document.getElementById("levelFilter");
        const fromDateFilter = document.getElementById("fromDateFilter");
        const toDateFilter = document.getElementById("toDateFilter");
        const operationIdFilter = document.getElementById("operationIdFilter");
        const clearFiltersBtn = document.getElementById("clearFiltersBtn");
        const loadMoreBtn = document.getElementById("loadMoreBtn");

        document.querySelectorAll("[data-log-tab]").forEach((button) => {
            button.addEventListener("click", () => {
                this.setTab(button.dataset.logTab || "all");
            });
        });

        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => this.fetchLogs({ reset: true }));
        }

        if (copyBtn) {
            copyBtn.addEventListener("click", () => this.copyLogsToClipboard());
        }

        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener("change", (e) => {
                this.isAutoRefreshEnabled = e.target.checked;
                if (this.isAutoRefreshEnabled) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }

        if (levelFilter) {
            levelFilter.addEventListener("change", (e) => {
                this.currentLevel = e.target.value;
                if (this.currentTab !== "all") {
                    this.setTab("all", { refetch: false });
                }
                this.fetchLogs({ reset: true });
            });
        }

        if (fromDateFilter) {
            fromDateFilter.addEventListener("change", (e) => {
                this.currentFromDate = e.target.value;
                this.fetchLogs({ reset: true });
            });
        }

        if (toDateFilter) {
            toDateFilter.addEventListener("change", (e) => {
                this.currentToDate = e.target.value;
                this.fetchLogs({ reset: true });
            });
        }

        if (operationIdFilter) {
            operationIdFilter.addEventListener("input", (e) => {
                this.currentOperationId = e.target.value.trim();
                this.scheduleOperationFetch();
            });
        }

        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener("click", () => this.clearFilters());
        }

        if (loadMoreBtn) {
            loadMoreBtn.addEventListener("click", () => this.loadMore());
        }
    }

    setTab(tabKey, options = {}) {
        const nextTab = tabKey === "errors" ? "errors" : "all";
        if (this.currentTab === nextTab) {
            return;
        }

        this.currentTab = nextTab;
        this.updateTabState();
        this.updateLevelFilterState();

        if (options.refetch === false) {
            return;
        }

        this.fetchLogs({ reset: true });
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
        if (!levelFilter) {
            return;
        }

        const disabled = this.isErrorsTab();
        levelFilter.disabled = disabled;
        levelFilter.setAttribute("aria-disabled", disabled ? "true" : "false");
    }

    isErrorsTab() {
        return this.currentTab === "errors";
    }

    buildRequestParams({ direction = "initial" } = {}) {
        const params = new URLSearchParams();

        if (this.isErrorsTab()) {
            params.append("errors_only", "true");
        } else if (this.currentLevel) {
            params.append("level", this.currentLevel);
        }

        if (this.currentOperationId) {
            params.append("operation_id", this.currentOperationId);
        }

        if (this.currentFromDate) {
            const fromDate = new Date(this.currentFromDate);
            params.append("since", fromDate.toISOString());
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
        if (!this.currentToDate) {
            return logs;
        }

        const toDate = new Date(this.currentToDate).getTime();
        if (Number.isNaN(toDate)) {
            return logs;
        }

        return logs.filter((log) => {
            const logTime = new Date(log.timestamp).getTime();
            return logTime <= toDate;
        });
    }

    setLoadedWindowFromLogs(rawLogs) {
        if (!rawLogs.length) {
            this.newestLoadedId = null;
            this.oldestLoadedId = null;
            return;
        }

        this.newestLoadedId = rawLogs[0].id || null;
        this.oldestLoadedId = rawLogs[rawLogs.length - 1].id || null;
    }

    extendNewestCursor(rawLogs) {
        if (!rawLogs.length) {
            return;
        }

        this.newestLoadedId = rawLogs[0].id || this.newestLoadedId;
    }

    extendOldestCursor(rawLogs) {
        if (!rawLogs.length) {
            return;
        }

        this.oldestLoadedId = rawLogs[rawLogs.length - 1].id || this.oldestLoadedId;
    }

    sortLogsDescending(logs) {
        return [...logs].sort((a, b) => {
            const idA = Number.parseInt(a.id || "", 10);
            const idB = Number.parseInt(b.id || "", 10);

            if (!Number.isNaN(idA) && !Number.isNaN(idB) && idA !== idB) {
                return idB - idA;
            }

            const timeA = new Date(a.timestamp || 0).getTime();
            const timeB = new Date(b.timestamp || 0).getTime();
            return timeB - timeA;
        });
    }

    async fetchLogs({ reset = true, isAutoRefresh = false } = {}) {
        if (this.isLoading) return;
        if (!this.logsApiUrl) {
            this.showError("Logs API URL not configured");
            return;
        }

        this.stopOperationFetch();
        this.isLoading = true;
        this.showLoading();
        this.hideError();

        try {
            const direction = isAutoRefresh ? "newer" : "initial";
            const params = this.buildRequestParams({ direction });
            const response = await fetch(`${this.logsApiUrl}?${params.toString()}`, {
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            const rawLogs = data.logs || [];
            const filteredLogs = this.applyClientSideFilters(rawLogs);

            if (reset) {
                this.displayedLogs = filteredLogs;
                this.setLoadedWindowFromLogs(rawLogs);
                this.canLoadMoreOlder = Boolean(data.has_more);
                this.total = data.total || this.displayedLogs.length;
            } else if (isAutoRefresh) {
                if (rawLogs.length > 0) {
                    this.displayedLogs = [...filteredLogs, ...this.displayedLogs];
                    this.extendNewestCursor(rawLogs);
                    this.total += rawLogs.length;
                }
            } else {
                this.displayedLogs = filteredLogs;
                this.setLoadedWindowFromLogs(rawLogs);
                this.canLoadMoreOlder = Boolean(data.has_more);
                this.total = data.total || this.displayedLogs.length;
            }

            this.renderLogs();
            this.updateLogCount();
            this.updateFilterIndicator(data.active_filters);
            this.updateLoadMoreState();

            if (this.isAutoRefreshEnabled) {
                this.startAutoRefresh();
            }
        } catch (error) {
            console.error("Failed to fetch logs:", error);
            this.showError(error.message || "Failed to fetch logs");
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    async loadMore() {
        if (this.isLoading) return;
        if (!this.canLoadMoreOlder || !this.oldestLoadedId) return;

        this.isLoading = true;
        this.hideError();

        try {
            const params = this.buildRequestParams({
                direction: "older",
            });
            const response = await fetch(`${this.logsApiUrl}?${params.toString()}`, {
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

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
            console.error("Failed to load more logs:", error);
            this.showError(error.message || "Failed to load more logs");
        } finally {
            this.isLoading = false;
        }
    }

    renderLogs() {
        const tbody = document.getElementById("logsTableBody");
        const noLogsMessage = document.getElementById("noLogsMessage");

        if (!tbody || !noLogsMessage) return;

        tbody.innerHTML = "";

        if (this.displayedLogs.length === 0) {
            noLogsMessage.style.display = "block";
            this.updateCopyButtonState();
            return;
        }

        noLogsMessage.style.display = "none";

        const sortedLogs = this.sortLogsDescending(this.displayedLogs);

        sortedLogs.forEach((log) => {
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

            tbody.appendChild(row);
        });

        this.updateCopyButtonState();
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
                <div class="log-detail-content" style="display: none;">
                    <div class="p-3 bg-light border-top">
                        ${log.expandable && log.expandable.traceback ? `
                            <h6 class="mb-2">Traceback:</h6>
                            <pre class="mb-0 small"><code>${this.escapeHtml(log.expandable.traceback)}</code></pre>
                        ` : ""}
                        ${log.operation ? `<div class="mb-2"><strong>Operation:</strong> ${this.escapeHtml(log.operation)}</div>` : ""}
                        ${log.phase ? `<div class="mb-2"><strong>Phase:</strong> ${this.escapeHtml(log.phase)}</div>` : ""}
                        ${log.resource_type && log.resource_id ? `<div class="mb-2"><strong>Resource:</strong> ${this.escapeHtml(log.resource_type)}#${this.escapeHtml(String(log.resource_id))}</div>` : ""}
                    </div>
                </div>
            </td>
        `;

        row.after(detailRow);
        const content = detailRow.querySelector(".log-detail-content");
        if (content) {
            content.style.display = "block";
        }

        row.dataset.expanded = "true";
        row.classList.add("expanded");
        const icon = row.querySelector(".expand-icon");
        if (icon) {
            icon.classList.replace("mdi-chevron-down", "mdi-chevron-up");
        }
    }

    copyLogsToClipboard() {
        const text = this.formatLogsForClipboard(this.sortLogsDescending(this.displayedLogs));
        if (!text) {
            return;
        }

        const copyBtn = document.getElementById("copyLogsBtn");
        const copyLabel = copyBtn?.dataset.labelCopy || "Copy to clipboard";
        const copiedLabel = copyBtn?.dataset.labelCopied || "Copied";

        const ok = () => {
            this.setCopyButtonLabel(copiedLabel);
            window.setTimeout(() => this.setCopyButtonLabel(copyLabel), 2000);
        };

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(ok).catch(() => {
                this.fallbackCopy(text, ok);
            });
        } else {
            this.fallbackCopy(text, ok);
        }
    }

    fallbackCopy(text, onSuccess) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();

        try {
            if (document.execCommand("copy")) {
                onSuccess();
            }
        } catch (error) {
            console.error("Failed to copy logs:", error);
        } finally {
            document.body.removeChild(textarea);
        }
    }

    formatLogsForClipboard(logs) {
        return logs
            .map((log) => this.formatLogForClipboard(log))
            .filter(Boolean)
            .join("\n\n");
    }

    formatLogForClipboard(log) {
        if (!log) {
            return "";
        }

        const header = `[${this.formatTimestamp(log.timestamp)}] ${log.level || "-"} ${log.module || "-"}`;
        const operationId = log.operation_id ? ` op=${log.operation_id}` : "";
        const message = log.message || "";
        const summary = message ? `${header}${operationId} - ${message}` : `${header}${operationId}`;
        const details = [];

        if (log.operation) {
            details.push(`Operation: ${log.operation}`);
        }
        if (log.phase) {
            details.push(`Phase: ${log.phase}`);
        }
        if (log.resource_type && log.resource_id != null) {
            details.push(`Resource: ${log.resource_type}#${log.resource_id}`);
        }
        if (log.expandable && log.expandable.traceback) {
            details.push(log.expandable.traceback.trim());
        }

        return [summary, ...details].join("\n");
    }

    updateCopyButtonState() {
        const copyBtn = document.getElementById("copyLogsBtn");
        if (!copyBtn) {
            return;
        }

        copyBtn.disabled = this.displayedLogs.length === 0;
    }

    setCopyButtonLabel(label) {
        const copyBtn = document.getElementById("copyLogsBtn");
        if (!copyBtn) {
            return;
        }

        const labelEl = copyBtn.querySelector("[data-copy-label]") || copyBtn;
        labelEl.textContent = label;
    }

    formatTimestamp(timestamp) {
        if (!timestamp) return "-";
        try {
            const date = new Date(timestamp);
            if (Number.isNaN(date.getTime())) {
                return timestamp;
            }
            return date.toLocaleString();
        } catch {
            return timestamp;
        }
    }

    getLevelBadgeColor(level) {
        const colors = {
            DEBUG: "secondary",
            INFO: "primary",
            WARNING: "warning",
            ERROR: "danger",
            CRITICAL: "danger",
        };
        return colors[level] || "secondary";
    }

    escapeHtml(text) {
        if (text === null || text === undefined) return "";
        const div = document.createElement("div");
        div.textContent = String(text);
        return div.innerHTML;
    }

    updateLogCount() {
        const countEl = document.getElementById("logCount");
        const totalEl = document.getElementById("totalCount");
        if (countEl) {
            countEl.textContent = this.displayedLogs.length;
        }
        if (totalEl && this.total !== this.displayedLogs.length) {
            totalEl.textContent = ` (${this.total} total)`;
            totalEl.style.display = "inline";
        } else if (totalEl) {
            totalEl.textContent = "";
            totalEl.style.display = "none";
        }
    }

    updateFilterIndicator(activeFilters) {
        const indicator = document.getElementById("filterIndicator");
        const badge = document.getElementById("activeFiltersBadge");

        if (!indicator || !badge) return;

        const filters = [];

        if (this.isErrorsTab() || (activeFilters && activeFilters.errors_only)) {
            filters.push("Errors");
        }

        if (!this.isErrorsTab() && this.currentLevel) {
            filters.push(`Client: level=${this.currentLevel}`);
        }

        if (this.currentOperationId) {
            filters.push(`Backend: operation=${this.currentOperationId.substring(0, 8)}`);
        } else if (activeFilters && activeFilters.operation_id) {
            filters.push(`Backend: operation=${String(activeFilters.operation_id).substring(0, 8)}`);
        }

        if (filters.length > 0) {
            badge.textContent = filters.join(" | ");
            indicator.style.display = "block";
        } else {
            indicator.style.display = "none";
        }
    }

    updateLoadMoreState() {
        const shouldShow = this.canLoadMoreOlder && Boolean(this.oldestLoadedId);
        if (shouldShow) {
            this.showLoadMore();
        } else {
            this.hideLoadMore();
        }
    }

    clearFilters() {
        this.currentLevel = "";
        this.currentOperationId = "";
        this.currentFromDate = "";
        this.currentToDate = "";

        const levelFilter = document.getElementById("levelFilter");
        const operationIdFilter = document.getElementById("operationIdFilter");
        const fromDateFilter = document.getElementById("fromDateFilter");
        const toDateFilter = document.getElementById("toDateFilter");

        if (levelFilter) levelFilter.value = "";
        if (operationIdFilter) operationIdFilter.value = "";
        if (fromDateFilter) fromDateFilter.value = "";
        if (toDateFilter) toDateFilter.value = "";

        this.updateLevelFilterState();
        this.fetchLogs({ reset: true });
    }

    showLoading() {
        const loadingRow = document.getElementById("loadingRow");
        if (loadingRow) {
            loadingRow.style.display = "";
        }
    }

    hideLoading() {
        const loadingRow = document.getElementById("loadingRow");
        if (loadingRow) {
            loadingRow.style.display = "none";
        }
    }

    showError(message) {
        const errorMessage = document.getElementById("errorMessage");
        const errorText = document.getElementById("errorText");
        if (errorMessage) {
            errorMessage.style.display = "block";
        }
        if (errorText) {
            errorText.textContent = message;
        }
        this.hideLoadMore();
        this.updateCopyButtonState();
        this.hideLoading();
    }

    hideError() {
        const errorMessage = document.getElementById("errorMessage");
        if (errorMessage) {
            errorMessage.style.display = "none";
        }
    }

    showLoadMore() {
        const loadMoreBtn = document.getElementById("loadMoreBtn");
        if (loadMoreBtn) {
            loadMoreBtn.style.display = "";
        }
    }

    hideLoadMore() {
        const loadMoreBtn = document.getElementById("loadMoreBtn");
        if (loadMoreBtn) {
            loadMoreBtn.style.display = "none";
        }
    }

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
        if (this.operationIdFetchTimer) {
            clearTimeout(this.operationIdFetchTimer);
        }
        this.operationIdFetchTimer = window.setTimeout(() => {
            this.operationIdFetchTimer = null;
            this.fetchLogs({ reset: true });
        }, 300);
    }

    stopOperationFetch() {
        if (this.operationIdFetchTimer) {
            clearTimeout(this.operationIdFetchTimer);
            this.operationIdFetchTimer = null;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new LogsPage();
});
