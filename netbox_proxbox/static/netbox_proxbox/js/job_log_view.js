/**
 * Parse and render Proxbox stream log lines as NetBox-like Bootstrap tables (textContent only).
 */
(function (global) {
  "use strict";

  var MAX_DEPTH = 6;
  var STREAM_PREFIX = "[proxbox-stream]";
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
    var pre = document.createElement("pre");
    pre.className = "mb-0 small font-monospace";
    pre.textContent = text;
    return pre;
  }

  function renderPlainLine(text) {
    var p = document.createElement("p");
    p.className = "mb-0 small";
    appendText(p, text);
    return p;
  }

  function renderKeyValueTable(value, depth) {
    depth = depth || 0;
    if (depth > MAX_DEPTH) {
      var fallback = document.createElement("span");
      fallback.className = "small text-muted";
      appendText(fallback, "[max depth]");
      return fallback;
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
        var empty = document.createElement("em");
        empty.className = "text-muted small";
        appendText(empty, "[]");
        return empty;
      }
      var arrTable = document.createElement("table");
      arrTable.className =
        "table table-sm table-bordered table-hover mb-0 align-middle";
      var arrBody = document.createElement("tbody");
      for (var i = 0; i < value.length; i++) {
        var tr = document.createElement("tr");
        var th = document.createElement("th");
        th.className = "text-muted small";
        th.scope = "row";
        appendText(th, String(i));
        var td = document.createElement("td");
        td.appendChild(renderKeyValueTable(value[i], depth + 1));
        tr.appendChild(th);
        tr.appendChild(td);
        arrBody.appendChild(tr);
      }
      arrTable.appendChild(arrBody);
      return arrTable;
    }

    var keys = Object.keys(value);
    if (keys.length === 0) {
      var objEmpty = document.createElement("em");
      objEmpty.className = "text-muted small";
      appendText(objEmpty, "{}");
      return objEmpty;
    }

    var table = document.createElement("table");
    table.className =
      "table table-sm table-bordered table-hover mb-0 align-middle object-list";
    var tbody = document.createElement("tbody");
    for (var k = 0; k < keys.length; k++) {
      var key = keys[k];
      var row = document.createElement("tr");
      var thKey = document.createElement("th");
      thKey.className = "text-muted small text-nowrap";
      thKey.scope = "row";
      appendText(thKey, key);
      var tdVal = document.createElement("td");
      tdVal.className = "small";
      tdVal.appendChild(renderKeyValueTable(value[key], depth + 1));
      row.appendChild(thKey);
      row.appendChild(tdVal);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }

  function renderParsed(parsed) {
    var wrap = document.createElement("div");
    wrap.className = "nb-proxbox-parsed-msg";

    var badge = document.createElement("span");
    badge.className = "badge bg-secondary me-2";
    appendText(badge, parsed.event);
    wrap.appendChild(badge);

    if (parsed.parseError || parsed.data === null) {
      var raw = parsed.rawSuffix || "";
      wrap.appendChild(renderRawJson(raw));
      return wrap;
    }

    wrap.appendChild(renderKeyValueTable(parsed.data, 0));
    return wrap;
  }

  function renderMessageContent(msg) {
    var parsed = parseProxboxMessage(msg);
    if (parsed) {
      return renderParsed(parsed);
    }
    return renderPlainLine(msg);
  }

  function renderLiveLog(container, entries) {
    if (!container) return;
    container.replaceChildren();

    if (!Array.isArray(entries) || entries.length === 0) {
      var empty = document.createElement("p");
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
      row.className =
        "nb-job-live-log-entry border-bottom pb-2 mb-2 border-secondary border-opacity-25";

      var head = document.createElement("div");
      head.className = "d-flex flex-wrap align-items-center gap-2 mb-1";

      var t = e.timestamp != null ? String(e.timestamp) : "";
      if (t) {
        var timeEl = document.createElement("span");
        timeEl.className = "text-muted small font-monospace";
        appendText(timeEl, t);
        head.appendChild(timeEl);
      }

      var lvl = e.level != null ? String(e.level) : "";
      if (lvl) {
        var lvlSpan = document.createElement("span");
        lvlSpan.className = "badge text-bg-secondary text-uppercase";
        appendText(lvlSpan, lvl);
        head.appendChild(lvlSpan);
      }

      row.appendChild(head);

      var msg = e.message != null ? String(e.message) : "";
      var body = document.createElement("div");
      body.className = "nb-job-live-log-body";
      body.appendChild(renderMessageContent(msg));
      row.appendChild(body);

      container.appendChild(row);
    }
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
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
