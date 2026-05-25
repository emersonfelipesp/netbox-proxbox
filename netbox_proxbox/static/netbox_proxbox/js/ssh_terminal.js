(function () {
  const terminalElement = document.getElementById("proxbox-ssh-terminal");
  if (!terminalElement) return;

  const statusBadge = document.getElementById("proxbox-terminal-status");
  const targetSelect = document.getElementById("proxbox-terminal-target");
  const nodeSelect = document.getElementById("proxbox-terminal-node");
  const connectButton = document.getElementById("proxbox-terminal-connect");
  const disconnectButton = document.getElementById("proxbox-terminal-disconnect");
  const nodesElement = document.getElementById("proxbox-ssh-nodes");
  const nodes = nodesElement ? JSON.parse(nodesElement.textContent || "[]") : [];

  let socket = null;
  let terminal = null;
  let connected = false;

  function setStatus(label, className) {
    if (!statusBadge) return;
    statusBadge.textContent = label;
    statusBadge.className = `badge ${className}`;
  }

  function terminalSize() {
    const rect = terminalElement.getBoundingClientRect();
    return {
      cols: Math.max(80, Math.min(220, Math.floor(rect.width / 9))),
      rows: Math.max(24, Math.min(80, Math.floor(rect.height / 18))),
    };
  }

  function resizeTerminal() {
    if (!terminal) return terminalSize();
    const size = terminalSize();
    terminal.resize(size.cols, size.rows);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "resize", cols: size.cols, rows: size.rows }));
    }
    return size;
  }

  function ensureTerminal() {
    if (!window.Terminal) {
      terminalElement.textContent = "xterm.js is not available.";
      return null;
    }
    if (terminal) return terminal;
    terminal = new window.Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.15,
      scrollback: 5000,
      theme: {
        background: "#101418",
        foreground: "#e5edf4",
        cursor: "#f6c177",
        selectionBackground: "#2d4f67",
      },
    });
    terminal.open(terminalElement);
    resizeTerminal();
    terminal.onData((data) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "input", data }));
      }
    });
    return terminal;
  }

  function selectedPayload() {
    const size = resizeTerminal();
    const targetType = targetSelect ? targetSelect.value : "endpoint";
    const payload = {
      target_type: targetType,
      cols: size.cols,
      rows: size.rows,
    };
    if (targetType === "node") {
      payload.node_id = Number(nodeSelect.value);
    }
    return payload;
  }

  function setConnectedState(isConnected) {
    connected = isConnected;
    const hasTarget =
      targetSelect &&
      targetSelect.selectedOptions.length > 0 &&
      !targetSelect.selectedOptions[0].disabled;
    if (connectButton) connectButton.disabled = isConnected || !hasTarget;
    if (disconnectButton) disconnectButton.disabled = !isConnected;
    if (targetSelect) targetSelect.disabled = isConnected;
    if (nodeSelect) nodeSelect.disabled = isConnected || targetSelect.value !== "node";
  }

  async function createSession() {
    const response = await fetch(terminalElement.dataset.sessionUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": terminalElement.dataset.csrfToken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(selectedPayload()),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || "Could not create SSH terminal session.");
    }
    return data;
  }

  async function connect() {
    const term = ensureTerminal();
    if (!term) return;
    term.clear();
    setConnectedState(true);
    setStatus("Connecting", "text-bg-warning");
    try {
      const session = await createSession();
      socket = new WebSocket(session.websocket_url);
      socket.addEventListener("open", () => {
        socket.send(JSON.stringify({ type: "auth", ticket: session.ticket }));
      });
      socket.addEventListener("message", (event) => {
        const frame = JSON.parse(event.data);
        if (frame.type === "ready") {
          setStatus("Connected", "text-bg-success");
          return;
        }
        if (frame.type === "output") {
          term.write(frame.data || "");
          return;
        }
        if (frame.type === "error") {
          term.writeln(`\r\n${frame.message || "SSH terminal error"}`);
          setStatus("Error", "text-bg-danger");
          return;
        }
        if (frame.type === "exit") {
          setStatus("Disconnected", "text-bg-secondary");
          setConnectedState(false);
        }
      });
      socket.addEventListener("close", () => {
        setStatus("Disconnected", "text-bg-secondary");
        setConnectedState(false);
      });
      socket.addEventListener("error", () => {
        setStatus("Error", "text-bg-danger");
        setConnectedState(false);
      });
    } catch (error) {
      term.writeln(String(error.message || error));
      setStatus("Error", "text-bg-danger");
      setConnectedState(false);
    }
  }

  function disconnect() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "close" }));
      socket.close();
    }
    setConnectedState(false);
    setStatus("Disconnected", "text-bg-secondary");
  }

  function refreshTargetControls() {
    if (!targetSelect || !nodeSelect) return;
    if (targetSelect.selectedOptions[0] && targetSelect.selectedOptions[0].disabled) {
      const firstEnabled = Array.from(targetSelect.options).find((option) => !option.disabled);
      if (firstEnabled) targetSelect.value = firstEnabled.value;
    }
    nodeSelect.disabled = targetSelect.value !== "node" || nodes.length === 0;
    setConnectedState(connected);
  }

  if (connectButton) connectButton.addEventListener("click", connect);
  if (disconnectButton) disconnectButton.addEventListener("click", disconnect);
  if (targetSelect) targetSelect.addEventListener("change", refreshTargetControls);
  window.addEventListener("resize", resizeTerminal);
  refreshTargetControls();
})();
