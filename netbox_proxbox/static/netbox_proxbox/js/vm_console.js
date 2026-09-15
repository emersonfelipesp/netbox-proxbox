const MAX_AUTO_RETRIES = 2;
const AUTO_RETRY_DELAYS_MS = Object.freeze([1000, 2500]);
const SESSION_RESPONSE_FIELDS = Object.freeze([
  "websocket_url",
  "stream_token",
  "expires_at",
  "console_type",
]);
const STREAM_TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,256}$/;
const SUPPORTED_CONSOLE_TYPES = new Set(["novnc", "term"]);
const RETRYABLE_CLOSE_CODES = new Set([1006, 1012, 1013]);
const TERMINAL_KEEPALIVE_BYTES = new Set([0, 48]);
const DEFAULT_ROWS = 32;
const DEFAULT_COLS = 120;

function decodeBinaryTerminalFrame(raw) {
  const bytes = new Uint8Array(raw);
  if (bytes.length === 0) return { kind: "ignore" };
  if (bytes[0] === 100) return { kind: "data", payload: bytes.subarray(1) };
  if (TERMINAL_KEEPALIVE_BYTES.has(bytes[0])) return { kind: "keepalive" };
  return { kind: "ignore" };
}

function decodeTextTerminalFrame(raw) {
  if (typeof raw !== "string" || raw.length === 0) return { kind: "ignore" };
  if (raw.startsWith("d")) return { kind: "data", payload: raw.slice(1) };
  if (raw === "0" || raw === "\0") return { kind: "keepalive" };
  return { kind: "ignore" };
}

export function decodeTerminalFrame(raw) {
  if (raw instanceof ArrayBuffer) return decodeBinaryTerminalFrame(raw);
  return decodeTextTerminalFrame(raw);
}

export function classifyWebSocketClose(code) {
  if (code === 1008) {
    return {
      retryable: false,
      message: "The console session expired or was already used. Request a new session.",
    };
  }
  if (code === 1011) {
    return {
      retryable: false,
      message: "The console relay reported a server error. Try again when the service is available.",
    };
  }
  if (RETRYABLE_CLOSE_CODES.has(code)) {
    return { retryable: true, message: "The console connection was interrupted." };
  }
  return { retryable: false, message: "The console connection closed." };
}

function detailFailure(detail) {
  if (detail.includes("replay") || detail.includes("already used")) {
    return "That console session was already used. Request a new session.";
  }
  if (detail.includes("expired")) {
    return "The console session expired. Request a new session.";
  }
  return "";
}

function failureForStatus(status) {
  const fixedFailures = {
    401: "You are not authorized to open this console.",
    403: "You are not authorized to open this console.",
    404: "Console access is unavailable for this guest.",
    409: "That console session was already used. Request a new session.",
    410: "The console session expired. Request a new session.",
  };
  if (fixedFailures[status]) return { retryable: false, message: fixedFailures[status] };
  if (status === 429) return { retryable: true, message: "The console service is busy." };
  if (status >= 500) {
    return {
      retryable: status !== 501,
      message: "The console service reported a server error.",
    };
  }
  return { retryable: false, message: "The console session could not be created." };
}

function sessionError(status, payload) {
  const detail = [payload?.detail, payload?.error]
    .filter((value) => typeof value === "string")
    .join(" ")
    .toLowerCase();
  const detailMessage = detailFailure(detail);
  if (detailMessage) return { retryable: false, message: detailMessage };
  return failureForStatus(status);
}

function assertSessionObject(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("The console service returned an invalid response.");
  }
}

function assertKnownSessionFields(payload) {
  const unexpected = Object.keys(payload).filter(
    (field) => !SESSION_RESPONSE_FIELDS.includes(field),
  );
  if (unexpected.length > 0) {
    throw new Error("The console service returned an unexpected response.");
  }
}

function assertSessionValues(payload, requestedType) {
  if (payload.console_type !== requestedType) {
    throw new Error("The console service returned the wrong protocol.");
  }
  if (typeof payload.websocket_url !== "string" || payload.websocket_url.length === 0) {
    throw new Error("The console service did not provide a WebSocket URL.");
  }
  if (typeof payload.expires_at !== "string") {
    throw new Error("The console service returned an invalid expiry time.");
  }
  if (!Number.isFinite(Date.parse(payload.expires_at))) {
    throw new Error("The console service returned an invalid expiry time.");
  }
  if (typeof payload.stream_token !== "string") {
    throw new Error("The console service returned an invalid stream token.");
  }
  if (!STREAM_TOKEN_PATTERN.test(payload.stream_token)) {
    throw new Error("The console service returned an invalid stream token.");
  }
}

function safeWebSocketUrl(value, pageUrl) {
  let websocketUrl;
  try {
    websocketUrl = new URL(value, pageUrl);
  } catch {
    throw new Error("The console service returned an unsafe WebSocket URL.");
  }
  if (websocketUrl.protocol !== "wss:") {
    throw new Error("The console service returned an unsafe WebSocket URL.");
  }
  if (websocketUrl.username || websocketUrl.password) {
    throw new Error("The console service returned an unsafe WebSocket URL.");
  }
  if (websocketUrl.search || websocketUrl.hash) {
    throw new Error("The console service returned an unsafe WebSocket URL.");
  }
  return websocketUrl.href;
}

function readSessionResponse(payload, requestedType, pageUrl) {
  assertSessionObject(payload);
  assertKnownSessionFields(payload);
  assertSessionValues(payload, requestedType);
  return {
    websocket_url: safeWebSocketUrl(payload.websocket_url, pageUrl),
    stream_token: payload.stream_token,
    expires_at: payload.expires_at,
    console_type: payload.console_type,
  };
}

function consoleError(message, retryable = false) {
  const failure = new Error(message);
  failure.retryable = retryable;
  return failure;
}

function clearProtocolList(protocols) {
  protocols.fill("");
  protocols.length = 0;
}

async function responseJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function browserEnvironment() {
  return {
    document,
    window,
    fetch: (...args) => window.fetch(...args),
    WebSocket: window.WebSocket,
    Terminal: window.Terminal,
    ResizeObserver: window.ResizeObserver,
    AbortController: window.AbortController,
    importRfb: (url) => import(url),
    now: () => Date.now(),
  };
}

function consoleElements(documentObject) {
  const ids = {
    statusBadge: "proxbox-console-status",
    typeSelect: "proxbox-console-type",
    connectButton: "proxbox-console-connect",
    connectLabel: "proxbox-console-connect-label",
    disconnectButton: "proxbox-console-disconnect",
    messageElement: "proxbox-console-message",
    placeholder: "proxbox-console-placeholder",
    surface: "proxbox-console-surface",
    novncContainer: "proxbox-console-novnc",
    terminalContainer: "proxbox-console-terminal",
  };
  const entries = Object.entries(ids).map(([name, id]) => [
    name,
    documentObject.getElementById(id),
  ]);
  if (entries.some((entry) => !entry[1])) return null;
  return Object.fromEntries(entries);
}

class ConsoleController {
  constructor(root, elements, environment) {
    this.root = root;
    this.elements = elements;
    this.env = environment;
    this.consoleReady = root.dataset.consoleReady === "true";
    this.vmType = root.dataset.vmType === "lxc" ? "lxc" : "qemu";
    this.sessionUrl = root.dataset.sessionUrl || "";
    this.csrfToken = root.dataset.csrfToken || "";
    this.novncModuleUrl = root.dataset.novncModuleUrl || "";
    this.requestGeneration = 0;
    this.retryAttempt = 0;
    this.requestAbort = null;
    this.reconnectTimer = null;
    this.expiryTimer = null;
    this.resizeFrame = null;
    this.resizeObserver = null;
    this.rfb = null;
    this.rfbHandlers = null;
    this.socket = null;
    this.terminal = null;
    this.terminalInput = null;
    this.streamToken = null;
    this.destroyed = false;
  }

  initialize() {
    if (this.vmType === "lxc") this.elements.typeSelect.value = "term";
    this.elements.connectButton.addEventListener("click", () => this.connect(true));
    this.elements.disconnectButton.addEventListener("click", () => this.disconnect());
    this.elements.typeSelect.addEventListener("change", () => this.disconnect());
    this.env.window.addEventListener("pagehide", () => this.shutdown(), { once: true });
    this.env.window.addEventListener("unload", () => this.shutdown(), { once: true });
    this.setControls("idle");
  }

  setStatus(label, badgeClass, state) {
    this.elements.statusBadge.textContent = label;
    this.elements.statusBadge.className = `badge ${badgeClass}`;
    this.root.dataset.state = state;
  }

  showMessage(message) {
    this.elements.messageElement.textContent = message;
    this.elements.messageElement.classList.toggle("d-none", !message);
  }

  showConsoleView(type) {
    this.elements.placeholder.classList.add("d-none");
    this.elements.novncContainer.classList.toggle("d-none", type !== "novnc");
    this.elements.terminalContainer.classList.toggle("d-none", type !== "term");
  }

  showPlaceholder() {
    this.elements.placeholder.classList.remove("d-none");
    this.elements.novncContainer.classList.add("d-none");
    this.elements.terminalContainer.classList.add("d-none");
  }

  setControls(state) {
    const busy = state === "loading";
    const active = state === "connected" || state === "retrying";
    const labels = {
      connected: "Reconnect",
      error: "Retry",
      idle: "Connect",
      loading: "Connecting",
      retrying: "Reconnect now",
    };
    this.elements.connectButton.disabled = !this.consoleReady || this.destroyed || busy;
    this.elements.disconnectButton.disabled = this.destroyed || (!active && !busy);
    this.elements.typeSelect.disabled =
      !this.consoleReady || this.destroyed || busy || state === "connected";
    this.elements.connectLabel.textContent = labels[state] || "Connect";
  }

  clearTimer(kind) {
    const timer = kind === "expiry" ? this.expiryTimer : this.reconnectTimer;
    if (timer !== null) this.env.window.clearTimeout(timer);
    if (kind === "expiry") this.expiryTimer = null;
    else this.reconnectTimer = null;
  }

  clearResizeResources() {
    if (this.resizeFrame !== null) {
      this.env.window.cancelAnimationFrame(this.resizeFrame);
    }
    this.resizeFrame = null;
    if (this.resizeObserver) this.resizeObserver.disconnect();
    this.resizeObserver = null;
  }

  removeRfbHandlers() {
    if (!this.rfb || !this.rfbHandlers) return;
    Object.entries(this.rfbHandlers).forEach(([name, listener]) => {
      this.rfb.removeEventListener(name, listener);
    });
  }

  disconnectRfb() {
    if (!this.rfb) return;
    this.removeRfbHandlers();
    try {
      this.rfb.disconnect();
    } catch {
      // The transport may already be closed.
    }
    this.rfb = null;
    this.rfbHandlers = null;
    this.elements.novncContainer.textContent = "";
  }

  closeSocket() {
    if (!this.socket) return;
    this.socket.onopen = null;
    this.socket.onmessage = null;
    this.socket.onerror = null;
    this.socket.onclose = null;
    const openStates = new Set([this.env.WebSocket.OPEN, this.env.WebSocket.CONNECTING]);
    if (openStates.has(this.socket.readyState)) {
      this.socket.close(1000, "Client disconnected");
    }
    this.socket = null;
  }

  disconnectTerminal() {
    this.clearResizeResources();
    if (this.terminalInput) this.terminalInput.dispose();
    this.terminalInput = null;
    this.closeSocket();
    if (this.terminal) this.terminal.dispose();
    this.terminal = null;
    this.elements.terminalContainer.textContent = "";
  }

  cleanupTransport() {
    this.clearTimer("expiry");
    this.disconnectRfb();
    this.disconnectTerminal();
    this.clearStreamToken();
  }

  cleanupAttempt() {
    this.clearTimer("reconnect");
    if (this.requestAbort) this.requestAbort.abort();
    this.requestAbort = null;
    this.cleanupTransport();
  }

  enterError(message) {
    this.showPlaceholder();
    this.showMessage(message);
    this.setStatus("Error", "text-bg-danger", "error");
    this.setControls("error");
  }

  retryExhausted() {
    return this.destroyed || this.retryAttempt >= MAX_AUTO_RETRIES;
  }

  scheduleRetry(message) {
    this.cleanupTransport();
    if (this.retryExhausted()) {
      this.enterError(
        `${message} Automatic retries are exhausted; select Retry to request a new session.`,
      );
      return;
    }
    const delay = AUTO_RETRY_DELAYS_MS[this.retryAttempt];
    this.retryAttempt += 1;
    this.showPlaceholder();
    this.showMessage("");
    this.setStatus(
      `Retrying ${this.retryAttempt}/${MAX_AUTO_RETRIES}`,
      "text-bg-warning",
      "retrying",
    );
    this.setControls("retrying");
    this.reconnectTimer = this.env.window.setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect(false);
    }, delay);
  }

  handleTransportClose(message, retryable) {
    if (this.destroyed) return;
    if (retryable) this.scheduleRetry(message);
    else {
      this.cleanupTransport();
      this.enterError(message);
    }
  }

  armExpiry(expiresAt, generation) {
    const remaining = Date.parse(expiresAt) - this.env.now();
    if (remaining <= 0) {
      throw new Error("The console session expired before it could be opened.");
    }
    this.expiryTimer = this.env.window.setTimeout(() => {
      if (this.isStale(generation) || this.root.dataset.state === "connected") return;
      this.cleanupTransport();
      this.enterError(
        "The console session expired before the connection opened. Request a new session.",
      );
    }, Math.min(remaining, 2147483647));
  }

  isStale(generation) {
    return this.destroyed || generation !== this.requestGeneration;
  }

  markConnected() {
    this.clearTimer("expiry");
    this.showMessage("");
    this.setStatus("Connected", "text-bg-success", "connected");
    this.setControls("connected");
  }

  focusNoVnc() {
    this.env.window.requestAnimationFrame(() => {
      const canvas = this.elements.novncContainer.querySelector("canvas");
      const focusTarget = canvas || this.elements.novncContainer;
      if (canvas) canvas.tabIndex = 0;
      focusTarget.focus();
    });
  }

  onRfbConnect(generation) {
    if (this.isStale(generation)) return;
    this.markConnected();
    this.focusNoVnc();
  }

  onRfbDisconnect(generation, event) {
    if (this.isStale(generation)) return;
    this.handleTransportClose(
      "The graphical console disconnected.",
      event.detail?.clean === false,
    );
  }

  onRfbSecurityFailure(generation) {
    if (this.isStale(generation)) return;
    this.handleTransportClose("The console relay rejected the graphical session.", false);
  }

  onRfbCredentialsRequired(generation) {
    if (this.isStale(generation)) return;
    this.handleTransportClose(
      "Server-side console authentication could not be completed.",
      false,
    );
  }

  attachRfbHandlers(generation) {
    this.rfbHandlers = {
      connect: () => this.onRfbConnect(generation),
      disconnect: (event) => this.onRfbDisconnect(generation, event),
      securityfailure: () => this.onRfbSecurityFailure(generation),
      credentialsrequired: () => this.onRfbCredentialsRequired(generation),
    };
    Object.entries(this.rfbHandlers).forEach(([name, listener]) => {
      this.rfb.addEventListener(name, listener);
    });
  }

  async loadRfb() {
    try {
      return await this.env.importRfb(this.novncModuleUrl);
    } catch {
      throw new Error("The noVNC client could not be loaded.");
    }
  }

  storeStreamToken(value, generation) {
    this.streamToken = { value, generation };
  }

  connectionProtocols(generation) {
    const storedToken = this.streamToken;
    if (
      !storedToken ||
      storedToken.generation !== generation ||
      !STREAM_TOKEN_PATTERN.test(storedToken.value)
    ) {
      throw new Error("The console service returned an invalid stream token.");
    }
    return ["binary", `proxbox-token.${storedToken.value}`];
  }

  clearStreamToken(generation) {
    if (generation === undefined || this.streamToken?.generation === generation) {
      this.streamToken = null;
    }
  }

  createRfb(RFB, session, generation) {
    const protocols = this.connectionProtocols(generation);
    try {
      return new RFB(this.elements.novncContainer, session.websocket_url, {
        wsProtocols: protocols,
      });
    } catch {
      throw new Error("The graphical console could not be initialized.");
    } finally {
      clearProtocolList(protocols);
    }
  }

  async connectNoVnc(session, generation) {
    if (!this.novncModuleUrl) throw new Error("The noVNC client is unavailable.");
    const novncModule = await this.loadRfb();
    if (this.isStale(generation)) return;
    const RFB = novncModule.default;
    if (typeof RFB !== "function") throw new Error("The noVNC client is unavailable.");
    this.showConsoleView("novnc");
    this.rfb = this.createRfb(RFB, session, generation);
    this.rfb.scaleViewport = true;
    this.rfb.resizeSession = true;
    this.rfb.viewOnly = false;
    this.attachRfbHandlers(generation);
  }

  terminalDimensions() {
    const rect = this.elements.terminalContainer.getBoundingClientRect();
    return {
      cols: Math.max(40, Math.min(240, Math.floor(Math.max(rect.width - 24, 320) / 8))),
      rows: Math.max(12, Math.min(100, Math.floor(Math.max(rect.height - 24, 216) / 18))),
    };
  }

  sendTerminalResize() {
    if (!this.terminal) return;
    const { cols, rows } = this.terminalDimensions();
    if (this.terminal.cols !== cols || this.terminal.rows !== rows) {
      this.terminal.resize(cols, rows);
    }
    if (this.socket?.readyState === this.env.WebSocket.OPEN) {
      this.socket.send(`1:${this.terminal.rows}:${this.terminal.cols}:0`);
    }
  }

  scheduleTerminalResize() {
    if (this.resizeFrame !== null) {
      this.env.window.cancelAnimationFrame(this.resizeFrame);
    }
    this.resizeFrame = this.env.window.requestAnimationFrame(() => {
      this.resizeFrame = null;
      this.sendTerminalResize();
    });
  }

  createTerminal() {
    return new this.env.Terminal({
      allowProposedApi: false,
      cols: DEFAULT_COLS,
      rows: DEFAULT_ROWS,
      convertEol: true,
      cursorBlink: true,
      cursorStyle: "bar",
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.25,
      scrollback: 1000,
      theme: {
        background: "#07090d",
        foreground: "#d7dde8",
        cursor: "#7dd3fc",
        selectionBackground: "#2563eb66",
      },
    });
  }

  createSocket(url, generation) {
    const protocols = this.connectionProtocols(generation);
    try {
      return new this.env.WebSocket(url, protocols);
    } catch {
      throw new Error("The terminal connection could not be initialized.");
    } finally {
      clearProtocolList(protocols);
    }
  }

  onTerminalOpen(generation) {
    if (this.isStale(generation)) return;
    this.sendTerminalResize();
    this.markConnected();
    this.terminal.focus();
  }

  onTerminalMessage(generation, event) {
    if (this.isStale(generation)) return;
    const frame = decodeTerminalFrame(event.data);
    if (frame.kind === "data") this.terminal.write(frame.payload);
    if (frame.kind === "keepalive") this.sendKeepalive();
  }

  sendKeepalive() {
    if (this.socket.readyState === this.env.WebSocket.OPEN) this.socket.send("0");
  }

  onTerminalError(generation) {
    if (this.isStale(generation)) return;
    this.setStatus("Connection error", "text-bg-danger", "loading");
  }

  onTerminalClose(generation, event) {
    if (this.isStale(generation)) return;
    const outcome = classifyWebSocketClose(event.code);
    this.handleTransportClose(outcome.message, outcome.retryable);
  }

  attachTerminalHandlers(generation) {
    this.socket.onopen = () => this.onTerminalOpen(generation);
    this.socket.onmessage = (event) => this.onTerminalMessage(generation, event);
    this.socket.onerror = () => this.onTerminalError(generation);
    this.socket.onclose = (event) => this.onTerminalClose(generation, event);
    this.terminalInput = this.terminal.onData((data) => {
      if (this.socket?.readyState === this.env.WebSocket.OPEN) this.socket.send(data);
    });
  }

  connectTerminal(session, generation) {
    if (typeof this.env.Terminal !== "function") {
      throw new Error("The terminal client is unavailable.");
    }
    this.showConsoleView("term");
    this.terminal = this.createTerminal();
    this.terminal.open(this.elements.terminalContainer);
    this.scheduleTerminalResize();
    this.socket = this.createSocket(session.websocket_url, generation);
    this.socket.binaryType = "arraybuffer";
    this.attachTerminalHandlers(generation);
    this.resizeObserver = new this.env.ResizeObserver(() => this.scheduleTerminalResize());
    this.resizeObserver.observe(this.elements.surface);
  }

  async createSession(consoleType, signal) {
    let response;
    try {
      response = await this.env.fetch(this.sessionUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": this.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ console_type: consoleType }),
        signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw consoleError("The console session request could not reach the server.", true);
    }
    const payload = await responseJson(response);
    if (!response.ok) {
      const outcome = sessionError(response.status, payload);
      throw consoleError(outcome.message, outcome.retryable);
    }
    return readSessionResponse(payload, consoleType, this.env.window.location.href);
  }

  selectedConsoleType() {
    if (this.vmType === "lxc") return "term";
    return this.elements.typeSelect.value;
  }

  canConnect() {
    return this.consoleReady && !this.destroyed && Boolean(this.sessionUrl);
  }

  releaseRequest(requestAbort) {
    if (this.requestAbort === requestAbort) this.requestAbort = null;
  }

  prepareConnection() {
    this.showPlaceholder();
    this.showMessage("");
    this.setStatus("Connecting", "text-bg-warning", "loading");
    this.setControls("loading");
  }

  async openSession(consoleType, generation, requestAbort) {
    const session = await this.createSession(consoleType, requestAbort.signal);
    this.releaseRequest(requestAbort);
    try {
      if (this.isStale(generation)) return;
      this.armExpiry(session.expires_at, generation);
      this.storeStreamToken(session.stream_token, generation);
      if (session.console_type === "novnc") await this.connectNoVnc(session, generation);
      else this.connectTerminal(session, generation);
    } finally {
      this.clearStreamToken(generation);
      session.stream_token = "";
    }
  }

  ignoreFailure(error, generation) {
    return this.isStale(generation) || error?.name === "AbortError";
  }

  handleConnectionFailure(error, generation, requestAbort) {
    this.releaseRequest(requestAbort);
    if (this.ignoreFailure(error, generation)) return;
    if (error?.retryable) this.scheduleRetry(error.message);
    else {
      this.cleanupTransport();
      this.enterError(error?.message || "The console could not be opened.");
    }
  }

  async connect(resetRetries = true) {
    if (!this.canConnect()) return;
    this.cleanupAttempt();
    if (resetRetries) this.retryAttempt = 0;
    const generation = ++this.requestGeneration;
    const consoleType = this.selectedConsoleType();
    if (!SUPPORTED_CONSOLE_TYPES.has(consoleType)) {
      this.enterError("Select a supported console protocol.");
      return;
    }
    this.prepareConnection();
    const requestAbort = new this.env.AbortController();
    this.requestAbort = requestAbort;
    try {
      await this.openSession(consoleType, generation, requestAbort);
    } catch (error) {
      this.handleConnectionFailure(error, generation, requestAbort);
    }
  }

  disconnect() {
    this.requestGeneration += 1;
    this.retryAttempt = 0;
    this.cleanupAttempt();
    this.showPlaceholder();
    this.showMessage("");
    this.setStatus("Disconnected", "text-bg-secondary", "idle");
    this.setControls("idle");
  }

  shutdown() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.requestGeneration += 1;
    this.cleanupAttempt();
  }
}

export function createConsoleController(root, environment) {
  const activeEnvironment = environment || browserEnvironment();
  const elements = consoleElements(activeEnvironment.document);
  if (!elements) return null;
  const controller = new ConsoleController(root, elements, activeEnvironment);
  controller.initialize();
  return controller;
}

if (typeof document !== "undefined") {
  const consoleRoot = document.getElementById("proxbox-vm-console");
  if (consoleRoot) createConsoleController(consoleRoot);
}
