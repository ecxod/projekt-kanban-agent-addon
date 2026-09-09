# Installation: Projekt Kanban Agent Connector

## Windows Firefox with an agent in WSL

Use the separate Manager/Bridge release for Windows with WSL:

```text
https://github.com/ecxod/projekt-kanban-agent-manager/releases/latest
```

Download and extract:

```text
projekt-kanban-agent-manager-0.1.8.19-windows-wsl.zip
```

Then double-click:

```text
start-agent-manager.cmd
```

The graphical manager lets you select the WSL distribution, enter the Codex and
workspace paths, install/update the bridge, test it, activate/deactivate the
agent, and uninstall the bridge.

For a command-line installation, open PowerShell in the extracted directory and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native-host-windows-wsl\install.ps1
```

The installer uses the default WSL distribution. To select another installed
distribution:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native-host-windows-wsl\install.ps1 -Distribution Ubuntu
```

The installer copies the native host and Windows relay under `%LOCALAPPDATA%`,
verifies the complete relay through `wsl.exe`, and registers it for the current
Windows user under `HKCU\Software\Mozilla\NativeMessagingHosts`.

In the Manager settings use:

- **WSL Distribution:** the selected distribution, for example `Devuan` or `Ubuntu`
- **Agent ID:** `local-codex`
- **Adapter:** `Codex CLI`
- **Agentenprogramm:** the executable returned by `command -v codex` in WSL, for example
  `/home/christian/.nvm/versions/node/v22.23.2/bin/codex`
- **Sandbox:** `workspace-write`, `read-only` or explicitly `danger-full-access`
- **Arbeitsbereich:** an absolute WSL path, for example `/mnt/c/Users/Christian/workspace`

Do not use the old Windows-profile Codex wrapper if it reports an older Codex
version:

```text
/mnt/c/Users/Christian/.codex/bin/wsl/codex
```

Do not use the resolved internal JavaScript file either:

```text
/home/christian/.nvm/versions/node/v22.23.2/lib/node_modules/@openai/codex/bin/codex.js
```

With unrestricted access the workspace field is not used. The start directory
is the agent user's home. In the Windows-WSL bundle a Codex executable below
`/mnt/c/Users/<name>` starts in that Windows profile (the WSL spelling of
`C:\Users\<name>`); otherwise the WSL/Linux home is used.

## Linux Firefox

### 1. Install the local Native Messaging host

Extract the release bundle and run as the desktop user who runs Firefox:

```sh
./native-host/install-linux.sh
```

No daemon or systemd service is installed. Firefox starts the Native Messaging
host on demand. The host is installed only for the current user.

## Install the Firefox extension

Use the add-on release:

```text
https://github.com/ecxod/projekt-kanban-agent-addon/releases/latest
```

Download the XPI signed by Mozilla for self-distribution:

```text
projekt-kanban-agent-0.1.8.4-signed.xpi
```

1. Open **Add-ons and themes** in Firefox.
2. Open the cog menu.
3. Select **Install Add-on From File**.
4. Select `projekt-kanban-agent-0.1.8.4-signed.xpi`.
5. Confirm with **Add**.

A full Firefox restart is normally not required. If Firefox still uses an old
Native Messaging connection, disable/enable the add-on or close and reopen the
add-on page.

## Configure an agent

1. Open the add-on settings.
2. Add a local or SSH agent.
3. Select `Codex CLI` or the provider-neutral `JSONL bridge` adapter.
4. For the restricted modes, select an absolute workspace containing your repositories.
5. Save and use **Verbindung testen**.

Provider credentials remain in the provider's own CLI or operating-system
credential store. Do not put API keys or passwords into the add-on fields.

On Linux, `native-host/agent-manager.sh` combines installation, configuration,
testing, activation/deactivation, and removal in one menu. It does not install a
daemon or require systemd.

## Verify the download

Run `sha256sum -c SHA256SUMS` in the directory containing the downloaded
release files. The signed XPI additionally contains Mozilla's `META-INF`
signature files.

## Removal

On Windows with WSL:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native-host-windows-wsl\uninstall.ps1
```

On Linux:

```sh
./native-host/uninstall-linux.sh
```

This removes the installed program and Firefox Native Messaging manifest. Local
agent settings and run history are intentionally retained.

If the Windows relay fails, inspect
`%LOCALAPPDATA%\ProjektKanbanAgent\relay.log` before reinstalling.
