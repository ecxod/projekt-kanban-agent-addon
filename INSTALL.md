# Installation

## Windows Firefox with an agent in WSL

Extract `projekt-kanban-agent-0.1.8.0-windows-wsl.zip` and double-click:

```text
native-host-windows-wsl\start-agent-manager.cmd
```

The graphical manager lets you select the WSL distribution, enter the Codex
and workspace paths, install/update the bridge, test it, activate/deactivate
the agent, and uninstall the bridge.

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
verifies the complete relay through `wsl.exe`, and registers it for the current Windows user under
`HKCU\Software\Mozilla\NativeMessagingHosts`.

Restart Firefox after installation. In the add-on settings use:

- **Verbindung:** `Lokal / über Windows-WSL-Bridge`
- **Adapter:** `Codex CLI`
- **Agentenprogramm:** the WSL path to Codex, for example
  `/mnt/c/Users/Christian/.codex/bin/wsl/codex`
- **Sandbox:** `Arbeitsbereich schreiben`, `Nur lesen (Dry-Run)` or explicitly
  `Uneingeschränkter Zugriff`
- **Arbeitsbereich:** a directory containing any number of projects, for example
  `/mnt/c/Users/Christian/workspace`

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

The release bundle contains the XPI signed by Mozilla for self-distribution:

1. Open **Add-ons and themes** in Firefox.
2. Open the cog menu.
3. Select **Install Add-on From File**.
4. Select `projekt-kanban-agent-0.1.8.0-signed.xpi` from the extracted bundle.
5. Confirm with **Add**.

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
