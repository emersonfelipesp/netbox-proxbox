import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const modulePath = process.argv[2];
assert.ok(modulePath, "vm_console.js path is required");
const { createConsoleController, decodeTerminalFrame, classifyWebSocketClose } =
  await import(pathToFileURL(modulePath).href);

const ELEMENT_IDS = [
  "proxbox-console-status",
  "proxbox-console-type",
  "proxbox-console-connect",
  "proxbox-console-connect-label",
  "proxbox-console-disconnect",
  "proxbox-console-message",
  "proxbox-console-placeholder",
  "proxbox-console-surface",
  "proxbox-console-novnc",
  "proxbox-console-terminal",
];
const STREAM_TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE";

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }

  toggle(value, force) {
    if (force) this.add(value);
    else this.remove(value);
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.classList = new FakeClassList();
    this.dataset = {};
    this.listeners = new Map();
    this.textContent = "";
    this.className = "";
    this.disabled = false;
    this.value = "novnc";
    this.focused = false;
    this.canvas = null;
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  dispatch(name, event = {}) {
    return this.listeners.get(name)?.(event);
  }

  getBoundingClientRect() {
    return { width: 1000, height: 600 };
  }

  querySelector(selector) {
    return selector === "canvas" ? this.canvas : null;
  }

  focus() {
    this.focused = true;
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map(ELEMENT_IDS.map((id) => [id, new FakeElement(id)]));
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

class FakeWindow {
  constructor() {
    this.location = { href: "https://netbox.example.test/virtualization/virtual-machines/1/" };
    this.listeners = new Map();
    this.timers = new Map();
    this.frames = new Map();
    this.nextId = 1;
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  dispatch(name) {
    this.listeners.get(name)?.();
  }

  setTimeout(callback, delay) {
    const id = this.nextId++;
    this.timers.set(id, { callback, delay });
    return id;
  }

  clearTimeout(id) {
    this.timers.delete(id);
  }

  requestAnimationFrame(callback) {
    const id = this.nextId++;
    this.frames.set(id, callback);
    return id;
  }

  cancelAnimationFrame(id) {
    this.frames.delete(id);
  }

  flushFrames() {
    const frames = [...this.frames.values()];
    this.frames.clear();
    frames.forEach((callback) => callback());
  }

  runShortestTimer() {
    const selected = [...this.timers.entries()].sort(
      ([leftId, left], [rightId, right]) => left.delay - right.delay || leftId - rightId,
    )[0];
    assert.ok(selected, "expected a pending timer");
    const [id, timer] = selected;
    this.timers.delete(id);
    timer.callback();
  }
}

class FakeRFB {
  static instances = [];

  constructor(container, url, options) {
    this.container = container;
    this.url = url;
    this.options = options;
    this.openedProtocols = [...options.wsProtocols];
    this.listeners = new Map();
    this.disconnectCount = 0;
    FakeRFB.instances.push(this);
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  removeEventListener(name, listener) {
    if (this.listeners.get(name) === listener) this.listeners.delete(name);
  }

  emit(name, detail = {}) {
    this.listeners.get(name)?.({ detail });
  }

  disconnect() {
    this.disconnectCount += 1;
  }
}

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  static instances = [];

  constructor(url, protocols) {
    this.url = url;
    this.protocols = protocols;
    this.openedProtocols = [...protocols];
    this.readyState = FakeWebSocket.CONNECTING;
    this.sent = [];
    this.closeCalls = [];
    FakeWebSocket.instances.push(this);
  }

  send(value) {
    this.sent.push(value);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  message(data) {
    this.onmessage?.({ data });
  }

  remoteClose(code) {
    const handler = this.onclose;
    this.readyState = FakeWebSocket.CLOSED;
    handler?.({ code });
  }

  close(code, reason) {
    this.closeCalls.push([code, reason]);
    this.readyState = FakeWebSocket.CLOSED;
  }
}

class FakeTerminal {
  static instances = [];

  constructor(options) {
    this.options = options;
    this.cols = options.cols;
    this.rows = options.rows;
    this.writes = [];
    this.resizeCalls = [];
    this.disposed = false;
    this.focused = false;
    this.inputDisposed = false;
    FakeTerminal.instances.push(this);
  }

  open(element) {
    this.element = element;
  }

  resize(cols, rows) {
    this.cols = cols;
    this.rows = rows;
    this.resizeCalls.push([cols, rows]);
  }

  write(value) {
    this.writes.push(value);
  }

  focus() {
    this.focused = true;
  }

  dispose() {
    this.disposed = true;
  }

  onData(listener) {
    this.inputListener = listener;
    return {
      dispose: () => {
        this.inputDisposed = true;
      },
    };
  }

  input(value) {
    this.inputListener(value);
  }
}

class FakeResizeObserver {
  static instances = [];

  constructor(callback) {
    this.callback = callback;
    this.disconnected = false;
    FakeResizeObserver.instances.push(this);
  }

  observe(element) {
    this.element = element;
  }

  disconnect() {
    this.disconnected = true;
  }

  trigger() {
    this.callback();
  }
}

function resetFakes() {
  FakeRFB.instances = [];
  FakeWebSocket.instances = [];
  FakeTerminal.instances = [];
  FakeResizeObserver.instances = [];
}

function session(consoleType, sequence = 1, expiryOffset = 60_000) {
  return {
    websocket_url: `wss://relay.example.test/console/${sequence}`,
    stream_token: STREAM_TOKEN,
    expires_at: new Date(1_000_000 + expiryOffset).toISOString(),
    console_type: consoleType,
  };
}

function assertTokenPrivacy(app, transportUrl) {
  assert.equal(transportUrl.includes(STREAM_TOKEN), false);
  assert.equal(transportUrl.includes("?"), false);
  assert.equal(app.controller.streamToken, null);
  for (const element of app.document.elements.values()) {
    assert.equal(element.textContent.includes(STREAM_TOKEN), false);
  }
}

function response(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function harness({
  vmType = "qemu",
  fetch,
  importRfb = async () => ({ default: FakeRFB }),
}) {
  resetFakes();
  const document = new FakeDocument();
  const window = new FakeWindow();
  const root = new FakeElement("proxbox-vm-console");
  root.dataset = {
    consoleReady: "true",
    vmType,
    sessionUrl: "/plugins/proxbox/virtual-machines/1/console/session/",
    csrfToken: "csrf-value",
    novncModuleUrl: "/static/netbox_proxbox/vendor/novnc/core/rfb.js",
  };
  const environment = {
    document,
    window,
    fetch,
    WebSocket: FakeWebSocket,
    Terminal: FakeTerminal,
    ResizeObserver: FakeResizeObserver,
    AbortController,
    importRfb,
    now: () => 1_000_000,
  };
  const controller = createConsoleController(root, environment);
  assert.ok(controller);
  return { controller, document, root, window };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, reject, resolve };
}

async function flushTasks() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function testNoVncSuccessAndManualReconnect() {
  const calls = [];
  let sequence = 0;
  const app = harness({
    fetch: async (url, options) => {
      calls.push([url, options]);
      sequence += 1;
      return response(session("novnc", sequence));
    },
  });
  const canvas = new FakeElement("canvas");
  app.document.getElementById("proxbox-console-novnc").canvas = canvas;

  await app.controller.connect();
  const first = FakeRFB.instances[0];
  assert.equal(first.url, "wss://relay.example.test/console/1");
  assert.deepEqual(first.openedProtocols, ["binary", `proxbox-token.${STREAM_TOKEN}`]);
  assert.deepEqual(first.options.wsProtocols, []);
  assertTokenPrivacy(app, first.url);
  assert.equal(first.scaleViewport, true);
  assert.equal(first.resizeSession, true);
  assert.equal(first.viewOnly, false);
  assert.equal(JSON.parse(calls[0][1].body).console_type, "novnc");
  assert.equal(calls[0][1].headers["X-CSRFToken"], "csrf-value");
  first.emit("connect");
  app.window.flushFrames();
  assert.equal(app.root.dataset.state, "connected");
  assert.equal(canvas.focused, true);

  await app.controller.connect(true);
  assert.equal(first.disconnectCount, 1);
  assert.equal(FakeRFB.instances.length, 2);
  assert.deepEqual(FakeRFB.instances[1].openedProtocols, [
    "binary",
    `proxbox-token.${STREAM_TOKEN}`,
  ]);
  assert.deepEqual(FakeRFB.instances[1].options.wsProtocols, []);
  assertTokenPrivacy(app, FakeRFB.instances[1].url);
  assert.equal(calls.length, 2);
}

async function testQemuTerminalProtocolAndCleanup() {
  const app = harness({ fetch: async () => response(session("term")) });
  app.document.getElementById("proxbox-console-type").value = "term";
  await app.controller.connect();
  app.window.flushFrames();

  const socket = FakeWebSocket.instances[0];
  const terminal = FakeTerminal.instances[0];
  const observer = FakeResizeObserver.instances[0];
  assert.deepEqual(socket.openedProtocols, ["binary", `proxbox-token.${STREAM_TOKEN}`]);
  assert.deepEqual(socket.protocols, []);
  assertTokenPrivacy(app, socket.url);
  socket.open();
  assert.match(socket.sent[0], /^1:\d+:\d+:0$/);
  terminal.input("raw-input");
  assert.equal(socket.sent.at(-1), "raw-input");
  socket.message("dhello");
  assert.equal(terminal.writes.at(-1), "hello");
  socket.message("\0");
  assert.equal(socket.sent.at(-1), "0");
  socket.message(new TextEncoder().encode("dbinary").buffer);
  assert.equal(new TextDecoder().decode(terminal.writes.at(-1)), "binary");

  observer.trigger();
  app.window.flushFrames();
  assert.match(socket.sent.at(-1), /^1:\d+:\d+:0$/);
  app.controller.disconnect();
  assert.deepEqual(socket.closeCalls[0], [1000, "Client disconnected"]);
  assert.equal(terminal.disposed, true);
  assert.equal(terminal.inputDisposed, true);
  assert.equal(observer.disconnected, true);
  assert.equal(app.root.dataset.state, "idle");
}

async function testLxcForcesTerminal() {
  let requestBody;
  const app = harness({
    vmType: "lxc",
    fetch: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return response(session("term"));
    },
  });
  app.document.getElementById("proxbox-console-type").value = "novnc";
  await app.controller.connect();
  assert.deepEqual(requestBody, { console_type: "term" });
  assert.equal(FakeRFB.instances.length, 0);
  assert.equal(FakeWebSocket.instances.length, 1);
}

async function testRetryExhaustion() {
  let calls = 0;
  const app = harness({
    fetch: async () => {
      calls += 1;
      if (calls === 1) throw new TypeError("offline");
      return response({ error: "temporarily unavailable" }, 503);
    },
  });
  await app.controller.connect();
  assert.equal(app.root.dataset.state, "retrying");
  app.window.runShortestTimer();
  await flushTasks();
  assert.equal(app.root.dataset.state, "retrying");
  app.window.runShortestTimer();
  await flushTasks();
  assert.equal(calls, 3);
  assert.equal(app.root.dataset.state, "error");
  assert.match(
    app.document.getElementById("proxbox-console-message").textContent,
    /Automatic retries are exhausted/,
  );
  assert.equal(app.window.timers.size, 0);
}

async function testRetryableTransportDisconnect() {
  let calls = 0;
  const app = harness({
    fetch: async () => {
      calls += 1;
      return response(session("term", calls));
    },
  });
  app.document.getElementById("proxbox-console-type").value = "term";
  await app.controller.connect();
  app.window.flushFrames();
  const firstSocket = FakeWebSocket.instances[0];
  const firstTerminal = FakeTerminal.instances[0];
  firstSocket.open();
  firstSocket.remoteClose(1006);
  assert.equal(app.root.dataset.state, "retrying");
  assert.equal(firstTerminal.disposed, true);

  app.window.runShortestTimer();
  await flushTasks();
  assert.equal(calls, 2);
  assert.equal(FakeWebSocket.instances.length, 2);
  app.controller.disconnect();
  assert.equal(app.window.timers.size, 0);
}

async function testExpiryBeforeConnect() {
  const app = harness({
    fetch: async () => response(session("novnc", 1, 500)),
  });
  await app.controller.connect();
  const rfb = FakeRFB.instances[0];
  app.window.runShortestTimer();
  assert.equal(rfb.disconnectCount, 1);
  assert.equal(app.root.dataset.state, "error");
  assert.match(
    app.document.getElementById("proxbox-console-message").textContent,
    /expired before the connection opened/,
  );
}

async function testStaleGenerationAndDisconnectDuringFetch() {
  const first = deferred();
  const second = deferred();
  const signals = [];
  let calls = 0;
  const app = harness({
    fetch: (_url, options) => {
      signals.push(options.signal);
      calls += 1;
      return calls === 1 ? first.promise : second.promise;
    },
  });

  const staleConnect = app.controller.connect();
  await flushTasks();
  const currentConnect = app.controller.connect();
  assert.equal(signals[0].aborted, true);
  const aborted = new Error("aborted");
  aborted.name = "AbortError";
  first.reject(aborted);
  await staleConnect;
  assert.equal(app.controller.requestAbort.signal, signals[1]);
  second.resolve(response(session("novnc", 2)));
  await currentConnect;
  assert.equal(FakeRFB.instances.length, 1);
  assert.equal(FakeRFB.instances[0].url, "wss://relay.example.test/console/2");

  const third = deferred();
  app.controller.disconnect();
  app.controller.env.fetch = (_url, options) => {
    signals.push(options.signal);
    return third.promise;
  };
  const interrupted = app.controller.connect();
  await flushTasks();
  app.controller.disconnect();
  assert.equal(signals.at(-1).aborted, true);
  third.resolve(response(session("novnc", 3)));
  await interrupted;
  assert.equal(app.root.dataset.state, "idle");
  assert.equal(FakeRFB.instances.length, 1);
}

async function testStaleRfbLoadCannotClearTheCurrentToken() {
  const firstImport = deferred();
  const secondImport = deferred();
  let imports = 0;
  let calls = 0;
  const app = harness({
    fetch: async () => {
      calls += 1;
      return response({ ...session("novnc", calls), stream_token: "a".repeat(43) });
    },
    importRfb: () => {
      imports += 1;
      return imports === 1 ? firstImport.promise : secondImport.promise;
    },
  });

  const staleConnect = app.controller.connect();
  await flushTasks();
  const currentConnect = app.controller.connect();
  await flushTasks();
  assert.equal(app.controller.streamToken.generation, 2);

  firstImport.resolve({ default: FakeRFB });
  await staleConnect;
  assert.equal(app.controller.streamToken.generation, 2);
  secondImport.resolve({ default: FakeRFB });
  await currentConnect;
  assert.equal(FakeRFB.instances.length, 1);
  assert.equal(app.controller.streamToken, null);
}

async function testSessionFailuresAndWssValidation() {
  const redirect = harness({
    fetch: async () => response({ detail: "moved" }, 302),
  });
  await redirect.controller.connect();
  assert.equal(redirect.root.dataset.state, "error");
  assert.match(
    redirect.document.getElementById("proxbox-console-message").textContent,
    /could not be created/,
  );

  const insecure = harness({
    fetch: async () =>
      response({
        ...session("novnc"),
        websocket_url: "ws://relay.example.test/console/1",
      }),
  });
  await insecure.controller.connect();
  assert.equal(insecure.root.dataset.state, "error");
  assert.equal(FakeRFB.instances.length, 0);
  assert.match(
    insecure.document.getElementById("proxbox-console-message").textContent,
    /unsafe WebSocket URL/,
  );

  const tokenInQuery = harness({
    fetch: async () =>
      response({
        ...session("novnc"),
        websocket_url: `wss://relay.example.test/console/1?token=${STREAM_TOKEN}`,
      }),
  });
  await tokenInQuery.controller.connect();
  assert.equal(tokenInQuery.root.dataset.state, "error");
  assert.equal(FakeRFB.instances.length, 0);
  assert.equal(
    tokenInQuery.document.getElementById("proxbox-console-message").textContent.includes(
      STREAM_TOKEN,
    ),
    false,
  );

  for (const streamToken of ["short", "unsafe.token!", "a".repeat(257)]) {
    const invalidToken = harness({
      fetch: async () => response({ ...session("novnc"), stream_token: streamToken }),
    });
    await invalidToken.controller.connect();
    assert.equal(invalidToken.root.dataset.state, "error");
    assert.equal(FakeRFB.instances.length, 0);
    assert.match(
      invalidToken.document.getElementById("proxbox-console-message").textContent,
      /invalid stream token/,
    );
  }

  const unexpected = harness({
    fetch: async () => response({ ...session("novnc"), ticket: "must-not-pass" }),
  });
  await unexpected.controller.connect();
  assert.equal(unexpected.root.dataset.state, "error");
  assert.equal(FakeRFB.instances.length, 0);
  assert.match(
    unexpected.document.getElementById("proxbox-console-message").textContent,
    /unexpected response/,
  );
}

async function testPageLifecycleCleanup() {
  const terminalApp = harness({ fetch: async () => response(session("term")) });
  terminalApp.document.getElementById("proxbox-console-type").value = "term";
  await terminalApp.controller.connect();
  terminalApp.window.flushFrames();
  FakeWebSocket.instances[0].open();
  terminalApp.window.dispatch("pagehide");
  assert.equal(FakeWebSocket.instances[0].closeCalls.length, 1);
  assert.equal(FakeTerminal.instances[0].disposed, true);
  assert.equal(FakeResizeObserver.instances[0].disconnected, true);

  const novncApp = harness({ fetch: async () => response(session("novnc")) });
  await novncApp.controller.connect();
  const rfb = FakeRFB.instances[0];
  novncApp.window.dispatch("unload");
  assert.equal(rfb.disconnectCount, 1);
}

function testPureProtocolHelpers() {
  assert.deepEqual(decodeTerminalFrame("dhello"), { kind: "data", payload: "hello" });
  assert.deepEqual(decodeTerminalFrame("0"), { kind: "keepalive" });
  assert.deepEqual(decodeTerminalFrame("\0"), { kind: "keepalive" });
  assert.deepEqual(decodeTerminalFrame("xignored"), { kind: "ignore" });
  assert.equal(classifyWebSocketClose(1006).retryable, true);
  assert.equal(classifyWebSocketClose(1008).retryable, false);
  assert.match(classifyWebSocketClose(1011).message, /server error/);
}

testPureProtocolHelpers();
await testNoVncSuccessAndManualReconnect();
await testQemuTerminalProtocolAndCleanup();
await testLxcForcesTerminal();
await testRetryExhaustion();
await testRetryableTransportDisconnect();
await testExpiryBeforeConnect();
await testStaleGenerationAndDisconnectDuringFetch();
await testStaleRfbLoadCannotClearTheCurrentToken();
await testSessionFailuresAndWssValidation();
await testPageLifecycleCleanup();
