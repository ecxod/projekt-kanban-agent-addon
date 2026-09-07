(function () {
  "use strict";

  const agentsContainer = document.getElementById("agents");
  const template = document.getElementById("agentTemplate");
  const bridgeStatus = document.getElementById("bridgeStatus");
  const saveStatus = document.getElementById("saveStatus");

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

  function projectsToText(projects) {
    return Object.entries(projects || {}).map(([id, path]) => `${id}=${path}`).join("\n");
  }

  function textToProjects(value) {
    const projects = {};
    for (const originalLine of value.split(/\r?\n/)) {
      const line = originalLine.trim();
      if (!line || line.startsWith("#")) {
        continue;
      }
      const separator = line.indexOf("=");
      if (separator < 1 || separator === line.length - 1) {
        throw new Error(`Ungültige Projektzuordnung: ${line}`);
      }
      const id = line.slice(0, separator).trim();
      const path = line.slice(separator + 1).trim();
      if (!/^[A-Za-z0-9._-]{1,100}$/.test(id)) {
        throw new Error(`Ungültige Projektkennung: ${id}`);
      }
      projects[id] = path;
    }
    if (!Object.keys(projects).length) {
      throw new Error("Mindestens ein Projekt muss freigegeben werden.");
    }
    return projects;
  }

  function updateTransport(card) {
    const transport = card.querySelector('[name="transport"]').value;
    card.querySelector(".ssh-field").hidden = transport !== "ssh";
    card.querySelector('[name="sshHost"]').required = transport === "ssh";
  }

  function updateAdapter(card) {
    const adapter = card.querySelector('[name="adapter"]').value;
    card.querySelector(".arguments-field").hidden = adapter !== "jsonl-bridge";
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
      projects: projectsToText(agent.projects)
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
    card.querySelector(".remove-agent").addEventListener("click", () => card.remove());
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
        label: card.querySelector('[name="label"]').value.trim(),
        transport: card.querySelector('[name="transport"]').value,
        adapter: card.querySelector('[name="adapter"]').value,
        executable: card.querySelector('[name="executable"]').value.trim(),
        arguments: card.querySelector('[name="arguments"]').value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        sshHost: card.querySelector('[name="sshHost"]').value.trim(),
        sandbox: card.querySelector('[name="sandbox"]').value,
        projects: textToProjects(card.querySelector('[name="projects"]').value)
      });
    }
    return agents;
  }

  async function saveAgents() {
    const agents = collectAgents();
    const result = await nativeRequest("config.set", { version: 1, agents });
    setStatus(saveStatus, `${result.agentCount} Agent(en) gespeichert.`, "success");
    return result;
  }

  async function load() {
    setStatus(bridgeStatus, "Verbindung wird geprüft …");
    setStatus(saveStatus, "");
    agentsContainer.replaceChildren();
    try {
      const hello = await nativeRequest("hello");
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
