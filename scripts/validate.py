#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"


def fail(message: str) -> None:
    raise SystemExit(message)


manifest = json.loads((ADDON / "manifest.json").read_text(encoding="utf-8"))
package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
if manifest.get("manifest_version") != 3:
    fail("manifest_version must be 3")
if package.get("version") != manifest.get("version"):
    fail("package and extension versions must match")
if manifest.get("permissions") != ["nativeMessaging"]:
    fail("extension must request only nativeMessaging API permission")
if manifest.get("host_permissions") != ["https://projekt-kanban.de/*"]:
    fail("host permission must be restricted to projekt-kanban.de")
gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
if gecko.get("strict_min_version") != "128.0":
    fail("desktop Firefox compatibility must start at ESR 128")
if gecko.get("data_collection_permissions", {}).get("required") != ["websiteContent"]:
    fail("websiteContent data declaration is required")
if manifest.get("incognito") != "not_allowed":
    fail("private browsing must remain disabled")

addon_files = [
    "background.js",
    "content-script.js",
    "options/options.html",
    "popup/popup.html",
    "icons/agent.svg",
    "icons/agent-inactive.svg",
]
for relative in addon_files:
    if not (ADDON / relative).is_file():
        fail(f"missing extension file: {relative}")

for relative in [
    "native-host/kanban_agent_host.py",
    "native-host/feedback-schema.json",
    "native-host/agent-manager.sh",
    "native-host-windows-wsl/install.ps1",
    "native-host-windows-wsl/agent-manager.ps1",
    "native-host-windows-wsl/start-agent-manager.cmd",
    "native-host-windows-wsl/uninstall.ps1",
    "native-host-windows-wsl/wsl-relay.c",
]:
    if not (ROOT / relative).is_file():
        fail(f"missing release file: {relative}")

host_source = (ROOT / "native-host/kanban_agent_host.py").read_text(encoding="utf-8")
if f'VERSION = "{manifest["version"]}"' not in host_source:
    fail("native host and extension versions must match")

windows_installer = (ROOT / "native-host-windows-wsl/install.ps1").read_text(encoding="utf-8")
for required in [
    "HKCU:\\Software\\Mozilla\\NativeMessagingHosts\\$HostName",
    "allowed_extensions",
    "--exec python3",
    "--self-test",
    "wslpath -a -u",
    "relay-config.txt",
    "projekt-kanban-agent-wsl.exe",
]:
    if required not in windows_installer:
        fail(f"Windows-WSL installer is missing required behavior: {required}")

if f"$ExpectedVersion = '{manifest['version']}'" not in windows_installer:
    fail("Windows-WSL installer and extension versions must match")

windows_manager_path = ROOT / "native-host-windows-wsl/agent-manager.ps1"
windows_manager_bytes = windows_manager_path.read_bytes()
if not windows_manager_bytes.startswith(b"\xef\xbb\xbf"):
    fail("Windows PowerShell manager must use a UTF-8 BOM for Windows PowerShell 5.1")
windows_manager = windows_manager_bytes.decode("utf-8-sig")
for required in [
    "System.Windows.Forms",
    "Install / update bridge",
    "Save agent configuration",
    "Test Codex connection",
    "Enable agent for tasks",
    "Disable agent and cancel runs",
    "SettingsPage",
    "HelpPage",
    "SettingsButtonPanel",
    "--manager-configure-local",
    "InitialDistribution",
    "Get-WslDistributions",
    "Microsoft\\Windows\\CurrentVersion\\Lxss",
]:
    if required not in windows_manager:
        fail(f"Windows manager is missing required behavior: {required}")

windows_manager_launcher = (ROOT / "native-host-windows-wsl/start-agent-manager.cmd").read_text(encoding="ascii")
for required in ["WSLDIST", "wsl.exe", "--list --quiet", "-InitialDistribution"]:
    if required not in windows_manager_launcher:
        fail(f"Windows manager launcher is missing WSL auto-detection: {required}")

relay_source = (ROOT / "native-host-windows-wsl/wsl-relay.c").read_text(encoding="utf-8")
for exit_code in range(21, 27):
    if f"({exit_code}," not in relay_source and f"return {exit_code};" not in relay_source:
        fail(f"Windows relay is missing self-test diagnostic exit code {exit_code}")

linux_manager = ROOT / "native-host/agent-manager.sh"
completed = subprocess.run(["bash", "-n", str(linux_manager)], capture_output=True, text=True)
if completed.returncode:
    sys.stderr.write(completed.stderr)
    fail("Linux agent manager has invalid Bash syntax")

for script in sorted(ADDON.rglob("*.js")):
    completed = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    if completed.returncode:
        sys.stderr.write(completed.stderr)
        fail(f"JavaScript syntax check failed: {script.relative_to(ROOT)}")

for html in ADDON.rglob("*.html"):
    source = html.read_text(encoding="utf-8")
    if "<script>" in source or "javascript:" in source.lower():
        fail(f"inline JavaScript is not allowed: {html.relative_to(ROOT)}")

print("Extension manifest, permissions, files, CSP assumptions, and JavaScript syntax are valid.")
