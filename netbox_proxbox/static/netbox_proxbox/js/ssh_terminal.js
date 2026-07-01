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

  const endpointId = terminalElement.dataset.endpointId || "";
  const endpointReady = terminalElement.dataset.endpointReady === "true";
  const canStore = terminalElement.dataset.canStore === "true";
  const SSH_CRED_API_BASE = "/api/plugins/proxbox/ssh-credentials/";

  // Modal elements (may be absent if the template did not render them).
  const modalElement = document.getElementById("proxbox-ssh-cred-modal");
  const modalOpenTrigger = document.getElementById("proxbox-cred-open");
  const modalCloseTrigger = document.getElementById("proxbox-cred-close");
  const hasModal = Boolean(modalElement);

  // Open/close via the Bootstrap instance when the JS global is exposed, else
  // fall back to the declarative data-API (hidden trigger/dismiss buttons) —
  // the same mechanism the plugin's other modals rely on, so it works whether
  // or not NetBox exposes `window.bootstrap`.
  function showModal() {
    if (window.bootstrap && modalElement) {
      window.bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } else if (modalOpenTrigger) {
      modalOpenTrigger.click();
    }
  }
  function hideModal() {
    if (window.bootstrap && modalElement) {
      const instance = window.bootstrap.Modal.getInstance(modalElement);
      if (instance) instance.hide();
      else if (modalCloseTrigger) modalCloseTrigger.click();
    } else if (modalCloseTrigger) {
      modalCloseTrigger.click();
    }
  }
  const credTargetLabel = document.getElementById("proxbox-cred-target-label");
  const credUsername = document.getElementById("proxbox-cred-username");
  const credPort = document.getElementById("proxbox-cred-port");
  const credAuth = document.getElementById("proxbox-cred-auth");
  const credPasswordGroup = document.getElementById("proxbox-cred-password-group");
  const credPassword = document.getElementById("proxbox-cred-password");
  const credKeyGroup = document.getElementById("proxbox-cred-key-group");
  const credKey = document.getElementById("proxbox-cred-key");
  const credFingerprint = document.getElementById("proxbox-cred-fingerprint");
  const credScanButton = document.getElementById("proxbox-cred-scan");
  const credSubmit = document.getElementById("proxbox-cred-submit");
  const credError = document.getElementById("proxbox-cred-error");
  const storeSaveRadio = document.getElementById("proxbox-cred-store-save");

  let socket = null;
  let terminal = null;
  let connected = false;
  // Credential typed into the modal for the next connect (one-shot or store).
  let pendingCredential = null;
  let pendingStore = false;

  function setStatus(label, className) {
    if (!statusBadge) return;
    statusBadge.textContent = label;
    statusBadge.className = `badge ${className}`;
  }

  function nodeById(id) {
    return nodes.find((node) => String(node.id) === String(id)) || null;
  }

  function currentTargetType() {
    return targetSelect ? targetSelect.value : "endpoint";
  }

  function targetHasStoredCredential() {
    if (currentTargetType() === "node") {
      const node = nodeById(nodeSelect ? nodeSelect.value : "");
      return Boolean(node && node.ssh_ready);
    }
    return endpointReady;
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
    const targetType = currentTargetType();
    const payload = {
      target_type: targetType,
      cols: size.cols,
      rows: size.rows,
    };
    if (targetType === "node") {
      payload.node_id = Number(nodeSelect.value);
    }
    if (pendingCredential) {
      payload.credential = pendingCredential;
      payload.store = pendingStore;
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
    const payload = selectedPayload();
    const response = await fetch(terminalElement.dataset.sessionUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": terminalElement.dataset.csrfToken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || "Could not create SSH terminal session.");
    }
    // A successful store request means the credential now exists server-side —
    // mark the node ready so a reconnect uses the stored path.
    if (payload.store && payload.target_type === "node") {
      const node = nodeById(payload.node_id);
      if (node) node.ssh_ready = true;
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
          maybePromptOnError(frame.message || "");
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
        // A one-shot credential is single-use; drop it so the next connect
        // re-prompts. Stored credentials persist server-side.
        if (!pendingStore) pendingCredential = null;
      });
      socket.addEventListener("error", () => {
        setStatus("Error", "text-bg-danger");
        setConnectedState(false);
      });
    } catch (error) {
      term.writeln(String(error.message || error));
      setStatus("Error", "text-bg-danger");
      setConnectedState(false);
      maybePromptOnError(String(error.message || error));
    }
  }

  function maybePromptOnError(message) {
    // Fallback trigger: if the backend reports a missing credential, offer the
    // modal even when the per-node readiness flag said otherwise.
    if (hasModal && /No SSH credential registered/i.test(message)) {
      pendingCredential = null;
      openCredentialModal();
    }
  }

  function onConnectClick() {
    if (!targetHasStoredCredential() && !pendingCredential && hasModal) {
      openCredentialModal();
      return;
    }
    connect();
  }

  function showCredError(message) {
    if (!credError) return;
    if (message) {
      credError.textContent = message;
      credError.classList.remove("d-none");
    } else {
      credError.textContent = "";
      credError.classList.add("d-none");
    }
  }

  function toggleAuthFields() {
    if (!credAuth) return;
    const isKey = credAuth.value === "key";
    if (credKeyGroup) credKeyGroup.classList.toggle("d-none", !isKey);
    if (credPasswordGroup) credPasswordGroup.classList.toggle("d-none", isKey);
  }

  function openCredentialModal() {
    if (!hasModal) return;
    showCredError("");
    const targetType = currentTargetType();
    if (credTargetLabel) {
      if (targetType === "node") {
        const node = nodeById(nodeSelect ? nodeSelect.value : "");
        credTargetLabel.textContent = node
          ? `Node ${node.name} (${node.host})`
          : "Selected node";
      } else {
        credTargetLabel.textContent = "Endpoint SSH host";
      }
    }
    // Endpoint credentials are stored from the SSH settings tab, so only the
    // one-shot option applies for endpoint targets.
    if (storeSaveRadio) {
      const onceRadio = document.getElementById("proxbox-cred-store-once");
      const disableStore = targetType === "endpoint" || !canStore;
      storeSaveRadio.disabled = disableStore;
      if (disableStore && onceRadio) onceRadio.checked = true;
    }
    toggleAuthFields();
    showModal();
  }

  async function scanHostKey() {
    if (!credFingerprint) return;
    const targetType = currentTargetType();
    let url;
    if (targetType === "node") {
      const nodeId = nodeSelect ? Number(nodeSelect.value) : 0;
      const port = credPort ? Number(credPort.value) || 22 : 22;
      url = `${SSH_CRED_API_BASE}by-node/${nodeId}/host-key-fingerprint/?port=${port}`;
    } else {
      url = `${SSH_CRED_API_BASE}by-endpoint/${endpointId}/host-key-fingerprint/`;
    }
    showCredError("");
    if (credScanButton) credScanButton.disabled = true;
    try {
      const response = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || "Host-key scan failed.");
      }
      credFingerprint.value = data.fingerprint || "";
      if (!data.fingerprint) {
        showCredError("The backend returned an empty fingerprint.");
      }
    } catch (error) {
      showCredError(String(error.message || error));
    } finally {
      if (credScanButton) credScanButton.disabled = false;
    }
  }

  function submitCredential() {
    const username = credUsername ? credUsername.value.trim() : "";
    const fingerprint = credFingerprint ? credFingerprint.value.trim() : "";
    const authMethod = credAuth ? credAuth.value : "password";
    const password = credPassword ? credPassword.value : "";
    const privateKey = credKey ? credKey.value : "";
    let port = credPort ? Number(credPort.value) : 22;
    if (!Number.isInteger(port) || port < 1 || port > 65535) port = 22;

    if (!username) {
      showCredError("SSH username is required.");
      return;
    }
    if (authMethod === "password" && !password) {
      showCredError("Password is required for password authentication.");
      return;
    }
    if (authMethod === "key" && !privateKey.trim()) {
      showCredError("Private key is required for key authentication.");
      return;
    }
    if (!fingerprint) {
      showCredError('Fetch and accept the host key first ("Fetch host key").');
      return;
    }

    const credential = {
      username,
      port,
      auth_method: authMethod,
      known_host_fingerprint: fingerprint,
    };
    if (authMethod === "key") {
      credential.private_key = privateKey;
    } else {
      credential.password = password;
    }
    pendingCredential = credential;
    pendingStore = Boolean(
      storeSaveRadio && storeSaveRadio.checked && !storeSaveRadio.disabled
    );
    hideModal();
    connect();
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

  if (connectButton) connectButton.addEventListener("click", onConnectClick);
  if (disconnectButton) disconnectButton.addEventListener("click", disconnect);
  if (targetSelect) targetSelect.addEventListener("change", refreshTargetControls);
  if (credAuth) credAuth.addEventListener("change", toggleAuthFields);
  if (credScanButton) credScanButton.addEventListener("click", scanHostKey);
  if (credSubmit) credSubmit.addEventListener("click", submitCredential);
  window.addEventListener("resize", resizeTerminal);
  refreshTargetControls();
})();
