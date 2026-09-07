(function () {
  "use strict";

  const bridgeStatus = document.getElementById("bridgeStatus");
  const agents = document.getElementById("agents");

  async function request(action, payload = {}) {
    const response = await browser.runtime.sendMessage({ type: "PK_ADMIN_REQUEST", action, payload });
    if (!response || !response.ok) {
      throw new Error(response && response.error ? response.error.message : "Native Host antwortet nicht.");
    }
    return response.data || {};
  }

  async function load() {
    try {
      const hello = await request("hello");
      bridgeStatus.textContent = `Native Host ${hello.version} verbunden`;
      bridgeStatus.className = "success";
      const result = await request("agent.list");
      agents.replaceChildren();
      if (!result.agents || !result.agents.length) {
        const item = document.createElement("li");
        item.textContent = "Noch keine Agenten konfiguriert.";
        agents.append(item);
        return;
      }
      for (const agent of result.agents) {
        const item = document.createElement("li");
        const name = document.createElement("strong");
        name.textContent = agent.label;
        const meta = document.createElement("span");
        meta.className = "agent-meta";
        meta.textContent = `${agent.adapter} · ${agent.transport} · ${agent.projects.join(", ")}`;
        item.append(name, meta);
        agents.append(item);
      }
    } catch (error) {
      bridgeStatus.textContent = error.message;
      bridgeStatus.className = "error";
      agents.replaceChildren();
      const item = document.createElement("li");
      item.textContent = "Installieren Sie zuerst die lokale Native-Messaging-Bridge.";
      agents.append(item);
    }
  }

  document.getElementById("openOptions").addEventListener("click", () => browser.runtime.openOptionsPage());
  load();
}());
