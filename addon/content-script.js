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
    "agent.test",
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

  function agentForPage(agent) {
    return {
      id: agent.id,
      label: agent.label,
      adapter: agent.adapter,
      transport: agent.transport,
      sandbox: agent.sandbox
    };
  }

  function responseForPage(action, response) {
    if (!response || !response.ok) {
      return response;
    }
    if (action === "agent.list") {
      return {
        ...response,
        data: { agents: (response.data.agents || []).map(agentForPage) }
      };
    }
    if ((action === "agent.ping" || action === "agent.test") && response.data && response.data.agent) {
      return {
        ...response,
        data: { ...response.data, agent: agentForPage(response.data.agent) }
      };
    }
    return response;
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

  function confirmTaskTransmission(payload, agent) {
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
        .agent { margin: 10px 0; font-size: 13px; color: #334155; overflow-wrap: anywhere; }
        .danger-notice { margin: 12px 0; padding: 10px 12px; border: 2px solid #dc2626; border-radius: 8px; background: #fff1f2; color: #991b1b; font-size: 13px; font-weight: 650; }
        .danger-confirm { display: flex; align-items: flex-start; gap: 8px; margin-top: 12px; font-size: 13px; font-weight: 600; color: #7f1d1d; }
        .danger-confirm input { margin-top: 3px; }
        footer { display: flex; justify-content: flex-end; gap: 9px; padding: 13px 20px; border-top: 1px solid #e2e8f0; }
        button { min-height: 36px; padding: 7px 14px; border: 1px solid #94a3b8; border-radius: 7px; background: #fff; color: #1f2937; cursor: pointer; font: inherit; }
        button.primary { border-color: #145da0; background: #145da0; color: #fff; }
        button:disabled { cursor: not-allowed; opacity: .55; }
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
      const agentDetails = document.createElement("p");
      agentDetails.className = "agent";
      agentDetails.textContent = agent.sandbox === "danger-full-access"
        ? `Agent: ${agent.label} · Startverzeichnis: ${agent.startDirectory}`
        : `Agent: ${agent.label} · Arbeitsbereich: ${agent.workspace}`;
      const notice = document.createElement("p");
      notice.className = "notice";
      notice.textContent = "Übertragen werden Task-Titel, Beschreibung, optional Notes und Subtasks. Zugangsdaten werden nicht an die Webseite übermittelt.";
      main.append(explanation, task, agentDetails, notice);

      const unrestricted = agent.sandbox === "danger-full-access";
      let dangerCheckbox = null;
      if (unrestricted) {
        const dangerNotice = document.createElement("p");
        dangerNotice.className = "danger-notice";
        dangerNotice.textContent = "Uneingeschränkter Zugriff: Der Agent kann auch außerhalb seines Startverzeichnisses Dateien lesen und verändern sowie dort erreichbare Zugangsdaten verwenden.";
        const dangerConfirm = document.createElement("label");
        dangerConfirm.className = "danger-confirm";
        dangerCheckbox = document.createElement("input");
        dangerCheckbox.type = "checkbox";
        const dangerText = document.createElement("span");
        dangerText.textContent = "Ich erlaube diesem Agenten für diesen Lauf uneingeschränkten Zugriff.";
        dangerConfirm.append(dangerCheckbox, dangerText);
        main.append(dangerNotice, dangerConfirm);
      }

      const footer = document.createElement("footer");
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Abbrechen";
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "primary";
      approve.textContent = unrestricted ? "Uneingeschränkt starten" : "An Agenten senden";
      approve.disabled = unrestricted;
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
      if (dangerCheckbox) {
        dangerCheckbox.addEventListener("change", () => {
          approve.disabled = !dangerCheckbox.checked;
        });
      }
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
      (dangerCheckbox || approve).focus();
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
    try {
      if (request.action === "run.start") {
        const listResponse = await browser.runtime.sendMessage({
          type: "PK_PAGE_REQUEST",
          action: "agent.list",
          payload: {}
        });
        if (!listResponse || !listResponse.ok) {
          sendToPage({ type: "response", requestId: request.requestId, ...(listResponse || {
            ok: false,
            error: { code: "CONNECTOR_ERROR", message: "Agentenkonfiguration konnte nicht geladen werden." }
          }) });
          return;
        }
        const agent = (listResponse.data.agents || []).find((item) => item.id === request.payload.agentId);
        if (!agent) {
          sendToPage({
            type: "response",
            requestId: request.requestId,
            ok: false,
            error: { code: "AGENT_NOT_FOUND", message: "Der ausgewählte Agent ist nicht aktiv oder nicht vorhanden." }
          });
          return;
        }
        if (!(await confirmTaskTransmission(request.payload, agent))) {
          sendToPage({
            type: "response",
            requestId: request.requestId,
            ok: false,
            error: { code: "USER_CANCELLED", message: "Die Übertragung wurde abgebrochen." }
          });
          return;
        }
      }
      const response = await browser.runtime.sendMessage({
        type: "PK_PAGE_REQUEST",
        requestId: request.requestId,
        action: request.action,
        payload: request.payload || {}
      });
      sendToPage({ type: "response", requestId: request.requestId, ...responseForPage(request.action, response) });
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
    capabilities: ["agent.list", "agent.ping", "agent.test", "run.start", "run.status", "run.list", "run.cancel"]
  });
}());
