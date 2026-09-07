(function () {
  "use strict";

  const agentsContainer = document.getElementById("agents");
  const template = document.getElementById("agentTemplate");
  const bridgeStatus = document.getElementById("bridgeStatus");
  const saveStatus = document.getElementById("saveStatus");
  const expectedHostVersion = browser.runtime.getManifest().version;
  let hostCompatible = false;

  function setStatus(element, message, type = "") {
    element.textContent = message;
    element.className = `status${type ? ` ${type}` : ""}`;
  }

  async function nativeRequest(action, payload = {}) {
    const response = await browser.runtime.sendMessage({ type: "PK_ADMIN_REQUEST", action, payload });
    if (!response || !response.ok) {
      const error = new Error(response && response.error ? response.error.message : "Unbekannter Connector-Fehler.");
      error.code = response && response.error ? response.error.code : "CONNECTOR_ERROR";
      throw error;
    }
    return response.data || {};
  }

  function updateTransport(card) {
    const transport = card.querySelector('[name="transport"]').value;
    card.querySelector(".ssh-field").hidden = transport !== "ssh";
    card.querySelector('[name="sshHost"]').required = transport === "ssh";
    card.querySelector('[name="workspace"]').placeholder = transport === "ssh"
      ? "/home/user/workspace"
      : "/mnt/c/Users/Christian/workspace";
  }

  function updateAdapter(card) {
    const adapter = card.querySelector('[name="adapter"]').value;
    card.querySelector(".arguments-field").hidden = adapter !== "jsonl-bridge";
  }

  function updateSandbox(card) {
    const sandbox = card.querySelector('[name="sandbox"]').value;
    const unrestricted = sandbox === "danger-full-access";
    const workspaceField = card.querySelector(".workspace-field");
    const workspaceInput = card.querySelector('[name="workspace"]');
    workspaceField.hidden = unrestricted;
    workspaceInput.required = !unrestricted;
    card.querySelector(".sandbox-warning").hidden = !unrestricted;
    card.querySelector(".sandbox-help").textContent = sandbox === "read-only"
      ? "Analysemodus: Der Agent kann das Projekt untersuchen und einen Plan liefern, aber keine Dateien verändern."
      : (unrestricted
        ? "Startverzeichnis ist automatisch das Home-Verzeichnis des Agentenbenutzers."
        : "Der Agent darf innerhalb des gewählten Arbeitsbereichs lesen und schreiben.");
  }

  function updateEnabled(card, enabled) {
    card.dataset.enabled = enabled ? "true" : "false";
    card.classList.toggle("is-disabled", !enabled);
    card.querySelector(".agent-state-badge").textContent = enabled ? "Aktiv" : "Deaktiviert";
    card.querySelector(".toggle-agent").textContent = enabled ? "Deaktivieren" : "Aktivieren";
    card.querySelector(".test-agent").disabled = !enabled;
  }

  function addAgent(agent = {}) {
    const card = template.content.firstElementChild.cloneNode(true);
    const values = {
      id: agent.id || "",
      label: agent.label || "",
      transport: agent.transport || "local",
      adapter: agent.adapter || "codex-exec",
      executable: agent.executable || "codex",
      arguments: (agent.arguments || []).join("\n"),
      sshHost: agent.sshHost || "",
      sandbox: agent.sandbox || "read-only",
      workspace: agent.workspace || ""
    };
    for (const [name, value] of Object.entries(values)) {
      card.querySelector(`[name="${name}"]`).value = value;
    }
    card.querySelector("h3").textContent = agent.label || "Neuer Agent";
    card.querySelector('[name="label"]').addEventListener("input", (event) => {
      card.querySelector("h3").textContent = event.target.value || "Neuer Agent";
    });
    card.querySelector('[name="transport"]').addEventListener("change", () => updateTransport(card));
    card.querySelector('[name="adapter"]').addEventListener("change", () => updateAdapter(card));
    card.querySelector('[name="sandbox"]').addEventListener("change", () => updateSandbox(card));
    card.querySelector(".remove-agent").addEventListener("click", () => card.remove());
    card.querySelector(".toggle-agent").addEventListener("click", async () => {
      const status = card.querySelector(".agent-status");
      const wasEnabled = card.dataset.enabled === "true";
      updateEnabled(card, !wasEnabled);
      try {
        await saveAgents();
        setStatus(status, wasEnabled ? "Agent wurde deaktiviert." : "Agent wurde aktiviert.", "success");
      } catch (error) {
        updateEnabled(card, wasEnabled);
        setStatus(status, error.message, "error");
      }
    });
    card.querySelector(".test-agent").addEventListener("click", async () => {
      const status = card.querySelector(".agent-status");
      try {
        await saveAgents();
        setStatus(status, "Verbindung wird geprüft …");
        const result = await nativeRequest("agent.ping", { agentId: card.querySelector('[name="id"]').value.trim() });
        setStatus(status, result.message || "Agent ist erreichbar.", "success");
      } catch (error) {
        setStatus(status, error.message, "error");
      }
    });
    updateTransport(card);
    updateAdapter(card);
    updateSandbox(card);
    updateEnabled(card, agent.enabled !== false);
    agentsContainer.append(card);
  }

  function collectAgents() {
    const agents = [];
    const ids = new Set();
    for (const card of agentsContainer.querySelectorAll(".agent-card")) {
      for (const control of card.querySelectorAll("input, select, textarea")) {
        if (!control.reportValidity()) {
          throw new Error("Bitte alle markierten Felder korrigieren.");
        }
      }
      const id = card.querySelector('[name="id"]').value.trim();
      if (ids.has(id)) {
        throw new Error(`Die Agent-ID „${id}“ ist mehrfach vorhanden.`);
      }
      ids.add(id);
      agents.push({
        id,
        enabled: card.dataset.enabled !== "false",
        label: card.querySelector('[name="label"]').value.trim(),
        transport: card.querySelector('[name="transport"]').value,
        adapter: card.querySelector('[name="adapter"]').value,
        executable: card.querySelector('[name="executable"]').value.trim(),
        arguments: card.querySelector('[name="arguments"]').value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        sshHost: card.querySelector('[name="sshHost"]').value.trim(),
        sandbox: card.querySelector('[name="sandbox"]').value,
        workspace: card.querySelector('[name="sandbox"]').value === "danger-full-access"
          ? ""
          : card.querySelector('[name="workspace"]').value.trim()
      });
    }
    return agents;
  }

  async function saveAgents() {
    if (!hostCompatible) {
      throw new Error(`Bitte zuerst Native Host ${expectedHostVersion} installieren und danach „Neu laden“ wählen.`);
    }
    const agents = collectAgents();
    const result = await nativeRequest("config.set", { version: 1, agents });
    for (const status of agentsContainer.querySelectorAll(".agent-status")) {
      setStatus(status, "");
    }
    setStatus(saveStatus, `${result.agentCount} Agent(en) gespeichert, ${result.enabledAgentCount} aktiv.`, "success");
    return result;
  }

  async function load() {
    hostCompatible = false;
    document.getElementById("save").disabled = true;
    document.getElementById("addAgent").disabled = true;
    setStatus(bridgeStatus, "Verbindung wird geprüft …");
    setStatus(saveStatus, "");
    agentsContainer.replaceChildren();
    try {
      const hello = await nativeRequest("hello");
      if (hello.version !== expectedHostVersion) {
        throw new Error(`Native Host ${hello.version || "unbekannt"} ist nicht kompatibel. Benötigt wird Version ${expectedHostVersion}. Bitte die Bridge aus dem aktuellen Release installieren.`);
      }
      hostCompatible = true;
      document.getElementById("save").disabled = false;
      document.getElementById("addAgent").disabled = false;
      setStatus(bridgeStatus, `Verbunden mit Native Host ${hello.version}.`, "success");
      const config = await nativeRequest("config.get");
      for (const agent of config.agents || []) {
        addAgent(agent);
      }
      if (!config.agents || !config.agents.length) {
        addAgent();
      }
    } catch (error) {
      setStatus(bridgeStatus, `${error.message} Bitte zuerst die lokale Bridge installieren.`, "error");
      addAgent();
    }
  }

  document.getElementById("addAgent").addEventListener("click", () => addAgent());
  document.getElementById("save").addEventListener("click", async () => {
    try {
      setStatus(saveStatus, "Speichern …");
      await saveAgents();
    } catch (error) {
      setStatus(saveStatus, error.message, "error");
    }
  });
  document.getElementById("reload").addEventListener("click", load);
  load();
}());
