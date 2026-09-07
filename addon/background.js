const NATIVE_HOST = "de.projekt_kanban.agent";
const PAGE_ORIGIN = "https://projekt-kanban.de/";
const PAGE_ACTIONS = new Set(["agent.list", "agent.ping", "run.start", "run.status", "run.list", "run.cancel"]);
const ADMIN_ACTIONS = new Set(["hello", "config.get", "config.set", "agent.list", "agent.ping", "run.list", "run.status", "run.cancel"]);
const pending = new Map();
const eventPorts = new Set();
const pagePortsByTab = new Map();
let nativePort = null;

function setPageIcon(tabId, active) {
  if (!Number.isInteger(tabId)) {
    return;
  }
  const icon = active ? "icons/agent.svg" : "icons/agent-inactive.svg";
  const title = active
    ? "Projekt Kanban Agent Connector – Kanban-Seite erkannt"
    : "Projekt Kanban Agent Connector – keine Kanban-Seite erkannt";
  Promise.all([
    browser.action.setIcon({ tabId, path: icon }),
    browser.action.setTitle({ tabId, title })
  ]).catch(() => {});
}

function newRequestId() {
  return crypto.randomUUID();
}

function normalizeError(error, fallbackCode = "NATIVE_HOST_ERROR") {
  return {
    code: error && error.code ? String(error.code) : fallbackCode,
    message: error && error.message ? String(error.message) : String(error)
  };
}

function disconnectNative(error) {
  const normalized = normalizeError(error || new Error("Native host disconnected."));
  nativePort = null;
  for (const entry of pending.values()) {
    clearTimeout(entry.timer);
    entry.resolve({ ok: false, error: normalized });
  }
  pending.clear();
}

function broadcastEvent(message) {
  for (const port of eventPorts) {
    try {
      port.postMessage({
        type: "PK_AGENT_EVENT",
        runId: message.runId,
        event: message.event,
        data: message.data || {}
      });
    } catch (_error) {
      eventPorts.delete(port);
    }
  }
}

function connectNative() {
  if (nativePort) {
    return nativePort;
  }

  nativePort = browser.runtime.connectNative(NATIVE_HOST);
  nativePort.onMessage.addListener((message) => {
    if (!message || typeof message !== "object") {
      return;
    }
    if (message.kind === "event") {
      broadcastEvent(message);
      return;
    }
    if (message.kind === "response" && typeof message.requestId === "string") {
      const entry = pending.get(message.requestId);
      if (!entry) {
        return;
      }
      pending.delete(message.requestId);
      clearTimeout(entry.timer);
      entry.resolve(message.ok
        ? { ok: true, data: message.data || {} }
        : { ok: false, error: message.error || { code: "NATIVE_HOST_ERROR", message: "Unknown native host error." } });
    }
  });
  nativePort.onDisconnect.addListener(() => {
    const detail = browser.runtime.lastError && browser.runtime.lastError.message
      ? browser.runtime.lastError.message
      : "Native host disconnected.";
    const diagnostic = /disconnected/i.test(detail)
      ? `${detail} Windows-WSL-Protokoll: %LOCALAPPDATA%\\ProjektKanbanAgent\\relay.log`
      : detail;
    disconnectNative(new Error(diagnostic));
  });
  return nativePort;
}

function requestNative(action, payload = {}, timeoutMs = 20000) {
  return new Promise((resolve) => {
    const requestId = newRequestId();
    const timer = setTimeout(() => {
      pending.delete(requestId);
      resolve({ ok: false, error: { code: "NATIVE_HOST_TIMEOUT", message: "Der lokale Agenten-Connector antwortet nicht." } });
    }, timeoutMs);

    pending.set(requestId, { resolve, timer });
    try {
      connectNative().postMessage({ kind: "request", requestId, action, payload });
    } catch (error) {
      pending.delete(requestId);
      clearTimeout(timer);
      resolve({ ok: false, error: normalizeError(error) });
    }
  });
}

function isPageSender(sender) {
  return Boolean(sender && sender.tab && typeof sender.url === "string" && sender.url.startsWith(PAGE_ORIGIN));
}

function isExtensionSender(sender) {
  const extensionOrigin = browser.runtime.getURL("");
  return Boolean(sender && typeof sender.url === "string" && sender.url.startsWith(extensionOrigin));
}

browser.runtime.onMessage.addListener((message, sender) => {
  if (!message || typeof message !== "object") {
    return undefined;
  }
  if (message.type === "PK_PAGE_REQUEST") {
    if (!isPageSender(sender) || !PAGE_ACTIONS.has(message.action)) {
      return Promise.resolve({ ok: false, error: { code: "FORBIDDEN", message: "Request source or action is not allowed." } });
    }
    return requestNative(message.action, message.payload || {});
  }
  if (message.type === "PK_ADMIN_REQUEST") {
    if (!isExtensionSender(sender) || !ADMIN_ACTIONS.has(message.action)) {
      return Promise.resolve({ ok: false, error: { code: "FORBIDDEN", message: "Administrative action is not allowed." } });
    }
    return requestNative(message.action, message.payload || {});
  }
  return undefined;
});

browser.runtime.onConnect.addListener((port) => {
  if (port.name !== "projekt-kanban-events" || !isPageSender(port.sender)) {
    port.disconnect();
    return;
  }
  eventPorts.add(port);
  const tabId = port.sender.tab.id;
  const tabPorts = pagePortsByTab.get(tabId) || new Set();
  tabPorts.add(port);
  pagePortsByTab.set(tabId, tabPorts);
  setPageIcon(tabId, true);
  port.onDisconnect.addListener(() => {
    eventPorts.delete(port);
    const currentPorts = pagePortsByTab.get(tabId);
    if (!currentPorts) {
      return;
    }
    currentPorts.delete(port);
    if (!currentPorts.size) {
      pagePortsByTab.delete(tabId);
      setPageIcon(tabId, false);
    }
  });
});
