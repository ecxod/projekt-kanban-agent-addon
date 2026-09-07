# Projekt Kanban Agent Connector

Firefox connector for sending user-selected tasks from
[`projekt-kanban.de`](https://projekt-kanban.de/) directly to coding agents
owned and configured by the user. The Projekt Kanban web server does not proxy
agent traffic and never receives agent credentials.

The repository contains two parts:

- a Firefox Manifest V3 WebExtension in `addon/`;
- a user-installed Linux Native Messaging host in `native-host/`.

The native host supports:

- `codex-exec`: OpenAI Codex CLI through its machine-readable JSONL mode;
- `jsonl-bridge`: a provider-neutral protocol for Gemini wrappers, local models,
  or other coding-agent bridges;
- local execution and execution on a user-controlled machine over SSH.

## Security model

- No OpenAI, Gemini, SSH, or other provider password is stored in the add-on.
- Agent executables, SSH targets, and repository paths are stored in the
  user-owned native-host configuration with mode `0600`.
- The website can send only a configured `agentId` and `projectId`; it cannot
  choose an executable, SSH host, CLI arguments, or filesystem path.
- Only `read-only` and `workspace-write` sandboxes are accepted.
- A run requires a visible add-on-controlled confirmation.
- The content script runs only on `https://projekt-kanban.de/*`.
- The toolbar icon is gray by default and turns blue only while a verified
  `projekt-kanban.de` page is connected.
- There is no telemetry, analytics, advertising, remote JavaScript, or dynamic
  code execution in the extension.

The Native Messaging host still starts powerful user-selected tools. Users must
review task content, restrict repository mappings, and apply the security policy
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
5. Open the extension settings and configure one or more agents and project
   mappings.
6. Use **Verbindung testen** before submitting a task.

The build creates an unsigned XPI. Normal Firefox release installations require
Mozilla signing; the unsigned package is intended for temporary development
installation or upload to AMO for unlisted/listed signing.

## Build and test

No third-party JavaScript is bundled and no package installation is required.

```sh
npm test
npm run build
```

Artifacts are written to `dist/`.

## Agent configuration

Each agent has:

- a stable ID and label;
- an adapter: `codex-exec` or `jsonl-bridge`;
- a transport: `local` or `ssh`;
- a fixed executable and optional fixed arguments;
- a sandbox;
- one or more logical project IDs mapped to repositories.

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
