(function () {
  "use strict";

  const agentsContainer = document.getElementById("agents");
  const template = document.getElementById("agentTemplate");
  const releaseStatus = document.getElementById("releaseStatus");
  const bridgeStatus = document.getElementById("bridgeStatus");
  const saveStatus = document.getElementById("saveStatus");
  const installedVersion = document.getElementById("installedVersion");
  const installedStatus = document.getElementById("installedStatus");
  const githubVersion = document.getElementById("githubVersion");
  const githubPublished = document.getElementById("githubPublished");
  const githubStatus = document.getElementById("githubStatus");
  const refreshReleasesButton = document.getElementById("refreshReleases");
  const updateReleaseButton = document.getElementById("updateRelease");
  const reloadButton = document.getElementById("reload");
  const expectedHostVersion = browser.runtime.getManifest().version;
  const githubRepository = "ecxod/projekt-kanban-agent-addon";
  const githubReleasesUrl = `https://api.github.com/repos/${githubRepository}/releases?per_page=20`;
  let hostCompatible = false;
  let loadInProgress = false;
  let releaseLoadInProgress = false;
  let latestRelease = null;
  let latestReleaseAssetUrl = "";

  function normalizeVersion(version) {
    return String(version || "")
      .trim()
      .replace(/^v/i, "")
      .split(/[^0-9]+/)
      .filter(Boolean)
      .map((part) => Number.parseInt(part, 10) || 0);
  }

  function compareVersions(left, right) {
    const a = normalizeVersion(left);
    const b = normalizeVersion(right);
    const length = Math.max(a.length, b.length);
    for (let index = 0; index < length; index += 1) {
      const delta = (a[index] || 0) - (b[index] || 0);
      if (delta !== 0) {
        return delta;
      }
    }
    return 0;
  }

  function formatReleaseDate(value) {
    if (!value) {
      return "—";
    }
    try {
      return new Intl.DateTimeFormat("de-DE", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(value));
    } catch (_) {
      return value;
    }
  }

  function pickReleaseAsset(release) {
    if (!release || !Array.isArray(release.assets)) {
      return null;
    }
    const preferred = release.assets.find((asset) => asset && typeof asset.name === "string" && asset.name.endsWith("-signed.xpi"));
    if (preferred) {
      return preferred;
    }
    return release.assets.find((asset) => asset && typeof asset.name === "string" && asset.name.endsWith(".xpi")) || null;
  }

  function releaseDisplayVersion(release) {
    if (!release) {
      return "—";
    }
    return String(release.tag_name || release.name || "—").trim() || "—";
  }

  function setReleaseActionEnabled(enabled) {
    updateReleaseButton.disabled = !enabled;
  }

  function renderReleaseState(message, type = "") {
    setStatus(releaseStatus, message, type);
  }

  function renderInstalledState() {
    installedVersion.textContent = expectedHostVersion;
    installedStatus.textContent = "Aktuell installiert";
  }

  function renderReleaseRow(release) {
    latestRelease = release || null;
    latestReleaseAssetUrl = "";
    if (!latestRelease) {
      githubVersion.textContent = "—";
      githubPublished.textContent = "—";
      githubStatus.textContent = "Keine veröffentlichte Version gefunden";
      updateReleaseButton.textContent = "Update installieren";
      setReleaseActionEnabled(false);
      return;
    }
    const version = releaseDisplayVersion(latestRelease);
    const asset = pickReleaseAsset(latestRelease);
    latestReleaseAssetUrl = asset ? asset.browser_download_url : latestRelease.html_url || "";
    githubVersion.textContent = version;
    githubPublished.textContent = formatReleaseDate(latestRelease.published_at || latestRelease.created_at);
    if (latestRelease.prerelease) {
      githubStatus.textContent = "Vorabversion";
    } else if (compareVersions(version, expectedHostVersion) > 0) {
      githubStatus.textContent = "Update verfügbar";
    } else if (compareVersions(version, expectedHostVersion) < 0) {
      githubStatus.textContent = "Lokale Version ist neuer";
    } else {
      githubStatus.textContent = "Aktuell";
    }
    updateReleaseButton.textContent = asset ? "Update installieren" : "Release öffnen";
    setReleaseActionEnabled(Boolean(latestReleaseAssetUrl));
  }

  async function openLatestRelease() {
    if (!latestReleaseAssetUrl) {
      throw new Error("Für diese Version ist kein XPI-Download gefunden worden.");
    }
    await browser.tabs.create({ url: latestReleaseAssetUrl, active: true });
  }

  async function loadReleases() {
    if (releaseLoadInProgress) {
      return;
    }
    releaseLoadInProgress = true;
    refreshReleasesButton.disabled = true;
    updateReleaseButton.disabled = true;
    renderInstalledState();
    renderReleaseState("GitHub-Releases werden geprüft …");
    githubVersion.textContent = "…";
    githubPublished.textContent = "…";
    githubStatus.textContent = "…";
    try {
      const response = await fetch(githubReleasesUrl, {
        cache: "no-store",
        headers: {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28"
        }
      });
      if (!response.ok) {
        throw new Error(`GitHub-Antwort ${response.status} ${response.statusText}`);
      }
      const releases = await response.json();
      const publishedReleases = Array.isArray(releases) ? releases.filter((release) => release && !release.draft) : [];
      const selectedRelease = publishedReleases.find((release) => !release.prerelease) || publishedReleases[0] || null;
      if (!selectedRelease) {
        renderReleaseRow(null);
        renderReleaseState("Auf GitHub sind noch keine Releases veröffentlicht.", "error");
        return;
      }
      renderReleaseRow(selectedRelease);
      const version = releaseDisplayVersion(selectedRelease);
      if (!selectedRelease.prerelease && compareVersions(version, expectedHostVersion) > 0) {
        renderReleaseState(`Neue Version ${version} ist auf GitHub verfügbar.`, "success");
      } else if (compareVersions(version, expectedHostVersion) === 0) {
        renderReleaseState(`Installierte Version ${expectedHostVersion} ist aktuell.`, "success");
      } else if (selectedRelease.prerelease) {
        renderReleaseState(`Vorabversion ${version} gefunden.`, "success");
      } else {
        renderReleaseState(`GitHub meldet Version ${version}.`, "success");
      }
    } catch (error) {
      renderReleaseRow(null);
      renderReleaseState(`GitHub-Releases konnten nicht geladen werden: ${error.message}`, "error");
    } finally {
      releaseLoadInProgress = false;
      refreshReleasesButton.disabled = false;
      if (latestReleaseAssetUrl) {
        updateReleaseButton.disabled = false;
      }
    }
  }

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
    card.querySelector(".test-agent").disabled = !enabled || !hostCompatible;
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
      if (!hostCompatible) {
        setStatus(status, bridgeStatus.textContent || `Bitte zuerst Native Host ${expectedHostVersion} installieren.`, "error");
        return;
      }
      try {
        await saveAgents();
        setStatus(status, "Verbindung wird geprüft …");
        const result = await nativeRequest("agent.test", { agentId: card.querySelector('[name="id"]').value.trim() });
        const message = result.message || "Der Agent hat den Verbindungstest beantwortet.";
        setStatus(status, message, "success");
        window.alert(`Agent-Antwort:\n\n${message}`);
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
    if (loadInProgress) {
      return;
    }
    loadInProgress = true;
    hostCompatible = false;
    document.getElementById("save").disabled = true;
    document.getElementById("addAgent").disabled = true;
    reloadButton.disabled = true;
    for (const card of agentsContainer.querySelectorAll(".agent-card")) {
      updateEnabled(card, card.dataset.enabled !== "false");
    }
    setStatus(bridgeStatus, "Verbindung wird geprüft …");
    setStatus(saveStatus, "");
    try {
      const hello = await nativeRequest("hello");
      if (hello.version !== expectedHostVersion) {
        throw new Error(`Native Host ${hello.version || "unbekannt"} ist nicht kompatibel. Benötigt wird Version ${expectedHostVersion}. Bitte die Bridge aus dem aktuellen Release installieren.`);
      }
      const config = await nativeRequest("config.get");
      hostCompatible = true;
      document.getElementById("save").disabled = false;
      document.getElementById("addAgent").disabled = false;
      setStatus(bridgeStatus, `Verbunden mit Native Host ${hello.version}.`, "success");
      agentsContainer.replaceChildren();
      for (const agent of config.agents || []) {
        addAgent(agent);
      }
      if (!config.agents || !config.agents.length) {
        addAgent();
      }
      for (const card of agentsContainer.querySelectorAll(".agent-card")) {
        updateEnabled(card, card.dataset.enabled !== "false");
      }
    } catch (error) {
      setStatus(bridgeStatus, `${error.message} Bitte zuerst die lokale Bridge installieren.`, "error");
      if (!agentsContainer.querySelector(".agent-card")) {
        addAgent();
      }
    } finally {
      loadInProgress = false;
      reloadButton.disabled = false;
    }
  }

  refreshReleasesButton.addEventListener("click", loadReleases);
  updateReleaseButton.addEventListener("click", async () => {
    try {
      setReleaseActionEnabled(false);
      await openLatestRelease();
    } catch (error) {
      renderReleaseState(error.message, "error");
    } finally {
      if (latestReleaseAssetUrl) {
        setReleaseActionEnabled(true);
      }
    }
  });
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
  renderInstalledState();
  loadReleases();
  load();
}());
