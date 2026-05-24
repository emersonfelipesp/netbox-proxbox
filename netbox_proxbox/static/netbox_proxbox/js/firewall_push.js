(function () {
  function csrfToken() {
    var token = document.cookie
      .split(";")
      .map(function (part) {
        return part.trim();
      })
      .find(function (part) {
        return part.indexOf("csrftoken=") === 0;
      });
    return token ? decodeURIComponent(token.split("=")[1]) : "";
  }

  function asText(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    if (typeof value === "object") {
      return JSON.stringify(value);
    }
    return String(value);
  }

  function setStatus(element, message, className) {
    if (!element) {
      return;
    }
    element.className = className || "ms-2 small text-muted";
    element.textContent = message;
  }

  function initPushForms() {
    document.querySelectorAll("[data-firewall-push-form]").forEach(function (form) {
      if (form.dataset.firewallPushReady === "true") {
        return;
      }
      form.dataset.firewallPushReady = "true";
      form.addEventListener("submit", function (event) {
        var apiUrl = form.dataset.firewallApiUrl;
        if (!apiUrl || !window.fetch) {
          return;
        }
        event.preventDefault();
        var button = form.querySelector("button[type='submit']");
        var status = form.querySelector("[data-firewall-push-status]");
        if (button) {
          button.disabled = true;
        }
        setStatus(status, "Pushing...", "ms-2 small text-muted");
        fetch(apiUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: "{}",
        })
          .then(function (response) {
            return response.json().then(function (payload) {
              return { ok: response.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok || result.payload.status === "error") {
              setStatus(
                status,
                result.payload.detail || result.payload.reason || "Push failed",
                "ms-2 small text-danger",
              );
              return;
            }
            setStatus(status, result.payload.status || "pushed", "ms-2 small text-success");
          })
          .catch(function (error) {
            setStatus(status, error.message, "ms-2 small text-danger");
          })
          .finally(function () {
            if (button) {
              button.disabled = false;
            }
          });
      });
    });
  }

  function initPreviewPanels() {
    document.querySelectorAll("[data-firewall-preview-panel]").forEach(function (panel) {
      if (panel.dataset.firewallPreviewReady === "true") {
        return;
      }
      panel.dataset.firewallPreviewReady = "true";
      var url = panel.dataset.firewallPreviewUrl;
      var status = panel.querySelector("[data-firewall-preview-status]");
      var wrap = panel.querySelector("[data-firewall-preview-table-wrap]");
      var rows = panel.querySelector("[data-firewall-preview-rows]");
      if (!url || !window.fetch || !rows) {
        return;
      }
      fetch(url, { credentials: "same-origin" })
        .then(function (response) {
          return response.json();
        })
        .then(function (payload) {
          var netboxState = payload.netbox_state || {};
          var proxmoxState = payload.proxmox_state || {};
          var differing = payload.differing_fields || [];
          var fields = Object.keys(Object.assign({}, netboxState, proxmoxState)).sort();
          rows.innerHTML = "";
          fields.forEach(function (field) {
            var row = document.createElement("tr");
            if (differing.indexOf(field) !== -1) {
              row.className = "table-warning";
            }
            [field, asText(netboxState[field]), asText(proxmoxState[field])].forEach(
              function (value) {
                var cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
              },
            );
            rows.appendChild(row);
          });
          if (wrap) {
            wrap.classList.remove("d-none");
          }
          setStatus(
            status,
            payload.detail || payload.reason || payload.status || "ready",
            "text-muted small",
          );
        })
        .catch(function (error) {
          setStatus(status, error.message, "text-danger small");
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initPushForms();
    initPreviewPanels();
  });
})();
