# Installation on a Linux workstation

## 1. Install the local Native Messaging host

Extract the release bundle and run as the desktop user who runs Firefox:

```sh
./native-host/install-linux.sh
```

No daemon or systemd service is installed. Firefox starts the Native Messaging
host on demand. The host is installed only for the current user.

## 2. Install the Firefox extension

The XPI in the GitHub release is unsigned. For a temporary test installation:

1. Open `about:debugging#/runtime/this-firefox` in Firefox.
2. Select **Load Temporary Add-on**.
3. Select `projekt-kanban-agent-0.1.0.xpi` from the extracted bundle.

Firefox removes temporary add-ons when the browser exits. A normal, persistent
installation in Firefox Release or Beta requires an XPI signed by Mozilla.

## 3. Configure an agent

1. Open the add-on settings.
2. Add a local or SSH agent.
3. Select `Codex CLI` or the provider-neutral `JSONL bridge` adapter.
4. Map the Kanban project ID to an absolute local repository path.
5. Save and use **Verbindung testen**.

Provider credentials remain in the provider's own CLI or operating-system
credential store. Do not put API keys or passwords into the add-on fields.

## Removal

```sh
./native-host/uninstall-linux.sh
```

This removes the installed program and Firefox Native Messaging manifest. Local
agent settings and run history are intentionally retained.
