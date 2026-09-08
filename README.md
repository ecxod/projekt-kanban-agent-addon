# Projekt Kanban Agent Connector

Firefox connector for sending user-selected tasks from
[`projekt-kanban.de`](https://projekt-kanban.de/) directly to coding agents
owned and configured by the user. The Projekt Kanban web server does not proxy
agent traffic and never receives agent credentials.

The repository contains two parts:

- a Firefox Manifest V3 WebExtension in `addon/`;
- a Native Messaging host in `native-host/`;
- a per-user Windows-to-WSL installer in `native-host-windows-wsl/`.

The native host supports:

- `codex-exec`: OpenAI Codex CLI through its machine-readable JSONL mode;
- `jsonl-bridge`: a provider-neutral protocol for Gemini wrappers, local models,
  or other coding-agent bridges;
- local execution and execution on a user-controlled machine over SSH.

## Simple agent manager

The release bundles include a guided manager, so paths and activation do not
have to be maintained manually in JSON files or shell commands.

- **Windows with WSL:** double-click
  `native-host-windows-wsl/start-agent-manager.cmd`. The PowerShell window
  installs or updates the bridge, stores the Codex and workspace paths, tests
  the connection, activates/deactivates the agent, and uninstalls the bridge.
  The launcher selects the default WSL distribution automatically; the manager
  also reads the WSL registry as a fallback.
- **Linux:** run `native-host/agent-manager.sh`. It uses `dialog` or `whiptail`
  when available and otherwise provides the same menu directly in the terminal.

Codex is not a permanent service. An active configuration allows Firefox to
start Codex on demand for a confirmed task. Stopping the agent disables new
runs and cancels an already running job for that agent.

## Security model

- No OpenAI, Gemini, SSH, or other provider password is stored in the add-on.
- Agent executables, SSH targets, and workspace paths are stored in the
  user-owned native-host configuration with mode `0600`.
- The website can send only a configured `agentId` and a logical `projectId`; it cannot
  choose an executable, SSH host, CLI arguments, or filesystem path.
- `read-only` provides a dry-run/analysis mode, while `workspace-write` limits
  writes to the configured workspace.
- `danger-full-access` is available only as an explicit user configuration. It
  starts in the agent user's home directory and requires an additional warning
  checkbox before every run.
- A run requires a visible add-on-controlled confirmation.
- The content script runs only on `https://projekt-kanban.de/*`.
- The toolbar icon is gray by default and turns blue only while a verified
  `projekt-kanban.de` page is connected.
- There is no telemetry, analytics, advertising, remote JavaScript, or dynamic
  code execution in the extension.

The Native Messaging host still starts powerful user-selected tools. Users must
review task content, choose an appropriate workspace or sandbox, and apply the security policy
of their chosen agent.

## Install for development on Linux

1. Install and authenticate the coding agent locally. For Codex, verify that
   `codex` runs successfully in a terminal.
2. Install the Native Messaging host:

   ```sh
   ./native-host/install-linux.sh
   ```

3. Open `about:debugging#/runtime/this-firefox` in Firefox.
4. Choose **Load Temporary Add-on** and select `addon/manifest.json`.
5. Open the extension settings and configure one or more agents and workspaces.
6. Use **Verbindung testen** before submitting a task.

Configured agents can be disabled without deleting their executable, SSH target,
or workspace. Disabled agents remain editable in settings but are not
exposed to the Kanban page and cannot start runs until re-enabled.

## Windows Firefox with Codex in WSL

Download and extract the Windows-WSL release ZIP, then run from PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native-host-windows-wsl\install.ps1
```

The bridge is registered only for the current Windows user. A native Windows
relay handles Firefox's binary framing and exchanges base64-encoded JSON lines
with the Python host inside WSL. No Python installation on Windows and no
Windows service are required. An optional `-Distribution` parameter selects a
non-default WSL distribution.

In the add-on settings choose the local connection and enter WSL paths. Example:

```text
Agentenprogramm: /mnt/c/Users/Christian/.codex/bin/wsl/codex
Arbeitsbereich: /mnt/c/Users/Christian/workspace
```

The build creates an unsigned XPI. Normal Firefox release installations require
Mozilla signing; the unsigned package is intended for temporary development
installation or upload to AMO for unlisted/listed signing.

The add-on settings can also check GitHub releases for a newer version and
open the installable XPI from the latest release.

Tagged releases are published automatically by GitHub Actions when a `v*`
tag is pushed.

## Build and test

No third-party JavaScript is bundled and no package installation is required.

```sh
npm test
npm run build
```

Artifacts are written to `dist/`.

The Linux release bundle contains the Mozilla-signed XPI, Native Messaging host,
installer, example configuration, license, and [`INSTALL.md`](INSTALL.md). The
unsigned XPI produced by the normal build is for development; the signed release
artifact can be installed persistently from Firefox's Add-ons Manager.

Firefox desktop 128 and later is supported. Firefox 140 and later displays its
built-in website-content transmission disclosure during installation. On Firefox
128 through 139, the add-on's own confirmation dialog provides the disclosure
and blocks every task transmission until the user explicitly approves.

## Agent configuration

Each agent has:

- a stable ID and label;
- an adapter: `codex-exec` or `jsonl-bridge`;
- a transport: `local` or `ssh`;
- a fixed executable and optional fixed arguments;
- a sandbox;
- one workspace containing any number of repositories; or
- unrestricted access starting in the agent user's home directory.

Passwords and API keys are intentionally not accepted as configuration fields.
Local provider authentication remains with the provider CLI. Remote execution
uses the user's existing SSH key or SSH agent.

See [`docs/bridge-protocol.md`](docs/bridge-protocol.md) for adding Gemini or
another provider and [`docs/page-protocol.md`](docs/page-protocol.md) for the
Projekt Kanban integration.

## Persistent run feedback

Runs continue in a detached runner if the Native Messaging connection closes.
Firefox can later use `run.status` or `run.list` to retrieve the final status and
normalized feedback. The Kanban application should persist that response under
the task's `agentRuns` array.

State is stored under `${XDG_STATE_HOME:-~/.local/state}/projekt-kanban-agent`.
Task prompts are removed from the native job request after the runner starts;
only a SHA-256 prompt snapshot and the resulting run feedback remain.

## Firefox review notes

- Required permissions: `nativeMessaging` and access to
  `https://projekt-kanban.de/*` only.
- Required Firefox data declaration: `websiteContent`, because the user-selected
  task text is transmitted to the user's native agent.
- Private browsing is disabled.
- Native messages never contain stored provider credentials.
- Source is intentionally readable and unminified.

See [`PRIVACY.md`](PRIVACY.md) for the complete data disclosure.
