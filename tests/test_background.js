"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

let connectListener;
const iconCalls = [];
const titleCalls = [];

global.browser = {
  action: {
    setIcon: async (details) => iconCalls.push(details),
    setTitle: async (details) => titleCalls.push(details)
  },
  runtime: {
    getURL: () => "moz-extension://projekt-kanban-agent/",
    onMessage: { addListener: () => {} },
    onConnect: { addListener: (listener) => { connectListener = listener; } },
    connectNative: () => { throw new Error("not used by this test"); },
    lastError: null
  }
};

require(path.join(__dirname, "..", "addon", "background.js"));

function newPort(url, tabId = 17) {
  let disconnectListener;
  return {
    name: "projekt-kanban-events",
    sender: { url, tab: { id: tabId } },
    disconnected: false,
    onMessage: { addListener: () => {} },
    onDisconnect: { addListener: (listener) => { disconnectListener = listener; } },
    postMessage: () => {},
    disconnect() { this.disconnected = true; },
    triggerDisconnect() { disconnectListener(); }
  };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  assert.equal(typeof connectListener, "function");

  const valid = newPort("https://projekt-kanban.de/project/demo");
  connectListener(valid);
  await settle();
  assert.equal(valid.disconnected, false);
  assert.deepEqual(iconCalls.at(-1), { tabId: 17, path: "icons/agent.svg" });
  assert.match(titleCalls.at(-1).title, /Kanban-Seite erkannt$/);

  valid.triggerDisconnect();
  await settle();
  assert.deepEqual(iconCalls.at(-1), { tabId: 17, path: "icons/agent-inactive.svg" });
  assert.match(titleCalls.at(-1).title, /keine Kanban-Seite erkannt$/);

  const invalid = newPort("https://example.org/");
  const callCount = iconCalls.length;
  connectListener(invalid);
  await settle();
  assert.equal(invalid.disconnected, true);
  assert.equal(iconCalls.length, callCount);

  process.stdout.write("Background origin restriction and icon state tests passed.\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
