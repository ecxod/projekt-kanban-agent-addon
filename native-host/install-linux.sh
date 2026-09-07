#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_base=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_home=${PK_AGENT_USER_HOME:-"$HOME"}
install_dir="$data_base/projekt-kanban-agent"
manifest_dir="$user_home/.mozilla/native-messaging-hosts"
manifest_path="$manifest_dir/de.projekt_kanban.agent.json"
host_path="$install_dir/kanban_agent_host.py"

install -d -m 0700 "$install_dir"
install -d -m 0700 "$manifest_dir"
install -m 0755 "$script_dir/kanban_agent_host.py" "$host_path"
install -m 0644 "$script_dir/feedback-schema.json" "$install_dir/feedback-schema.json"

python3 - "$host_path" "$manifest_path" <<'PY'
import json
import os
import sys

host_path, manifest_path = sys.argv[1:]
manifest = {
    "name": "de.projekt_kanban.agent",
    "description": "Connect Projekt Kanban to user-owned coding agents",
    "path": host_path,
    "type": "stdio",
    "allowed_extensions": ["projekt-kanban-agent@ecxod.de"],
}
temporary = manifest_path + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
os.chmod(temporary, 0o600)
os.replace(temporary, manifest_path)
PY

printf '%s\n' "Native Host installed: $host_path"
printf '%s\n' "Firefox manifest installed: $manifest_path"
printf '%s\n' "Restart Firefox, then open the add-on settings."
