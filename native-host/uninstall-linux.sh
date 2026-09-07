#!/bin/sh
set -eu

data_base=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_home=${PK_AGENT_USER_HOME:-"$HOME"}
install_dir="$data_base/projekt-kanban-agent"
manifest_path="$user_home/.mozilla/native-messaging-hosts/de.projekt_kanban.agent.json"

rm -f -- "$manifest_path"
rm -f -- "$install_dir/kanban_agent_host.py" "$install_dir/feedback-schema.json"
rmdir -- "$install_dir" 2>/dev/null || true

printf '%s\n' "Projekt Kanban Native Host removed."
printf '%s\n' "Agent settings and run history were retained in the XDG config/state directories."
