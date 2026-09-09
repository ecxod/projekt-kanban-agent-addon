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
  const githubAsset = document.getElementById("githubAsset");
  const refreshReleasesButton = document.getElementById("refreshReleases");
  const updateReleaseButton = document.getElementById("updateRelease");
  const reloadButton = document.getElementById("reload");
  const extensionVersion = browser.runtime.getManifest().version;
  const requiredHostProtocol = 1;
  const githubRepository = "ecxod/projekt-kanban-agent-addon";
  const githubReleasesUrl = `https://api.github.com/repos/${githubRepository}/releases?per_page=20`;
  const { compareVersions, getReleaseVersion, pickReleaseAsset, selectLatestRelease } = globalThis.PKReleaseUtils;
  let hostCompatible = false;
  let loadInProgress = false;
  let releaseLoadInProgress = false;
  let latestRelease = null;
  let latestReleaseTargetUrl = "";

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
    installedVersion.textContent = extensionVersion;
    installedStatus.textContent = "Installiert";
  }

  function renderReleaseRow(release) {
    latestRelease = release || null;
    latestReleaseTargetUrl = "";
    if (!latestRelease) {
      githubVersion.textContent = "—";
      githubPublished.textContent = "—";
      githubStatus.textContent = "Keine veröffentlichte Version gefunden";
      githubAsset.textContent = "—";
      updateReleaseButton.textContent = "Update installieren";
      setReleaseActionEnabled(false);
      return;
    }
    const version = releaseDisplayVersion(latestRelease);
    const releaseVersion = getReleaseVersion(latestRelease);
    const assetSelection = pickReleaseAsset(latestRelease);
    const asset = assetSelection.asset;
    latestReleaseTargetUrl = asset ? asset.browser_download_url : latestRelease.html_url || "";
    githubVersion.textContent = version;
    githubPublished.textContent = formatReleaseDate(latestRelease.published_at || latestRelease.created_at);
    githubAsset.textContent = asset
      ? `${asset.name}${assetSelection.kind === "signed" ? " (signiert)" : " (nicht signiert)"}`
      : `Kein passendes XPI für ${releaseVersion || "diese Version"}`;
    const versionComparison = releaseVersion ? compareVersions(releaseVersion, extensionVersion) : null;
    if (versionComparison === null) {
      githubStatus.textContent = "Versionsnummer des Release-Tags fehlt";
    } else if (versionComparison > 0 && assetSelection.kind === "signed") {
      githubStatus.textContent = "Update verfügbar (signiert)";
    } else if (versionComparison > 0 && assetSelection.kind === "unsigned") {
      githubStatus.textContent = "Update verfügbar (nicht signiert)";
    } else if (versionComparison > 0) {
      githubStatus.textContent = "Neue Version, passendes XPI fehlt";
    } else if (versionComparison < 0) {
      githubStatus.textContent = "Lokale Version ist neuer";
    } else if (assetSelection.kind === "missing") {
      githubStatus.textContent = "Aktuell, passendes XPI fehlt";
    } else {
      githubStatus.textContent = "Aktuell";
    }
    updateReleaseButton.textContent = assetSelection.kind === "signed"
      ? "Update installieren"
      : (assetSelection.kind === "unsigned" ? "XPI herunterladen" : "Release öffnen");
    setReleaseActionEnabled(Boolean(latestReleaseTargetUrl));
  }

  async function openLatestRelease() {
    if (!latestReleaseTargetUrl) {
      throw new Error("Für diese Version ist kein passendes Release-Ziel gefunden worden.");
    }
    await browser.tabs.create({ url: latestReleaseTargetUrl, active: true });
  }

  async function releaseNetworkDiagnostics() {
    let githubPermission = "unbekannt";
    try {
      if (browser.permissions && browser.permissions.contains) {
        githubPermission = await browser.permissions.contains({ origins: ["https://api.github.com/*"] })
          ? "erteilt"
          : "fehlt";
      }
    } catch (_) {
      githubPermission = "nicht prüfbar";
    }
    return `URL: ${githubReleasesUrl}; Online: ${navigator.onLine ? "ja" : "nein"}; GitHub-Berechtigung: ${githubPermission}`;
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
      const selectedRelease = selectLatestRelease(releases);
      if (!selectedRelease) {
        renderReleaseRow(null);
        renderReleaseState("Auf GitHub sind noch keine stabilen Releases veröffentlicht.", "error");
        return;
      }
      renderReleaseRow(selectedRelease);
      const version = getReleaseVersion(selectedRelease) || releaseDisplayVersion(selectedRelease);
      const versionComparison = getReleaseVersion(selectedRelease)
        ? compareVersions(version, extensionVersion)
        : null;
      const assetSelection = pickReleaseAsset(selectedRelease);
      if (versionComparison === null) {
        renderReleaseState("Das Release enthält keine auslesbare Versionsnummer.", "error");
      } else if (versionComparison > 0 && assetSelection.kind === "signed") {
        renderReleaseState(`Neue signierte Version ${version} ist auf GitHub verfügbar.`, "success");
      } else if (versionComparison > 0 && assetSelection.kind === "unsigned") {
        renderReleaseState(`Neue Version ${version} ist verfügbar, aber das XPI ist nicht signiert.`, "error");
      } else if (versionComparison > 0) {
        renderReleaseState(`Version ${version} ist verfügbar, aber ohne passendes XPI.`, "error");
      } else if (versionComparison === 0) {
        renderReleaseState(`Installierte Version ${extensionVersion} ist aktuell.`, "success");
      } else if (versionComparison < 0) {
        renderReleaseState(`GitHub meldet Version ${version}; die lokale Version ist neuer.`, "success");
      } else {
        renderReleaseState(`GitHub meldet Version ${version}.`, "success");
      }
    } catch (error) {
      renderReleaseRow(null);
      const detail = error && error.message ? error.message : String(error);
      const diagnostics = await releaseNetworkDiagnostics();
      renderReleaseState(`GitHub-Releases konnten nicht geladen werden: ${detail} (${diagnostics})`, "error");
    } finally {
      releaseLoadInProgress = false;
      refreshReleasesButton.disabled = false;
      if (latestReleaseTargetUrl) {
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
        setStatus(status, bridgeStatus.textContent || `Bitte zuerst einen Native Host mit Protokoll ${requiredHostProtocol} installieren.`, "error");
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
      throw new Error(`Bitte zuerst einen Native Host mit Protokoll ${requiredHostProtocol} installieren und danach „Neu laden“ wählen.`);
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
      if (hello.protocol !== requiredHostProtocol) {
        throw new Error(`Native Host ${hello.version || "unbekannt"} verwendet Protokoll ${hello.protocol || "unbekannt"}. Benötigt wird Protokoll ${requiredHostProtocol}. Bitte die Bridge über den Agent Manager aktualisieren.`);
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
      if (latestReleaseTargetUrl) {
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
