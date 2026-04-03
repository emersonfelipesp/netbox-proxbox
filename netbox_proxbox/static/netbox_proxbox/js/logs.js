/**
 * Backend Logs page JavaScript
 * Handles fetching, filtering, and displaying logs from the proxbox-api backend.
 */

class LogsPage {
    constructor() {
        this.config = window.proxboxLogsConfig || {};
        this.logsApiUrl = this.config.logsApiUrl || "";
        this.cachedLogs = [];
        this.allLogs = [];
        this.currentLevel = "";
        this.currentOperationId = "";
        this.autoRefreshInterval = 5000;
        this.autoRefreshTimer = null;
        this.isAutoRefreshEnabled = true;
        this.currentOffset = 0;
        this.limit = 200;
        this.total = 0;
        this.isLoading = false;

        this.init();
    }

    init() {
        this.bindEvents();
        this.fetchLogs();
    }

    bindEvents() {
        const refreshBtn = document.getElementById("refreshBtn");
        const autoRefreshToggle = document.getElementById("autoRefreshToggle");
        const levelFilter = document.getElementById("levelFilter");
        const operationIdFilter = document.getElementById("operationIdFilter");
        const clearFiltersBtn = document.getElementById("clearFiltersBtn");
        const loadMoreBtn = document.getElementById("loadMoreBtn");

        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => this.fetchLogs());
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
                this.applyFilters();
            });
        }

        if (operationIdFilter) {
            operationIdFilter.addEventListener("input", (e) => {
                this.currentOperationId = e.target.value.trim();
                this.applyFilters();
            });
        }

        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener("click", () => this.clearFilters());
        }

        if (loadMoreBtn) {
            loadMoreBtn.addEventListener("click", () => this.loadMore());
        }
    }

    async fetchLogs() {
        if (this.isLoading) return;
        if (!this.logsApiUrl) {
            this.showError("Logs API URL not configured");
            return;
        }

        this.isLoading = true;
        this.showLoading();

        try {
            const params = new URLSearchParams();
            if (this.currentLevel) {
                params.append("level", this.currentLevel);
            }
            params.append("limit", this.limit.toString());

            const url = `${this.logsApiUrl}?${params.toString()}`;
            const response = await fetch(url, {
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.allLogs = data.logs || [];
            this.total = data.total || this.allLogs.length;
            this.currentOffset = this.allLogs.length;

            this.applyFilters();

            this.updateLogCount();
            this.updateFilterIndicator(data.active_filters);

            if (this.allLogs.length < this.total) {
                this.showLoadMore();
            } else {
                this.hideLoadMore();
            }

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

    applyFilters() {
        this.cachedLogs = this.allLogs.filter((log) => {
            if (this.currentLevel) {
                const logLevel = this.getLogLevelPriority(log.level);
                const filterLevel = this.getLogLevelPriority(this.currentLevel);
                if (logLevel < filterLevel) return false;
            }

            if (this.currentOperationId) {
                if (!log.operation_id || !log.operation_id.includes(this.currentOperationId)) {
                    return false;
                }
            }

            return true;
        });

        this.renderLogs();
        this.updateFilterIndicator();
    }

    getLogLevelPriority(level) {
        const priorities = {
            DEBUG: 0,
            INFO: 1,
            WARNING: 2,
            ERROR: 3,
            CRITICAL: 4,
        };
        return priorities[level] ?? 0;
    }

    renderLogs() {
        const tbody = document.getElementById("logsTableBody");
        const noLogsMessage = document.getElementById("noLogsMessage");
        const template = document.getElementById("logRowTemplate");

        if (!tbody) return;

        tbody.innerHTML = "";

        if (this.cachedLogs.length === 0) {
            this.hideLoadMore();
            noLogsMessage.style.display = "block";
            return;
        }

        noLogsMessage.style.display = "none";

        this.cachedLogs.forEach((log, index) => {
            const row = document.createElement("tr");
            row.className = `log-entry log-level-${log.level.toLowerCase()}`;
            if (log.expandable) {
                row.classList.add(" expandable");
                row.dataset.expanded = "false";
            }

            row.innerHTML = `
                <td class="log-timestamp">${this.formatTimestamp(log.timestamp)}</td>
                <td class="log-level">
                    <span class="badge bg-${this.getLevelBadgeColor(log.level)}">${log.level}</span>
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
    }

    toggleExpand(row, log) {
        const isExpanded = row.dataset.expanded === "true";

        const existingDetail = row.nextElementSibling;
        if (existingDetail && existingDetail.classList.contains("log-detail-row")) {
            existingDetail.remove();
            row.dataset.expanded = "false";
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
        const icon = row.querySelector(".expand-icon");
        if (icon) {
            icon.classList.replace("mdi-chevron-down", "mdi-chevron-up");
        }
    }

    formatTimestamp(timestamp) {
        if (!timestamp) return "-";
        try {
            const date = new Date(timestamp);
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
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    updateLogCount() {
        const countEl = document.getElementById("logCount");
        const totalEl = document.getElementById("totalCount");
        if (countEl) {
            countEl.textContent = this.cachedLogs.length;
        }
        if (totalEl && this.total !== this.cachedLogs.length) {
            totalEl.textContent = ` (${this.total} total)`;
            totalEl.style.display = "inline";
        }
    }

    updateFilterIndicator(activeFilters) {
        const indicator = document.getElementById("filterIndicator");
        const badge = document.getElementById("activeFiltersBadge");

        if (!indicator || !badge) return;

        const filters = [];

        if (this.currentLevel) {
            filters.push(`level=${this.currentLevel}`);
        }

        if (this.currentOperationId) {
            filters.push(`operation=${this.currentOperationId.substring(0, 8)}`);
        }

        if (filters.length > 0) {
            badge.textContent = `Filtered: ${filters.join(", ")}`;
            indicator.style.display = "block";
        } else {
            indicator.style.display = "none";
        }
    }

    clearFilters() {
        this.currentLevel = "";
        this.currentOperationId = "";

        const levelFilter = document.getElementById("levelFilter");
        const operationIdFilter = document.getElementById("operationIdFilter");

        if (levelFilter) levelFilter.value = "";
        if (operationIdFilter) operationIdFilter.value = "";

        this.applyFilters();
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

    async loadMore() {
        if (this.isLoading) return;
        if (this.cachedLogs.length >= this.total) return;

        this.isLoading = true;

        try {
            const params = new URLSearchParams();
            if (this.currentLevel) {
                params.append("level", this.currentLevel);
            }
            params.append("limit", this.limit.toString());
            params.append("offset", this.currentOffset.toString());

            const url = `${this.logsApiUrl}?${params.toString()}`;
            const response = await fetch(url, {
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            const newLogs = data.logs || [];
            this.allLogs = [...this.allLogs, ...newLogs];
            this.total = data.total || this.allLogs.length;
            this.currentOffset = this.allLogs.length;

            this.applyFilters();

            if (this.currentOffset >= this.total) {
                this.hideLoadMore();
            }
        } catch (error) {
            console.error("Failed to load more logs:", error);
            this.showError(error.message || "Failed to load more logs");
        } finally {
            this.isLoading = false;
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        if (this.isAutoRefreshEnabled) {
            this.autoRefreshTimer = setInterval(() => {
                this.fetchLogs();
            }, this.autoRefreshInterval);
        }
    }

    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new LogsPage();
});
