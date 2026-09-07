(function () {
  "use strict";

  if (window.top !== window || window.location.origin !== "https://projekt-kanban.de") {
    return;
  }

  const PAGE_SOURCE = "projekt-kanban";
  const ADDON_SOURCE = "projekt-kanban-agent-addon";
  const PROTOCOL_VERSION = 1;
  const MAX_REQUEST_BYTES = 512 * 1024;
  const ALLOWED_ACTIONS = new Set([
    "agent.list",
    "agent.ping",
    "run.start",
    "run.status",
    "run.list",
    "run.cancel"
  ]);

  function sendToPage(message) {
    window.postMessage({
      source: ADDON_SOURCE,
      version: PROTOCOL_VERSION,
      ...message
    }, window.location.origin);
  }

  function errorPayload(error) {
    return {
      code: error && error.code ? String(error.code) : "ADDON_ERROR",
      message: error && error.message ? String(error.message) : String(error)
    };
  }

  function validatePageRequest(data) {
    if (!data || data.source !== PAGE_SOURCE || data.version !== PROTOCOL_VERSION || data.type !== "request") {
      return false;
    }
    if (typeof data.requestId !== "string" || data.requestId.length < 1 || data.requestId.length > 128) {
      throw new Error("Invalid requestId.");
    }
    if (!ALLOWED_ACTIONS.has(data.action)) {
      throw new Error("Unsupported agent action.");
    }
    if (new TextEncoder().encode(JSON.stringify(data)).length > MAX_REQUEST_BYTES) {
      throw new Error("The agent request is too large.");
    }
    return true;
  }

  function confirmTaskTransmission(payload) {
    return new Promise((resolve) => {
      const existing = document.getElementById("projekt-kanban-agent-confirmation");
      if (existing) {
        existing.remove();
      }

      const host = document.createElement("div");
      host.id = "projekt-kanban-agent-confirmation";
      const shadow = host.attachShadow({ mode: "closed" });
      const style = document.createElement("style");
      style.textContent = `
        .backdrop { position: fixed; inset: 0; z-index: 2147483647; display: grid; place-items: center; padding: 18px; background: rgba(15, 23, 42, .55); font: 15px/1.45 system-ui, sans-serif; color: #1f2937; }
        .dialog { width: min(520px, 100%); border: 1px solid #b8c5d6; border-radius: 12px; background: #fff; box-shadow: 0 20px 60px rgba(0, 0, 0, .35); }
        header { padding: 18px 20px 10px; font-size: 20px; font-weight: 700; }
        main { padding: 0 20px 18px; }
        .task { margin: 12px 0; padding: 10px 12px; border-radius: 8px; background: #f1f5f9; font-weight: 600; overflow-wrap: anywhere; }
        .notice { font-size: 13px; color: #475569; }
        footer { display: flex; justify-content: flex-end; gap: 9px; padding: 13px 20px; border-top: 1px solid #e2e8f0; }
        button { min-height: 36px; padding: 7px 14px; border: 1px solid #94a3b8; border-radius: 7px; background: #fff; color: #1f2937; cursor: pointer; font: inherit; }
        button.primary { border-color: #145da0; background: #145da0; color: #fff; }
        button:focus-visible { outline: 3px solid rgba(20, 93, 160, .3); outline-offset: 2px; }
      `;

      const backdrop = document.createElement("div");
      backdrop.className = "backdrop";
      backdrop.setAttribute("role", "dialog");
      backdrop.setAttribute("aria-modal", "true");
      backdrop.setAttribute("aria-labelledby", "pk-agent-confirm-title");

      const dialog = document.createElement("div");
      dialog.className = "dialog";
      const header = document.createElement("header");
      header.id = "pk-agent-confirm-title";
      header.textContent = "Task an eigenen Agenten senden?";
      const main = document.createElement("main");
      const explanation = document.createElement("p");
      explanation.textContent = "Projekt Kanban möchte die ausgewählte Task an den von Ihnen konfigurierten Agenten übertragen.";
      const task = document.createElement("div");
      task.className = "task";
      task.textContent = payload && payload.task && payload.task.title ? payload.task.title : "Unbenannte Task";
      const notice = document.createElement("p");
      notice.className = "notice";
      notice.textContent = "Übertragen werden Task-Titel, Beschreibung, optional Notes und Subtasks. Zugangsdaten werden nicht an die Webseite übermittelt.";
      main.append(explanation, task, notice);

      const footer = document.createElement("footer");
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Abbrechen";
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "primary";
      approve.textContent = "An Agenten senden";
      footer.append(cancel, approve);
      dialog.append(header, main, footer);
      backdrop.append(dialog);
      shadow.append(style, backdrop);
      document.documentElement.append(host);

      const finish = (approved) => {
        host.remove();
        resolve(approved);
      };
      cancel.addEventListener("click", () => finish(false), { once: true });
      approve.addEventListener("click", () => finish(true), { once: true });
      backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) {
          finish(false);
        }
      });
      backdrop.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          finish(false);
        }
      });
      approve.focus();
    });
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window || event.origin !== window.location.origin) {
      return;
    }

    let valid;
    try {
      valid = validatePageRequest(event.data);
    } catch (error) {
      if (event.data && event.data.requestId) {
        sendToPage({ type: "response", requestId: event.data.requestId, ok: false, error: errorPayload(error) });
      }
      return;
    }
    if (!valid) {
      return;
    }

    const request = event.data;
    if (request.action === "run.start" && !(await confirmTaskTransmission(request.payload))) {
      sendToPage({
        type: "response",
        requestId: request.requestId,
        ok: false,
        error: { code: "USER_CANCELLED", message: "Die Übertragung wurde abgebrochen." }
      });
      return;
    }

    try {
      const response = await browser.runtime.sendMessage({
        type: "PK_PAGE_REQUEST",
        requestId: request.requestId,
        action: request.action,
        payload: request.payload || {}
      });
      sendToPage({ type: "response", requestId: request.requestId, ...response });
    } catch (error) {
      sendToPage({ type: "response", requestId: request.requestId, ok: false, error: errorPayload(error) });
    }
  });

  const eventPort = browser.runtime.connect({ name: "projekt-kanban-events" });
  eventPort.onMessage.addListener((message) => {
    if (message && message.type === "PK_AGENT_EVENT") {
      sendToPage({ type: "event", runId: message.runId, event: message.event, data: message.data || {} });
    }
  });

  sendToPage({
    type: "ready",
    capabilities: ["agent.list", "agent.ping", "run.start", "run.status", "run.list", "run.cancel"]
  });
}());
