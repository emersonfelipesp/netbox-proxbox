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

    var root = document.createElement("div");
    root.className = "nb-proxbox-inline";

    for (var k = 0; k < keys.length; k++) {
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
    badge.className = "badge bg-secondary me-2 align-middle";
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

      var t = e.timestamp != null ? String(e.timestamp) : "";
      if (t) {
        var timeEl = document.createElement("span");
        timeEl.className = "text-muted small font-monospace";
        appendText(timeEl, t);
        row.appendChild(timeEl);
      }

      var lvl = e.level != null ? String(e.level) : "";
      if (lvl) {
        var lvlSpan = document.createElement("span");
        lvlSpan.className = "badge text-bg-secondary text-uppercase";
        appendText(lvlSpan, lvl);
        row.appendChild(lvlSpan);
      }

      var msg = e.message != null ? String(e.message) : "";
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
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
