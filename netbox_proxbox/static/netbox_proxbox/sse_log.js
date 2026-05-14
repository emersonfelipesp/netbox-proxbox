(function () {
  "use strict";

  var log = document.getElementById("apply-sse-log");
  if (!log) {
    return;
  }

  var streamUrl = log.getAttribute("data-sse-url");
  if (!streamUrl) {
    return;
  }

  function append(line, className) {
    var span = document.createElement("span");
    if (className) {
      span.className = className;
    }
    span.textContent = line + "\n";
    log.appendChild(span);
    log.scrollTop = log.scrollHeight;
  }

  function parsePayload(raw) {
    try {
      return JSON.parse(raw);
    } catch (error) {
      return { message: raw };
    }
  }

  function formatPayload(prefix, raw) {
    var payload = parsePayload(raw || "");
    var message = payload.message || payload.summary || payload.status || raw;
    return prefix + " " + message;
  }

  if (!window.EventSource) {
    append("EventSource is not supported by this browser.", "text-warning");
    return;
  }

  log.textContent = "";
  append("Opening apply job stream...", "text-muted");

  var source = new EventSource(streamUrl);

  source.addEventListener("open", function () {
    append("Stream connected.", "text-muted");
  });

  source.addEventListener("message", function (event) {
    append(formatPayload("[log]", event.data));
  });

  source.addEventListener("step", function (event) {
    append(formatPayload("[step]", event.data));
  });

  source.addEventListener("plan_summary", function (event) {
    var payload = parsePayload(event.data || "{}");
    var verdicts = payload.verdicts || [];
    append("[plan] " + verdicts.length + " verdict(s)");
    verdicts.forEach(function (verdict) {
      append(
        "  vmid=" + (verdict.vmid || "-") +
          " verdict=" + (verdict.verdict || verdict.level || "-") +
          " " + (verdict.message || "")
      );
    });
  });

  source.addEventListener("dispatch", function (event) {
    var payload = parsePayload(event.data || "{}");
    append(
      "[dispatch] vmid=" + (payload.vmid || "-") +
        " op=" + (payload.op || "-") +
        " kind=" + (payload.kind || "-") +
        " status=" + (payload.status || "-") +
        (payload.message ? " " + payload.message : "")
    );
  });

  source.addEventListener("complete", function (event) {
    append(formatPayload("[complete]", event.data), "text-success");
    source.close();
  });

  source.addEventListener("error", function (event) {
    if (event.data) {
      append(formatPayload("[error]", event.data), "text-danger");
    }
    if (source.readyState === EventSource.CLOSED) {
      append("Stream closed.", "text-muted");
    }
  });
})();
