# Installation on a Linux workstation

## 1. Install the local Native Messaging host

Extract the release bundle and run as the desktop user who runs Firefox:

```sh
./native-host/install-linux.sh
```

No daemon or systemd service is installed. Firefox starts the Native Messaging
host on demand. The host is installed only for the current user.

## 2. Install the Firefox extension

The release bundle contains the XPI signed by Mozilla for self-distribution:

1. Open **Add-ons and themes** in Firefox.
2. Open the cog menu.
3. Select **Install Add-on From File**.
4. Select `projekt-kanban-agent-0.1.1-signed.xpi` from the extracted bundle.
5. Confirm with **Add**.

## 3. Configure an agent

1. Open the add-on settings.
2. Add a local or SSH agent.
3. Select `Codex CLI` or the provider-neutral `JSONL bridge` adapter.
4. Map the Kanban project ID to an absolute local repository path.
5. Save and use **Verbindung testen**.

Provider credentials remain in the provider's own CLI or operating-system
credential store. Do not put API keys or passwords into the add-on fields.

## Verify the download

Run `sha256sum -c SHA256SUMS` in the directory containing the downloaded
release files. The signed XPI additionally contains Mozilla's `META-INF`
signature files.

## Removal

```sh
./native-host/uninstall-linux.sh
```

This removes the installed program and Firefox Native Messaging manifest. Local
agent settings and run history are intentionally retained.
