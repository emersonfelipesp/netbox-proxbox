/**
 * Parse and render Proxbox stream log lines (compact inline KV, textContent only).
 */
(function (global) {
  "use strict";

  var INLINE_MAX_DEPTH = 4;
  var STREAM_RE = /^\[proxbox-stream\]\s+(\S+):\s*(.+)$/;

  function parseProxboxMessage(msg) {
    if (typeof msg !== "string") return null;
    var m = msg.match(STREAM_RE);
    if (!m) return null;
    var event = m[1];
    var jsonStr = m[2].trim();
    if (!jsonStr) {
      return { event: event, data: null, rawSuffix: "", parseError: false };
    }
    try {
      var data = JSON.parse(jsonStr);
      return { event: event, data: data, rawSuffix: jsonStr, parseError: false };
    } catch (e) {
      return {
        event: event,
        data: null,
        rawSuffix: jsonStr,
        parseError: true,
      };
    }
  }

  function appendText(el, text) {
    el.appendChild(document.createTextNode(text));
  }

  function renderRawJson(text) {
    var span = document.createElement("span");
    span.className = "mb-0 small font-monospace";
    span.style.whiteSpace = "pre";
    appendText(span, text);
    return span;
  }

  function renderPlainLine(text) {
    var span = document.createElement("span");
    span.className = "mb-0 small";
    appendText(span, text);
    return span;
  }

  function filterStreamKeysForDisplay(obj) {
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
      return obj;
    }
    var out = {};
    var k;
    for (k in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, k)) {
        out[k] = obj[k];
      }
    }
    delete out.step;
    if (Object.prototype.hasOwnProperty.call(out, "status")) {
      if (String(out.status) === "progress") {
        delete out.status;
      }
    }
    return out;
  }

  function renderInlineValue(value, depth) {
    depth = depth || 0;
    if (depth > INLINE_MAX_DEPTH) {
      var cap = document.createElement("span");
      cap.className = "small text-muted";
      appendText(cap, "…");
      return cap;
    }

    if (value === null || value === undefined) {
      var em = document.createElement("em");
      em.className = "text-muted";
      appendText(em, "—");
      return em;
    }

    if (typeof value !== "object") {
      var span = document.createElement("span");
      span.className = "small";
      appendText(span, String(value));
      return span;
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        var empty = document.createElement("span");
        empty.className = "small text-muted";
        appendText(empty, "[]");
        return empty;
      }
      var wrap = document.createElement("span");
      wrap.className = "nb-proxbox-inline nb-proxbox-inline-array small";
      appendText(wrap, "[");
      for (var i = 0; i < value.length; i++) {
        if (i > 0) appendText(wrap, ", ");
        wrap.appendChild(renderInlineValue(value[i], depth + 1));
      }
      appendText(wrap, "]");
      return wrap;
    }

    return renderInlineObject(value, depth);
  }

  function renderInlineObject(obj, depth) {
    depth = depth || 0;
    if (depth > INLINE_MAX_DEPTH) {
      var cap2 = document.createElement("span");
      cap2.className = "small text-muted";
      appendText(cap2, "{…}");
      return cap2;
    }

    var filtered = filterStreamKeysForDisplay(obj);
    var keys = Object.keys(filtered);
    if (keys.length === 0) {
      var objEmpty = document.createElement("span");
      objEmpty.className = "small text-muted";
      appendText(objEmpty, "{}");
      return objEmpty;
    }

    var root = document.createElement("span");
    root.className = "nb-proxbox-inline";

    for (var k = 0; k < keys.length; k++) {
      if (k > 0) {
        appendText(root, " · ");
      }
      var key = keys[k];
      var kv = document.createElement("span");
      kv.className = "nb-proxbox-inline-kv";

      var keyEl = document.createElement("span");
      keyEl.className = "nb-proxbox-inline-key";
      appendText(keyEl, key);

      kv.appendChild(keyEl);
      appendText(kv, " ");

      var valWrap = document.createElement("span");
      valWrap.className = "nb-proxbox-inline-val";
      valWrap.appendChild(renderInlineValue(filtered[key], depth + 1));
      kv.appendChild(valWrap);

      root.appendChild(kv);
    }

    return root;
  }

  function renderParsedCompact(parsed) {
    var wrap = document.createElement("span");
    wrap.className = "nb-proxbox-parsed-msg";

    var badge = document.createElement("span");
    badge.className = "badge d-inline-flex text-bg-secondary text-uppercase nb-job-badge-fixed";
    appendText(badge, parsed.event);
    wrap.appendChild(badge);

    if (parsed.parseError || parsed.data === null) {
      wrap.appendChild(renderRawJson(parsed.rawSuffix || ""));
      return wrap;
    }

    var data = parsed.data;
    if (typeof data === "object" && !Array.isArray(data) && data !== null) {
      wrap.appendChild(renderInlineObject(data, 0));
    } else {
      wrap.appendChild(renderInlineValue(data, 0));
    }

    return wrap;
  }

  function getLevelBadgeClass(level) {
    var normalized = level != null ? String(level).trim().toLowerCase() : "";
    if (
      normalized === "completed" ||
      normalized === "success" ||
      normalized === "done" ||
      normalized === "ok"
    ) {
      return "badge d-inline-flex text-bg-success text-uppercase nb-job-badge-fixed";
    }
    if (
      normalized === "started" ||
      normalized === "streaming" ||
      normalized === "running" ||
      normalized === "pending"
    ) {
      return "badge d-inline-flex text-bg-blue text-uppercase nb-job-badge-fixed";
    }
    if (normalized === "progress") {
      return "badge d-inline-flex text-bg-warning text-uppercase nb-job-badge-fixed";
    }
    if (
      normalized === "error" ||
      normalized === "errored" ||
      normalized === "failed" ||
      normalized === "failure"
    ) {
      return "badge d-inline-flex text-bg-danger text-uppercase nb-job-badge-fixed";
    }
    return "badge d-inline-flex text-bg-secondary text-uppercase nb-job-badge-fixed";
  }

  function getProgressLabelClass(statusValue, done) {
    if (statusValue === "failed" || statusValue === "errored" || done) {
      return "nb-job-progress-label small fw-semibold text-white";
    }
    return "nb-job-progress-label small fw-semibold text-dark";
  }

  function renderMessageContent(msg) {
    var parsed = parseProxboxMessage(msg);
    var container = document.createElement("span");
    container.className = "nb-job-live-log-message d-inline-flex align-items-center gap-1";
    if (parsed) {
      container.appendChild(renderParsedCompact(parsed));
    } else {
      container.appendChild(renderPlainLine(msg));
    }
    return container;
  }

  // --- Stage progress parsing ---

  var ALL_STAGES = [
    "devices",
    "storage",
    "virtual-machines",
    "vm-disks",
    "vm-backups",
    "vm-snapshots",
    "network-interfaces",
    "ip-addresses"
  ];

  function resolveSyncTypes(apiData, entries) {
    var block = apiData && typeof apiData === "object" ? apiData.proxbox_sync : null;
    var params = block && typeof block === "object" ? block.params : null;
    var rawTypes = params && Array.isArray(params.sync_types) ? params.sync_types : null;

    if (rawTypes && rawTypes.length > 0) {
      if (rawTypes.length === 1 && rawTypes[0] === "all") {
        return ALL_STAGES.slice();
      }
      return rawTypes.slice();
    }

    // Fallback: scan log entries for the "Proxbox sync started for N stages" line
    var RE_STAGES = /^Proxbox sync started for (\d+) stages?$/;
    if (Array.isArray(entries)) {
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (!e || typeof e !== "object") continue;
        var msg = e.message != null ? String(e.message) : "";
        var m = msg.match(RE_STAGES);
        if (m) {
          var count = parseInt(m[1], 10);
          if (count > 0 && count <= ALL_STAGES.length) {
            return ALL_STAGES.slice(0, count);
          }
        }
      }
    }
    return [];
  }

  function parseJobProgress(entries, syncTypes) {
    var total = Array.isArray(syncTypes) ? syncTypes.length : 0;
    if (total === 0) {
      return { completed: 0, total: 0, currentStage: null, percent: 0, done: false };
    }
    if (!Array.isArray(entries)) {
      return { completed: 0, total: total, currentStage: null, percent: 0, done: false };
    }

    var RE_STARTING  = /^Starting stage \d+\/\d+:\s*(\S+)$/;
    var RE_COMPLETED = /^Stage (\S+) completed$/;
    var RE_ALL_DONE  = /^All sync stages completed\s*\(/;

    var completed = 0;
    var currentStage = null;
    var done = false;

    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (!e || typeof e !== "object") continue;
      var msg = e.message != null ? String(e.message) : "";

      if (RE_ALL_DONE.test(msg)) {
        done = true;
        completed = total;
        currentStage = null;
        break;
      }
      var mC = msg.match(RE_COMPLETED);
      if (mC) { completed++; currentStage = null; continue; }
      var mS = msg.match(RE_STARTING);
      if (mS) { currentStage = mS[1]; continue; }
    }

    var percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    if (done) percent = 100;

    return { completed: completed, total: total, currentStage: currentStage, percent: percent, done: done };
  }

  function applyProgress(barEl, d, entries) {
    if (!barEl) return;
    var apiData = d && typeof d === "object" && d.data ? d.data : null;
    var syncTypes = resolveSyncTypes(apiData, entries);
    var prog = parseJobProgress(entries, syncTypes);
    var statusValue = apiData && apiData.status != null ? apiData.status : "";
    if (statusValue && typeof statusValue === "object") {
      statusValue = statusValue.value != null ? String(statusValue.value) : "";
    } else {
      statusValue = String(statusValue);
    }
    statusValue = statusValue.trim().toLowerCase();

    var wrapper = barEl.parentElement;
    while (wrapper && !wrapper.classList.contains("nb-job-progress-wrap")) {
      wrapper = wrapper.parentElement;
    }

    if (prog.total === 0) {
      if (wrapper) wrapper.style.display = "none";
      return;
    }
    if (wrapper && wrapper.style.display === "none") wrapper.style.display = "";

    barEl.style.width = prog.percent + "%";
    barEl.setAttribute("aria-valuenow", String(prog.percent));
    var outer = barEl.parentElement;
    if (outer) outer.setAttribute("aria-valuenow", String(prog.percent));

    var label = barEl.querySelector(".nb-job-progress-label");
    if (label) {
      label.textContent = (statusValue === "failed" || statusValue === "errored")
        ? "Failed"
        : prog.done
          ? "Done"
          : prog.currentStage
            ? prog.currentStage + " (" + prog.completed + "/" + prog.total + ")"
            : prog.completed + "/" + prog.total;
      label.className = getProgressLabelClass(statusValue, prog.done);
    }

    barEl.classList.remove(
      "progress-bar-striped",
      "progress-bar-animated",
      "bg-info",
      "bg-warning",
      "bg-success",
      "bg-danger"
    );

    if (statusValue === "failed" || statusValue === "errored") {
      barEl.classList.add("bg-danger");
    } else if (prog.done || statusValue === "completed") {
      barEl.classList.add("bg-success");
    } else {
      barEl.classList.add("bg-warning", "progress-bar-striped", "progress-bar-animated");
    }
  }

  function formatTimestamp(ts) {
    if (!ts) return "";
    try {
      var d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      var h = String(d.getHours()).padStart(2, "0");
      var m = String(d.getMinutes()).padStart(2, "0");
      var s = String(d.getSeconds()).padStart(2, "0");
      var ms = String(d.getMilliseconds()).padStart(3, "0");
      return h + ":" + m + ":" + s + "." + ms;
    } catch (e) {
      return ts;
    }
  }

  function renderLiveLog(container, entries) {
    if (!container) return;
    container.replaceChildren();

    if (!Array.isArray(entries) || entries.length === 0) {
      var empty = document.createElement("span");
      empty.className = "mb-0 small text-muted";
      appendText(empty, "—");
      container.appendChild(empty);
      return;
    }

    var start = Math.max(0, entries.length - 50);
    for (var i = start; i < entries.length; i++) {
      var e = entries[i];
      if (!e || typeof e !== "object") continue;

      var row = document.createElement("div");
      row.className = "nb-job-live-log-entry";

      var rawTs = e.timestamp != null ? String(e.timestamp) : "";
      var lvl = e.level != null ? String(e.level) : "";
      var msg = e.message != null ? String(e.message) : "";

      row.dataset.timestamp = rawTs;
      row.dataset.level = lvl;
      row.dataset.raw = msg;

      if (rawTs) {
        var timeEl = document.createElement("span");
        timeEl.className = "text-muted small font-monospace nb-job-live-log-time";
        appendText(timeEl, formatTimestamp(rawTs));
        row.appendChild(timeEl);
      }

      if (lvl) {
        var lvlSpan = document.createElement("span");
        lvlSpan.className = getLevelBadgeClass(lvl);
        appendText(lvlSpan, lvl);
        row.appendChild(lvlSpan);
      }

      row.appendChild(renderMessageContent(msg));

      container.appendChild(row);
    }
  }

  function formatLogEntriesForClipboard(entries) {
    if (!Array.isArray(entries)) return "";
    var lines = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (!e || typeof e !== "object") continue;
      var ts = e.timestamp != null ? String(e.timestamp) : "";
      var lv = e.level != null ? String(e.level) : "";
      var ms = e.message != null ? String(e.message) : "";
      lines.push(ts + " [" + lv + "] " + ms);
    }
    return lines.join("\n");
  }

  function findMessageColumnIndex(table) {
    var headers = table.querySelectorAll("thead tr th");
    if (!headers.length) return -1;
    var i;
    for (i = 0; i < headers.length; i++) {
      if (headers[i].textContent.trim() === "Message") {
        return i;
      }
    }
    if (headers.length === 3) {
      return 2;
    }
    return -1;
  }

  function findJobLogTable() {
    var root = document.querySelector("#page-content") || document.body;
    var tables = root.querySelectorAll("table.table");
    for (var t = 0; t < tables.length; t++) {
      var tbl = tables[t];
      if (tbl.querySelector("thead") && findMessageColumnIndex(tbl) >= 0) {
        return tbl;
      }
    }
    return null;
  }

  function enhanceJobLogTable() {
    if (!/\/jobs\/\d+\/log\/?$/.test(window.location.pathname)) {
      return;
    }

    var table = findJobLogTable();
    if (!table) return;

    var colIdx = findMessageColumnIndex(table);
    if (colIdx < 0) return;

    var rows = table.querySelectorAll("tbody tr");
    for (var r = 0; r < rows.length; r++) {
      var tr = rows[r];
      var cells = tr.querySelectorAll("td");
      if (cells.length <= colIdx) continue;
      var td = cells[colIdx];
      if (td.dataset.nbProxboxEnhanced === "1") continue;

      var text = td.textContent;
      if (!parseProxboxMessage(text)) continue;

      td.replaceChildren();
      td.appendChild(renderMessageContent(text));
      td.dataset.nbProxboxEnhanced = "1";
    }
  }

  function boot() {
    enhanceJobLogTable();
  }

  global.NbProxboxJobLogView = {
    parseProxboxMessage: parseProxboxMessage,
    renderLiveLog: renderLiveLog,
    renderMessageContent: renderMessageContent,
    enhanceJobLogTable: enhanceJobLogTable,
    formatLogEntriesForClipboard: formatLogEntriesForClipboard,
    parseJobProgress: parseJobProgress,
    applyProgress: applyProgress,
    getLevelBadgeClass: getLevelBadgeClass,
    getProgressLabelClass: getProgressLabelClass,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
