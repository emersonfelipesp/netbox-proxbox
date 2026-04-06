(function (global) {
  "use strict";

  var terminal = { completed: 1, errored: 1, failed: 1 };
  var root = null;
  var pk = "0";
  var statusEl = null;
  var logEl = null;
  var copyBtn = null;
  var progressBarEl = null;
  var statePillEl = null;
  var summaryRoot = null;
  var summaryStatusEl = null;
  var summaryDetailEl = null;
  var phasesEl = null;
  var errorsEl = null;
  var streamUrl = "";
  var apiUrl = "";
  var logSuffix = "log lines";
  var timer = null;
  var sseSource = null;
  var isStreaming = false;
  var lastEntries = [];
  var phaseState = {};
  var errorEntries = [];
  var lastStatusValue = "";
  var lastStatusLabel = "";
  var stateStorageKey = "";

  function getStorage() {
    try {
      return global.localStorage;
    } catch (error) {
      try {
        return global.sessionStorage;
      } catch (fallbackError) {
        return null;
      }
    }
  }

  function readStoredState() {
    var storage = getStorage();
    if (!storage) return null;
    try {
      var raw = storage.getItem(stateStorageKey);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  function writeStoredState(extra) {
    var storage = getStorage();
    if (!storage) return;
    var payload = {
      entries: Array.isArray(lastEntries) ? lastEntries : [],
      statusText: statusEl ? statusEl.textContent : "",
      statusValue: lastStatusValue,
      statusLabel: lastStatusLabel,
      updatedAt: new Date().toISOString(),
    };
    if (extra && typeof extra === "object") {
      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key];
      });
    }
    try {
      storage.setItem(stateStorageKey, JSON.stringify(payload));
    } catch (error) {}
  }

  function jobStatusParts(status) {
    if (status && typeof status === "object") {
      var v = status.value != null ? String(status.value) : "";
      var lbl = status.label != null ? String(status.label) : v;
      return { value: v, label: lbl };
    }
    var s = status != null ? String(status) : "";
    return { value: s, label: s };
  }

  function isQueuedLikeStatus(statusValue) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    return normalized === "pending" || normalized === "scheduled";
  }

  function isRunningLikeStatus(statusValue) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    return normalized === "running" || normalized === "progress";
  }

  function expandSummaryIfNeeded(previousStatus, currentStatus) {
    if (!summaryRoot || summaryRoot.open) {
      return;
    }
    if (isQueuedLikeStatus(previousStatus) && isRunningLikeStatus(currentStatus)) {
      summaryRoot.open = true;
    }
  }

  function collapseSummaryIfNeeded(statusValue) {
    if (!summaryRoot || !summaryRoot.open) {
      return;
    }
    if (terminal[String(statusValue || "").trim().toLowerCase()]) {
      summaryRoot.open = false;
    }
  }

  function setQueuedStatePill(isQueued) {
    if (!statePillEl) {
      return;
    }
    statePillEl.className = isQueued ? "badge text-bg-warning" : "badge text-bg-warning d-none";
    statePillEl.setAttribute("aria-hidden", isQueued ? "false" : "true");
  }

  function applyStatusPresentation(statusValue) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    setQueuedStatePill(
      normalized === "waiting" ||
        normalized === "queued" ||
        normalized === "pending" ||
        normalized === "scheduled"
    );

    if (!statusEl) {
      return;
    }

    var classes = ["nb-job-live-status", "fw-semibold"];
    if (normalized === "waiting" || normalized === "queued" || normalized === "pending" || normalized === "scheduled") {
      classes.push("text-warning");
    } else if (normalized === "running" || normalized === "progress" || normalized === "started" || normalized === "streaming") {
      classes.push("text-info");
    } else if (normalized === "completed") {
      classes.push("text-success");
    } else if (normalized === "failed" || normalized === "errored") {
      classes.push("text-danger");
    } else {
      classes.push("text-body-secondary");
    }
    statusEl.className = classes.join(" ");

    if (root) {
      root.classList.toggle(
        "nb-job-live-card-queued",
        normalized === "waiting" ||
          normalized === "queued" ||
          normalized === "pending" ||
          normalized === "scheduled"
      );
    }
  }

  function isQueuedCompletion(payload) {
    if (!payload || typeof payload !== "object") {
      return false;
    }
    var status = String(payload.status || "").trim().toLowerCase();
    if (status === "waiting" || status === "queued") {
      return true;
    }
    var queuedStatus = String(payload.queued_status || "").trim().toLowerCase();
    return queuedStatus === "pending" || queuedStatus === "scheduled";
  }

  function setStatusValue(nextStatusValue, nextStatusLabel, previousStatusValue) {
    var normalizedNextStatus = String(nextStatusValue || "").trim().toLowerCase();
    var normalizedPreviousStatus = String(previousStatusValue || "").trim().toLowerCase();

    lastStatusValue = normalizedNextStatus;
    lastStatusLabel = String(nextStatusLabel || "").trim() || normalizedNextStatus;
    expandSummaryIfNeeded(normalizedPreviousStatus, normalizedNextStatus);
    applyStatusPresentation(normalizedNextStatus);
  }

  function updateSummaryDisplay() {
    if (!summaryRoot) {
      return;
    }

    var summaryStatus = summaryStatusEl || summaryRoot.querySelector("[data-proxbox-job-live-summary-status]");
    var summaryDetail = summaryDetailEl || summaryRoot.querySelector("[data-proxbox-job-live-summary-detail]");
    if (!summaryStatus && !summaryDetail) {
      return;
    }

    var statusValue = String(lastStatusValue || "").trim().toLowerCase();
    var statusLabel = String(lastStatusLabel || "").trim();
    if (!statusLabel) {
      statusLabel = statusValue || "Unknown";
    }

    if (summaryStatus) {
      summaryStatus.textContent = statusLabel;
    }

    if (summaryDetail) {
      var detailText = "";
      if (statusValue === "completed") {
        detailText = "Done";
      } else if (statusValue === "failed" || statusValue === "errored") {
        detailText = "Failed";
      } else if (progressBarEl) {
        var progressLabel = progressBarEl.querySelector(".nb-job-progress-label");
        if (progressLabel && progressLabel.textContent.trim()) {
          detailText = progressLabel.textContent.trim();
        }
      }

      if (!detailText) {
        var count = Array.isArray(lastEntries) ? lastEntries.length : 0;
        detailText = count + " " + logSuffix;
      }

      summaryDetail.textContent = detailText;
    }
  }

  function applyLog(entries) {
    if (!logEl) return;
    var api = global.NbProxboxJobLogView;
    lastEntries = Array.isArray(entries) ? entries : [];
    if (api && typeof api.renderLiveLog === "function") {
      api.renderLiveLog(logEl, lastEntries);
    } else {
      logEl.textContent = "";
    }
    logEl.scrollTop = logEl.scrollHeight;
    updateSummaryDisplay();
  }

  function renderStatusLine(st, entries) {
    var n = Array.isArray(entries) ? entries.length : 0;
    var display = st.label || st.value || "—";
    var detail = st.value && st.label && st.label !== st.value ? " (" + st.value + ")" : "";
    return " — " + display + detail + " · " + n + " " + logSuffix;
  }

  function restoreStoredState() {
    var stored = readStoredState();
    if (!stored) return;

    if (Array.isArray(stored.entries) && stored.entries.length > 0) {
      lastEntries = stored.entries.slice();
      applyLog(lastEntries);
    }

    if (stored.statusValue != null) {
      lastStatusValue = String(stored.statusValue);
    }
    if (stored.statusLabel != null) {
      lastStatusLabel = String(stored.statusLabel);
    }

    if (stored.statusText && statusEl) {
      statusEl.textContent = String(stored.statusText);
    }

    var api = global.NbProxboxJobLogView;
    if (api && typeof api.applyProgress === "function") {
      api.applyProgress(
        progressBarEl,
        { data: { status: stored.statusValue || "" } },
        lastEntries
      );
    }

    applyStatusPresentation(lastStatusValue);
    updateSummaryDisplay();
  }

  function getFrameMessage(data, eventType) {
    if (typeof data === "string") {
      return data;
    }
    if (!data || typeof data !== "object") {
      return "";
    }
    if (typeof data.message === "string" && data.message.trim()) {
      return data.message;
    }
    if (typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
    if (typeof data.error === "string" && data.error.trim()) {
      return data.error;
    }
    if (eventType === "complete" && data.ok === true) {
      return data.message || "Completed";
    }
    return "";
  }

  function isGenericProgressMessage(message, payload, eventType) {
    var msg = String(message || "").trim().toLowerCase();
    if (!msg) return false;
    if (msg === "sync progress" || msg === "progress") {
      return true;
    }
    if (eventType === "step" && String(payload && payload.step || "") === "progress" && msg.indexOf("stage") === -1) {
      return true;
    }
    return false;
  }

  function describeStepProgress(payload) {
    if (!payload || typeof payload !== "object") return "";
    var step = String(payload.step || "");
    if (step !== "progress") return "";
    var progress = payload.progress && typeof payload.progress === "object" ? payload.progress : null;
    if (!progress) return "";
    var stage = progress.stage != null ? String(progress.stage) : "";
    var current = progress.current != null ? String(progress.current) : "";
    var total = progress.total != null ? String(progress.total) : "";
    var status = String(payload.status || "").toLowerCase();
    if (status === "started") {
      if (stage && current && total) return "Starting stage " + stage + " (" + current + "/" + total + ")";
      if (stage) return "Starting stage " + stage;
    }
    if (status === "completed") {
      if (stage && current && total) return "Completed stage " + stage + " (" + current + "/" + total + ")";
      if (stage) return "Completed stage " + stage;
    }
    if (stage && current && total) return "Stage " + stage + " in progress (" + current + "/" + total + ")";
    return "";
  }

  function updateProgress(progress, previousStatus) {
    if (!progressBarEl) return;
    var wrap = progressBarEl.parentElement ? progressBarEl.parentElement.parentElement : null;
    if (wrap && wrap.classList.contains("nb-job-progress-wrap")) {
      wrap.style.display = "";
    }
    var pct = progress.percent !== undefined ? progress.percent : 100;
    progressBarEl.style.width = pct + "%";
    progressBarEl.setAttribute("aria-valuenow", pct);
    var label = progressBarEl.querySelector(".nb-job-progress-label");
    if (label) {
      if (progress.stage) {
        label.textContent = progress.stage + " (" + progress.current + "/" + progress.total + ")";
      } else {
        label.textContent = progress.current + "/" + progress.total;
      }
      label.className = "nb-job-progress-label small fw-semibold text-dark";
    }
    progressBarEl.classList.remove("bg-info", "bg-warning", "bg-success", "bg-danger");
    progressBarEl.classList.add("bg-warning", "progress-bar-striped", "progress-bar-animated");
    setStatusValue("progress", "Running", previousStatus);
    updateSummaryDisplay();
  }

  function finishStream(status, message) {
    setStatusValue(status, status === "completed" ? "Completed" : "Failed", lastStatusValue);
    collapseSummaryIfNeeded(status);
    if (progressBarEl) {
      progressBarEl.classList.remove("progress-bar-striped", "progress-bar-animated");
      progressBarEl.classList.remove("bg-info", "bg-warning", "bg-success", "bg-danger");
      progressBarEl.classList.add(status === "completed" ? "bg-success" : "bg-danger");
      var label = progressBarEl.querySelector(".nb-job-progress-label");
      if (label) {
        label.textContent = status === "completed" ? "Done" : "Failed";
        label.className = "nb-job-progress-label small fw-semibold text-white";
      }
    }
    if (message) {
      appendLog(message, status === "completed" ? "success" : "error", {
        status: status,
        message: message,
      });
    }
    if (statusEl) {
      statusEl.textContent = status === "completed" ? " — Completed" : " — Failed";
    }
    if (sseSource) {
      sseSource.close();
      sseSource = null;
    }
    isStreaming = false;
    updateSummaryDisplay();
    writeStoredState();
  }

  function appendLog(message, eventType, data) {
    if (!logEl) return;
    var api = global.NbProxboxJobLogView;
    var entry = {
      timestamp: new Date().toISOString(),
      level: eventType || "info",
      message: message,
    };
    if (!lastEntries) lastEntries = [];
    lastEntries.push(entry);
    if (lastEntries.length > 200) lastEntries.shift();
    if (api && typeof api.renderLiveLog === "function") {
      logEl.replaceChildren();
      api.renderLiveLog(logEl, lastEntries);
    } else {
      var span = document.createElement("div");
      span.className = "nb-job-live-log-entry";
      span.textContent = entry.timestamp + " [" + entry.level + "] " + entry.message;
      logEl.appendChild(span);
    }
    logEl.scrollTop = logEl.scrollHeight;
    updateSummaryDisplay();
    writeStoredState();
  }

  function ensurePhaseRow(phase) {
    if (!phasesEl || !phase) return null;
    var key = String(phase);
    var row = phasesEl.querySelector('[data-phase="' + key.replace(/"/g, "") + '"]');
    if (row) return row;
    row = document.createElement("div");
    row.className = "nb-job-phase-item";
    row.dataset.phase = key;
    row.dataset.status = "pending";
    var name = document.createElement("span");
    name.className = "nb-job-phase-name";
    name.textContent = key;
    var detail = document.createElement("span");
    detail.className = "nb-job-phase-detail";
    detail.textContent = "Pending";
    row.appendChild(name);
    row.appendChild(detail);
    phasesEl.appendChild(row);
    return row;
  }

  function renderErrors() {
    if (!errorsEl) return;
    errorsEl.replaceChildren();
    if (!Array.isArray(errorEntries) || errorEntries.length === 0) {
      errorsEl.classList.add("d-none");
      return;
    }
    errorsEl.classList.remove("d-none");
    var title = document.createElement("div");
    title.className = "nb-job-error-title";
    title.textContent = "Issues detected";
    errorsEl.appendChild(title);
    var start = Math.max(0, errorEntries.length - 6);
    for (var i = start; i < errorEntries.length; i++) {
      var item = document.createElement("div");
      item.className = "nb-job-error-item";
      item.textContent = errorEntries[i];
      errorsEl.appendChild(item);
    }
  }

  function handleDiscoveryFrame(payload) {
    if (!payload || typeof payload !== "object") return;
    var phase = String(payload.phase || payload.step || "sync");
    var row = ensurePhaseRow(phase);
    if (!row) return;
    var count = payload.count != null ? String(payload.count) : "0";
    var detail = row.querySelector(".nb-job-phase-detail");
    row.dataset.status = "processing";
    if (detail) {
      detail.textContent = "Discovered " + count + " item(s)";
    }
    phaseState[phase] = { status: "processing", count: count };
  }

  function handleSubstepFrame(payload) {
    if (!payload || typeof payload !== "object") return;
    var phase = String(payload.phase || payload.step || "sync");
    var row = ensurePhaseRow(phase);
    if (!row) return;
    var status = String(payload.status || "processing").toLowerCase();
    var substep = String(payload.substep || "work");
    var detail = row.querySelector(".nb-job-phase-detail");
    row.dataset.status = status === "failed" ? "failed" : "processing";
    if (detail) {
      detail.textContent = substep + " - " + (status === "completed" ? "done" : status);
    }
    phaseState[phase] = { status: row.dataset.status, substep: substep };
  }

  function handleItemProgressFrame(payload) {
    if (!payload || typeof payload !== "object") return;
    var phase = String(payload.phase || payload.step || "sync");
    var row = ensurePhaseRow(phase);
    if (!row) return;
    var progress = payload.progress && typeof payload.progress === "object" ? payload.progress : {};
    var current = progress.current != null ? String(progress.current) : "0";
    var total = progress.total != null ? String(progress.total) : "0";
    var status = String(payload.status || "processing").toLowerCase();
    var detail = row.querySelector(".nb-job-phase-detail");
    row.dataset.status = status === "failed" ? "failed" : status === "completed" ? "completed" : "processing";
    if (detail) {
      detail.textContent = current + "/" + total + " item(s)";
    }
    phaseState[phase] = { status: row.dataset.status, current: current, total: total };
  }

  function handlePhaseSummaryFrame(payload) {
    if (!payload || typeof payload !== "object") return;
    var phase = String(payload.phase || payload.step || "sync");
    var row = ensurePhaseRow(phase);
    if (!row) return;
    var result = payload.result && typeof payload.result === "object" ? payload.result : {};
    var created = result.created != null ? String(result.created) : "0";
    var failed = result.failed != null ? String(result.failed) : "0";
    var detail = row.querySelector(".nb-job-phase-detail");
    row.dataset.status = String(payload.status || "completed").indexOf("error") >= 0 ? "failed" : "completed";
    if (detail) {
      detail.textContent = created + " ok, " + failed + " failed";
    }
    phaseState[phase] = { status: row.dataset.status, created: created, failed: failed };
  }

  function handleErrorDetailFrame(payload) {
    if (!payload || typeof payload !== "object") return;
    var phase = String(payload.phase || payload.step || "sync");
    var row = ensurePhaseRow(phase);
    if (row) {
      row.dataset.status = "failed";
      var detail = row.querySelector(".nb-job-phase-detail");
      if (detail) {
        detail.textContent = String(payload.category || "error") + ": failed";
      }
    }
    var msg = String(payload.message || payload.error || payload.detail || "Error");
    if (payload.suggestion) {
      msg += " (" + String(payload.suggestion) + ")";
    }
    errorEntries.push(msg);
    if (errorEntries.length > 20) {
      errorEntries.shift();
    }
    renderErrors();
  }

  function handleSSEFrame(eventType, data) {
    var payload = data && typeof data === "object" ? data : {};
    if (eventType === "discovery") {
      handleDiscoveryFrame(payload);
    } else if (eventType === "substep") {
      handleSubstepFrame(payload);
    } else if (eventType === "item_progress") {
      handleItemProgressFrame(payload);
    } else if (eventType === "phase_summary") {
      handlePhaseSummaryFrame(payload);
    } else if (eventType === "error_detail") {
      handleErrorDetailFrame(payload);
    }

    var message = getFrameMessage(payload, eventType);
    var stepProgressText = describeStepProgress(payload);
    if (stepProgressText) {
      message = stepProgressText;
    }
    var status = payload.status ? String(payload.status) : "";
    var previousStatus = lastStatusValue;
    var isTerminal =
      eventType === "complete" ||
      status === "failed" ||
      status === "errored" ||
      eventType === "error";

    if (message && !isTerminal && !isGenericProgressMessage(message, payload, eventType)) {
      appendLog(
        message,
        eventType === "error"
          ? "error"
          : eventType === "message"
            ? "info"
            : status || eventType || "info",
        payload
      );
    }

    if (payload.progress) {
      updateProgress(payload.progress, previousStatus);
    }

    var api = global.NbProxboxJobLogView;
    if (lastEntries.length > 0 && api && typeof api.applyProgress === "function") {
      api.applyProgress(progressBarEl, { data: payload }, lastEntries);
      updateSummaryDisplay();
    }

    if (status) {
      setStatusValue(
        status,
        status !== "progress" ? status.charAt(0).toUpperCase() + status.slice(1) : "Running",
        previousStatus
      );
    }
    updateSummaryDisplay();
    writeStoredState();

    if (eventType === "complete") {
      if (isQueuedCompletion(payload)) {
        setStatusValue("waiting", "Queued", previousStatus);
        if (statusEl) {
          statusEl.textContent = " — Queued";
        }
        if (sseSource) {
          sseSource.close();
          sseSource = null;
        }
        isStreaming = false;
        updateSummaryDisplay();
        writeStoredState();
        startPollingFallback();
        return;
      }
      finishStream(payload.ok === false ? "failed" : "completed", message || payload.message || "");
      return;
    }
    if (status === "failed" || eventType === "error") {
      finishStream("failed", message || payload.detail || payload.error || "");
    }
  }

  function tick() {
    fetch(apiUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("poll failed");
        return r.json();
      })
      .then(function (d) {
        var st = jobStatusParts(d.status);
        var entries = Array.isArray(d.log_entries) ? d.log_entries : [];
        var previousStatus = lastStatusValue;
        lastEntries = entries;
        setStatusValue(st.value, st.label || st.value || "Unknown", previousStatus);
        if (statusEl) {
          statusEl.textContent = renderStatusLine(st, entries);
        }
        applyLog(entries);
        var api = global.NbProxboxJobLogView;
        if (api && typeof api.applyProgress === "function") {
          api.applyProgress(progressBarEl, d, entries);
        }
    if (terminal[st.value]) {
      if (timer) clearInterval(timer);
      timer = null;
          if (progressBarEl) {
            progressBarEl.classList.remove("progress-bar-striped", "progress-bar-animated");
            if (st.value === "errored" || st.value === "failed") {
              progressBarEl.classList.remove("bg-info", "bg-warning", "bg-success");
              progressBarEl.classList.add("bg-danger");
            } else if (st.value === "completed") {
              progressBarEl.classList.remove("bg-info", "bg-warning", "bg-danger");
              progressBarEl.classList.add("bg-success");
            }
          }
        }
        collapseSummaryIfNeeded(st.value);
        updateSummaryDisplay();
        writeStoredState();
      })
      .catch(function () {});
  }

  function startPollingFallback() {
    if (timer) return;
    tick();
    timer = setInterval(tick, 2500);
  }

  function startSSE() {
    if (isStreaming) return;
    if (!pk || !streamUrl) {
      startPollingFallback();
      return;
    }
    isStreaming = true;
    try {
      sseSource = new EventSource(streamUrl);
      sseSource.addEventListener("step", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("step", data);
        } catch (error) {}
      });
      sseSource.addEventListener("message", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("message", data);
        } catch (error) {}
      });
      sseSource.addEventListener("discovery", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("discovery", data);
        } catch (error) {}
      });
      sseSource.addEventListener("substep", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("substep", data);
        } catch (error) {}
      });
      sseSource.addEventListener("item_progress", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("item_progress", data);
        } catch (error) {}
      });
      sseSource.addEventListener("phase_summary", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("phase_summary", data);
        } catch (error) {}
      });
      sseSource.addEventListener("error_detail", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("error_detail", data);
        } catch (error) {}
      });
      sseSource.addEventListener("error", function () {
        if (!isStreaming) {
          return;
        }
        isStreaming = false;
        if (sseSource) {
          sseSource.close();
          sseSource = null;
        }
        startPollingFallback();
      });
      sseSource.addEventListener("complete", function (e) {
        try {
          var data = JSON.parse(e.data);
          handleSSEFrame("complete", data);
        } catch (error) {
          finishStream("completed", "");
        }
      });
      if (statusEl) {
        statusEl.textContent = " — Streaming...";
      }
      setStatusValue("running", "Streaming", lastStatusValue);
      updateSummaryDisplay();
      writeStoredState();
    } catch (error) {
      isStreaming = false;
      startPollingFallback();
    }
  }

  function startPolling() {
    restoreStoredState();
    startSSE();
    window.setTimeout(function () {
      if (!isStreaming) startPollingFallback();
    }, 1000);
  }

  function fallbackCopy(text, onOk) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      if (document.execCommand("copy")) {
        onOk();
      }
    } catch (error) {}
    document.body.removeChild(ta);
  }

  function wireCopyButton() {
    if (!copyBtn) return;
    copyBtn.addEventListener("click", function () {
      var api = global.NbProxboxJobLogView;
      var text =
        api && typeof api.formatLogEntriesForClipboard === "function"
          ? api.formatLogEntriesForClipboard(lastEntries)
          : "";
      var labelCopy = copyBtn.getAttribute("data-label-copy") || "Copy logs";
      var labelCopied = copyBtn.getAttribute("data-label-copied") || "Copied!";

      function restoreLabel() {
        copyBtn.textContent = labelCopy;
      }

      function ok() {
        copyBtn.textContent = labelCopied;
        window.setTimeout(restoreLabel, 2000);
      }

      if (!text) {
        return;
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok).catch(function () {
          fallbackCopy(text, ok);
        });
      } else {
        fallbackCopy(text, ok);
      }
    });
  }

  function bootstrap() {
    root = document.querySelector("[data-proxbox-job-live-root]");
    if (!root) {
      return;
    }

    pk = String(root.dataset.jobPk || "0");
    streamUrl = String(root.dataset.jobStreamUrl || "");
    apiUrl = String(root.dataset.jobApiUrl || "/api/core/jobs/" + pk + "/");
    logSuffix = String(root.dataset.jobLogSuffix || "log lines");
    statusEl = root.querySelector("[data-proxbox-job-live-status]");
    logEl = root.querySelector("[data-proxbox-job-live-log]");
    copyBtn = root.querySelector("[data-proxbox-job-live-copy]");
    progressBarEl = root.querySelector("[data-proxbox-job-live-progress-bar]");
    phasesEl = root.querySelector("[data-proxbox-job-live-phases]");
    errorsEl = root.querySelector("[data-proxbox-job-live-errors]");
    statePillEl = root.querySelector("[data-proxbox-job-live-state-pill]");
    summaryRoot = root.closest("[data-proxbox-job-live-summary]");
    summaryStatusEl = summaryRoot
      ? summaryRoot.querySelector("[data-proxbox-job-live-summary-status]")
      : null;
    summaryDetailEl = summaryRoot
      ? summaryRoot.querySelector("[data-proxbox-job-live-summary-detail]")
      : null;
    stateStorageKey = "netbox-proxbox.job-live-state:" + pk;

    wireCopyButton();

    window.addEventListener("storage", function (event) {
      if (event.key !== stateStorageKey) {
        return;
      }
      restoreStoredState();
    });

    startPolling();
  }

  global.NbProxboxJobLivePanel = {
    bootstrap: bootstrap,
    restoreStoredState: restoreStoredState,
    writeStoredState: writeStoredState,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})(window);
