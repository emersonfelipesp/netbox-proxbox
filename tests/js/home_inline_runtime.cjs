const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

async function main() {
const scriptPath = process.argv[2];
assert.ok(scriptPath, "home_inline.js path is required");

class FakeElement {
  constructor(id, url) {
    this.id = id;
    this.dataset = url ? { proxmoxCardId: id, proxmoxCardUrl: url } : {};
    this.className = "";
    this.textContent = "";
  }

  querySelector() {
    return new FakeElement("field");
  }

  replaceChildren() {}
  removeAttribute() {}
  setAttribute() {}
  addEventListener() {}
}

const cards = Array.from({ length: 8 }, (_, index) =>
  new FakeElement(String(index + 1), `/card/${index + 1}`),
);
const listeners = new Map();
const timers = [];
const attempts = new Map();
let activeRequests = 0;
let maximumActiveRequests = 0;

const document = {
  addEventListener(name, listener) {
    listeners.set(name, listener);
  },
  createElement() {
    return new FakeElement("created");
  },
  getElementById() {
    return new FakeElement("lookup");
  },
  querySelectorAll(selector) {
    return selector === "[data-proxmox-card-url]" ? cards : [];
  },
};

const window = {
  setTimeout(callback) {
    timers.push(callback);
    return timers.length;
  },
};

async function fetch(url) {
  activeRequests += 1;
  maximumActiveRequests = Math.max(maximumActiveRequests, activeRequests);
  const attempt = (attempts.get(url) || 0) + 1;
  attempts.set(url, attempt);
  await new Promise((resolve) => setImmediate(resolve));
  activeRequests -= 1;
  const throttled = attempt <= 3;
  return {
    ok: !throttled,
    status: throttled ? 429 : 200,
    headers: { get: () => (throttled ? "0" : null) },
    json: async () => throttled
      ? { detail: "busy" }
      : { cluster_data: { mode: "cluster", version: "8", repoid: "pve" } },
  };
}

vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), {
  Array,
  Date,
  Error,
  HTMLInputElement: FakeElement,
  Map,
  Math,
  Number,
  Promise,
  Set,
  String,
  WeakMap,
  document,
  fetch,
  window,
});

await listeners.get("DOMContentLoaded")();
for (let round = 0; round < 3; round += 1) {
  assert.equal(timers.length, cards.length, "each card has at most one pending retry");
  const pending = timers.splice(0);
  pending.forEach((callback) => callback());
  while (activeRequests > 0 || timers.length === 0) {
    await new Promise((resolve) => setImmediate(resolve));
    if (activeRequests === 0 && (timers.length > 0 || round === 2)) break;
  }
}

assert.equal(maximumActiveRequests, 4, "initial and retry requests share the four-worker pool");
for (const card of cards) {
  assert.equal(attempts.get(card.dataset.proxmoxCardUrl), 4, "retry count is capped at three");
}
assert.equal(timers.length, 0, "successful final attempts leave no retry timers");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
