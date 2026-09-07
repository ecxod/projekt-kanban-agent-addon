#!/bin/bash
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_base=${XDG_DATA_HOME:-"$HOME/.local/share"}
installed_host="$data_base/projekt-kanban-agent/kanban_agent_host.py"

agent_id=local-codex
agent_label="Local Codex"
agent_program=codex
workspace="$HOME/workspace"
sandbox=workspace-write

ui_backend=${PK_AGENT_UI:-auto}
if [ "$ui_backend" = auto ]; then
    ui_backend=text
    if command -v dialog >/dev/null 2>&1; then
        ui_backend=dialog
    elif command -v whiptail >/dev/null 2>&1; then
        ui_backend=whiptail
    fi
fi

message() {
    title=$1
    body=$2
    if [ "$ui_backend" = dialog ]; then
        dialog --title "$title" --msgbox "$body" 14 72
    elif [ "$ui_backend" = whiptail ]; then
        whiptail --title "$title" --msgbox "$body" 14 72
    else
        printf '\n%s\n%s\n\n' "$title" "$body"
        printf 'Weiter mit Enter …'
        read -r _answer
    fi
}

input_value() {
    title=$1
    prompt=$2
    default_value=$3
    if [ "$ui_backend" = dialog ]; then
        dialog --stdout --title "$title" --inputbox "$prompt" 10 72 "$default_value"
    elif [ "$ui_backend" = whiptail ]; then
        whiptail --title "$title" --inputbox "$prompt" 10 72 "$default_value" 3>&1 1>&2 2>&3
    else
        printf '%s [%s]: ' "$prompt" "$default_value" >&2
        read -r answer
        printf '%s\n' "${answer:-$default_value}"
    fi
}

choose_sandbox() {
    if [ "$ui_backend" = dialog ]; then
        dialog --stdout --title 'Zugriffsart' --menu 'Wie darf der Agent arbeiten?' 15 72 4 \
            read-only 'Nur lesen (Dry-Run)' \
            workspace-write 'Arbeitsbereich schreiben' \
            danger-full-access 'Uneingeschränkter Zugriff'
    elif [ "$ui_backend" = whiptail ]; then
        whiptail --title 'Zugriffsart' --menu 'Wie darf der Agent arbeiten?' 15 72 4 \
            read-only 'Nur lesen (Dry-Run)' \
            workspace-write 'Arbeitsbereich schreiben' \
            danger-full-access 'Uneingeschränkter Zugriff' 3>&1 1>&2 2>&3
    else
        printf '1) Nur lesen (Dry-Run)\n2) Arbeitsbereich schreiben\n3) Uneingeschränkter Zugriff\nAuswahl [2]: ' >&2
        read -r answer
        case ${answer:-2} in
            1) printf '%s\n' read-only ;;
            3) printf '%s\n' danger-full-access ;;
            *) printf '%s\n' workspace-write ;;
        esac
    fi
}

menu_choice() {
    if [ "$ui_backend" = dialog ]; then
        dialog --stdout --title 'Projekt Kanban Agent Manager' --menu \
            'Codex läuft nicht als Dienst. Aktivieren erlaubt Firefox, ihn für eine Task zu starten.' 20 78 9 \
            install 'Bridge installieren / aktualisieren' \
            configure 'Agentenpfade und Zugriffsart konfigurieren' \
            test 'Verbindung testen' \
            start 'Agent starten (aktivieren)' \
            stop 'Agent stoppen (deaktivieren)' \
            status 'Status anzeigen' \
            uninstall 'Bridge deinstallieren' \
            quit 'Beenden'
    elif [ "$ui_backend" = whiptail ]; then
        whiptail --title 'Projekt Kanban Agent Manager' --menu \
            'Codex läuft nicht als Dienst. Aktivieren erlaubt Firefox, ihn für eine Task zu starten.' 20 78 9 \
            install 'Bridge installieren / aktualisieren' \
            configure 'Agentenpfade und Zugriffsart konfigurieren' \
            test 'Verbindung testen' \
            start 'Agent starten (aktivieren)' \
            stop 'Agent stoppen (deaktivieren)' \
            status 'Status anzeigen' \
            uninstall 'Bridge deinstallieren' \
            quit 'Beenden' 3>&1 1>&2 2>&3
    else
        if [ -t 2 ]; then clear >&2 2>/dev/null || true; fi
        printf '%s\n' 'Projekt Kanban Agent Manager' >&2
        printf '%s\n' '1) Installieren / aktualisieren' '2) Konfigurieren' '3) Verbindung testen' \
            '4) Agent starten (aktivieren)' '5) Agent stoppen (deaktivieren)' \
            '6) Status' '7) Deinstallieren' '0) Beenden' >&2
        printf 'Auswahl: ' >&2
        read -r answer
        case $answer in
            1) printf '%s\n' install ;;
            2) printf '%s\n' configure ;;
            3) printf '%s\n' test ;;
            4) printf '%s\n' start ;;
            5) printf '%s\n' stop ;;
            6) printf '%s\n' status ;;
            7) printf '%s\n' uninstall ;;
            *) printf '%s\n' quit ;;
        esac
    fi
}

require_installation() {
    if [ ! -x "$installed_host" ]; then
        message 'Noch nicht installiert' 'Bitte zuerst „Bridge installieren / aktualisieren“ auswählen.'
        return 1
    fi
}

run_host() {
    output=$(python3 "$installed_host" "$@" 2>&1)
    status=$?
    if [ $status -ne 0 ]; then
        message 'Fehler' "$output"
        return $status
    fi
    pretty=$(python3 - "$output" <<'PY'
import json
import sys

response = json.loads(sys.argv[1])
data = response.get("data", {})
if "agents" in data:
    lines = [f"Native Host {data.get('version', '?')}"]
    for agent in data["agents"]:
        state = "AKTIV" if agent.get("enabled") else "DEAKTIVIERT"
        location = agent.get("startDirectory") or agent.get("workspace") or "-"
        lines.append(f"{agent.get('label', agent.get('id'))}: {state}")
        lines.append(f"  {agent.get('sandbox')} · {location}")
    if not data["agents"]:
        lines.append("Noch kein Agent konfiguriert.")
    print("\n".join(lines))
else:
    print(data.get("message") or json.dumps(data, ensure_ascii=False, indent=2))
PY
    ) || pretty=$output
    message 'Ergebnis' "$pretty"
}

configure_agent() {
    agent_id=$(input_value 'Agent' 'Agent-ID' "$agent_id") || return
    agent_label=$(input_value 'Agent' 'Anzeigename' "$agent_label") || return
    agent_program=$(input_value 'Agent' 'Pfad zum Agentenprogramm' "$agent_program") || return
    sandbox=$(choose_sandbox) || return
    if [ "$sandbox" = danger-full-access ]; then
        workspace=__HOME__
    else
        workspace=$(input_value 'Arbeitsbereich' 'Verzeichnis mit Ihren Projekten' "$workspace") || return
    fi
    require_installation || return
    run_host --manager-configure-local "$agent_id" "$agent_label" "$agent_program" "$sandbox" "$workspace"
}

while true; do
    choice=$(menu_choice) || break
    case $choice in
        install)
            if output=$("$script_dir/install-linux.sh" 2>&1); then
                message 'Installation erfolgreich' "$output"
            else
                message 'Installation fehlgeschlagen' "$output"
            fi
            ;;
        configure) configure_agent ;;
        test) require_installation && run_host --manager-ping "$agent_id" ;;
        start) require_installation && run_host --manager-enable "$agent_id" ;;
        stop) require_installation && run_host --manager-disable "$agent_id" ;;
        status) require_installation && run_host --manager-status ;;
        uninstall)
            if output=$("$script_dir/uninstall-linux.sh" 2>&1); then
                message 'Deinstallation abgeschlossen' "$output"
            else
                message 'Deinstallation fehlgeschlagen' "$output"
            fi
            ;;
        quit) break ;;
    esac
done
