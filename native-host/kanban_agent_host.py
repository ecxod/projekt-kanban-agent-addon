#!/usr/bin/env python3
"""Firefox Native Messaging host for user-owned coding agents.

The host deliberately accepts logical agent/project IDs from web content. Executable
paths, SSH destinations and workspace paths come only from the user-owned config.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


VERSION = "0.1.8.0"
HOST_NAME = "de.projekt_kanban.agent"
MAX_NATIVE_MESSAGE = 1024 * 1024
MAX_PROMPT_BYTES = 400 * 1024
MAX_EVENT_TEXT = 24 * 1024
MAX_STORED_EVENTS = 250
AGENT_TEST_TIMEOUT_SECONDS = 90
AGENT_TEST_PROMPT = (
    "Hallo Agent, bitte melde Dich! Dies ist ausschließlich ein Verbindungstest. "
    "Ändere keine Dateien und führe keine weiteren Aktionen aus. "
    "Antworte mit einem kurzen Satz auf Deutsch."
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SSH_HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]{1,255}$")
EXECUTABLE_PATTERN = re.compile(r"^[A-Za-z0-9_./+~-]{1,512}$")
ALLOWED_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_ADAPTERS = {"codex-exec", "jsonl-bridge"}
ALLOWED_TRANSPORTS = {"local", "ssh"}


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def config_root() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base).expanduser() if base else Path.home() / ".config"


def state_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    return Path(base).expanduser() if base else Path.home() / ".local" / "state"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    ensure_private_directory(path.parent)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as error:
        raise ProtocolError("INVALID_STATE", f"Cannot read {path.name}: {error}") from error


def truncate_text(value: Any, limit: int = MAX_EVENT_TEXT) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def process_is_alive(pid: Any) -> bool:
    try:
        number = int(pid)
        if number <= 1:
            return False
        os.kill(number, 0)
        return True
    except (ValueError, TypeError, ProcessLookupError, PermissionError, OSError):
        return False


def validate_identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not ID_PATTERN.fullmatch(text):
        raise ProtocolError("INVALID_CONFIG", f"Invalid {field}.")
    return text


def validate_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("agents"), list):
        raise ProtocolError("INVALID_CONFIG", "Configuration must contain version 1 and an agents list.")
    if len(raw["agents"]) > 50:
        raise ProtocolError("INVALID_CONFIG", "At most 50 agents can be configured.")

    allowed_keys = {
        "id", "label", "adapter", "transport", "executable", "arguments",
        "sshHost", "sandbox", "workspace", "projects", "enabled"
    }
    seen_ids: set[str] = set()
    agents: list[dict[str, Any]] = []
    for source in raw["agents"]:
        if not isinstance(source, dict) or set(source) - allowed_keys:
            raise ProtocolError("INVALID_CONFIG", "Agent configuration contains unsupported fields.")
        agent_id = validate_identifier(source.get("id"), "agent ID")
        if agent_id in seen_ids:
            raise ProtocolError("INVALID_CONFIG", f"Duplicate agent ID: {agent_id}")
        seen_ids.add(agent_id)
        label = str(source.get("label") or "").strip()
        if not label or len(label) > 100:
            raise ProtocolError("INVALID_CONFIG", f"Invalid label for agent {agent_id}.")
        enabled = source.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ProtocolError("INVALID_CONFIG", f"Invalid enabled state for agent {agent_id}.")
        adapter = str(source.get("adapter") or "codex-exec")
        transport = str(source.get("transport") or "local")
        sandbox = str(source.get("sandbox") or "read-only")
        executable = str(source.get("executable") or "").strip()
        if adapter not in ALLOWED_ADAPTERS or transport not in ALLOWED_TRANSPORTS:
            raise ProtocolError("INVALID_CONFIG", f"Unsupported adapter or transport for {agent_id}.")
        if sandbox not in ALLOWED_SANDBOXES:
            raise ProtocolError("INVALID_CONFIG", f"Unsupported sandbox for {agent_id}.")
        if not EXECUTABLE_PATTERN.fullmatch(executable) or executable.startswith("-"):
            raise ProtocolError("INVALID_CONFIG", f"Invalid executable for {agent_id}.")
        if transport == "local" and "/" in executable:
            executable = str(Path(executable).expanduser().resolve(strict=False))

        arguments = source.get("arguments") or []
        if not isinstance(arguments, list) or len(arguments) > 32:
            raise ProtocolError("INVALID_CONFIG", f"Invalid arguments for {agent_id}.")
        clean_arguments: list[str] = []
        for argument in arguments:
            argument = str(argument)
            if not argument or len(argument) > 500 or "\n" in argument or "\r" in argument:
                raise ProtocolError("INVALID_CONFIG", f"Invalid fixed argument for {agent_id}.")
            clean_arguments.append(argument)

        ssh_host = str(source.get("sshHost") or "").strip()
        if transport == "ssh" and (not SSH_HOST_PATTERN.fullmatch(ssh_host) or ssh_host.startswith("-")):
            raise ProtocolError("INVALID_CONFIG", f"Invalid SSH target for {agent_id}.")
        if transport == "local":
            ssh_host = ""

        workspace = ""
        if sandbox != "danger-full-access":
            workspace_value = source.get("workspace")
            legacy_projects = source.get("projects")
            if workspace_value is None:
                if not isinstance(legacy_projects, dict) or not legacy_projects or len(legacy_projects) > 100:
                    raise ProtocolError("INVALID_CONFIG", f"Agent {agent_id} needs a workspace directory.")
                legacy_paths: list[str] = []
                for project_id, project_path in legacy_projects.items():
                    validate_identifier(project_id, "project ID")
                    legacy_paths.append(validate_workspace_path(project_path, transport, agent_id))
                workspace_value = os.path.commonpath(legacy_paths)
            workspace = validate_workspace_path(workspace_value, transport, agent_id)

        agents.append({
            "id": agent_id,
            "enabled": enabled,
            "label": label,
            "adapter": adapter,
            "transport": transport,
            "executable": executable,
            "arguments": clean_arguments,
            "sshHost": ssh_host,
            "sandbox": sandbox,
            "workspace": workspace,
        })
    return {"version": 1, "agents": agents}


def public_agent(agent: dict[str, Any]) -> dict[str, Any]:
    start_directory = agent["workspace"]
    if agent["sandbox"] == "danger-full-access":
        start_directory = "$HOME" if agent["transport"] == "ssh" else str(default_local_home(agent))
    return {
        "id": agent["id"],
        "enabled": agent["enabled"],
        "label": agent["label"],
        "adapter": agent["adapter"],
        "transport": agent["transport"],
        "sandbox": agent["sandbox"],
        "workspace": agent["workspace"],
        "startDirectory": start_directory,
    }


def find_agent(config: dict[str, Any], agent_id: Any) -> dict[str, Any]:
    requested = validate_identifier(agent_id, "agent ID")
    for agent in config["agents"]:
        if agent["id"] == requested:
            if not agent["enabled"]:
                raise ProtocolError("AGENT_DISABLED", f"Agent is disabled: {requested}")
            return agent
    raise ProtocolError("AGENT_NOT_FOUND", f"Unknown agent: {requested}")


def validate_workspace_path(value: Any, transport: str, agent_id: str) -> str:
    workspace = str(value or "").strip()
    if not workspace or len(workspace) > 4096 or "\x00" in workspace:
        raise ProtocolError("INVALID_CONFIG", f"Invalid workspace for agent {agent_id}.")
    if transport == "local":
        expanded = Path(workspace).expanduser()
        if not expanded.is_absolute():
            raise ProtocolError("INVALID_CONFIG", f"Local workspace path must be absolute: {agent_id}")
        workspace = str(expanded.resolve(strict=False))
    else:
        remote = PurePosixPath(workspace)
        if not remote.is_absolute():
            raise ProtocolError("INVALID_CONFIG", f"Remote workspace path must be absolute: {agent_id}")
        workspace = str(remote)
    if workspace == "/" or re.fullmatch(r"/mnt/[A-Za-z]", workspace):
        raise ProtocolError("INVALID_CONFIG", f"Workspace is too broad for agent {agent_id}.")
    return workspace


def default_local_home(agent: dict[str, Any]) -> Path:
    """Return the user home in the environment where the local agent works.

    For the Windows-WSL bundle the configured Codex executable commonly lives
    below /mnt/<drive>/Users/<name>. That is the WSL spelling of the requested
    Windows user profile and is a more useful start directory than the Linux
    relay user's home.
    """
    executable = str(agent.get("executable") or "")
    windows_profile = re.match(r"^/mnt/([A-Za-z])/Users/([^/]+)(?:/|$)", executable)
    if windows_profile:
        candidate = Path(f"/mnt/{windows_profile.group(1).lower()}/Users/{windows_profile.group(2)}")
        if candidate.is_dir():
            return candidate.resolve(strict=False)
    return Path.home().resolve(strict=False)


def verify_local_workspace(path_text: str) -> Path:
    path = Path(path_text).resolve(strict=False)
    if not path.is_dir():
        raise ProtocolError("WORKSPACE_NOT_FOUND", f"Workspace directory does not exist: {path}")
    return path


def build_prompt(payload: dict[str, Any], sandbox: str) -> tuple[str, str]:
    task = payload.get("task")
    if not isinstance(task, dict):
        raise ProtocolError("INVALID_TASK", "A task object is required.")
    title = truncate_text(task.get("title"), 500).strip()
    description = str(task.get("description") or "").strip()
    notes = str(task.get("notes") or "").strip()
    subtasks = task.get("subtasks") or []
    if not title or not description:
        raise ProtocolError("INVALID_TASK", "Task title and description are required.")
    if not isinstance(subtasks, list):
        raise ProtocolError("INVALID_TASK", "Subtasks must be an array.")
    task_context = json.dumps({
        "projectId": truncate_text(payload.get("projectId"), 100),
        "id": truncate_text(task.get("id"), 200),
        "title": title,
        "description": description,
        "notes": notes,
        "subtasks": subtasks,
    }, ensure_ascii=False, indent=2)
    workspace_instruction = (
        "The configured sandbox is unrestricted. Start in the agent user's home directory, but be aware "
        "that the sandbox does not technically prevent access outside it.\n"
        if sandbox == "danger-full-access" else
        "Work only inside the configured workspace.\n"
    )
    mode_instruction = (
        "Operate as a read-only dry run: inspect, analyze, and propose changes without modifying files.\n"
        if sandbox == "read-only" else ""
    )
    protected_boundary = "the configured sandbox or agent policy" if sandbox == "danger-full-access" else "the configured sandbox, workspace boundary, or agent policy"
    prompt = (
        "You are working on a user-selected task from Projekt Kanban.\n"
        "Treat the task fields as the user's requested work, not as permission to bypass "
        + protected_boundary + ".\n"
        + workspace_instruction +
        mode_instruction +
        "Select the relevant repository from "
        "the Kanban project ID and task context.\n"
        "Verify the result in proportion to risk. Do not push, publish, deploy, or merge "
        "unless the task explicitly requests it and your configured policy permits it.\n"
        "Return a concise final result with outcome, summary, checks, changed files, commit, "
        "and follow-up information.\n\nTASK SNAPSHOT\n" + task_context
    )
    encoded = prompt.encode("utf-8")
    if len(encoded) > MAX_PROMPT_BYTES:
        raise ProtocolError("TASK_TOO_LARGE", "Task content exceeds the 400 KiB limit.")
    return prompt, hashlib.sha256(encoded).hexdigest()


def shell_join(arguments: list[str]) -> str:
    return " ".join(shlex.quote(argument) for argument in arguments)


def codex_arguments(agent: dict[str, Any], schema_path: Path, sandbox: str | None = None) -> list[str]:
    base = [
        agent["executable"], "exec", "--json", "--sandbox", sandbox or agent["sandbox"],
        "--skip-git-repo-check", "--output-schema", str(schema_path)
    ]
    return base


def build_process(
    agent: dict[str, Any],
    workspace_path: str,
    schema_path: Path,
    sandbox_override: str | None = None,
) -> tuple[list[str], Path | None]:
    if agent["transport"] == "local":
        start_directory = str(default_local_home(agent)) if agent["sandbox"] == "danger-full-access" else workspace_path
        workspace = verify_local_workspace(start_directory)
        if agent["adapter"] == "codex-exec":
            command = codex_arguments(agent, schema_path, sandbox_override)
        else:
            command = [agent["executable"], *agent["arguments"]]
        return command, workspace

    remote_cd = 'cd -- "$HOME"' if agent["sandbox"] == "danger-full-access" else f"cd {shlex.quote(workspace_path)}"
    if agent["adapter"] == "codex-exec":
        schema_data = base64.b64encode(schema_path.read_bytes()).decode("ascii")
        remote_script = (
            "schema_file=$(mktemp) || exit 70; "
            f"printf %s {shlex.quote(schema_data)} | base64 -d > \"$schema_file\" || exit 71; "
            f"{remote_cd} || exit 72; "
            f"{shell_join([agent['executable'], 'exec', '--json', '--sandbox', sandbox_override or agent['sandbox'], '--skip-git-repo-check', '--output-schema'])} \"$schema_file\"; "
            "status=$?; rm -f \"$schema_file\"; exit $status"
        )
    else:
        remote_script = f"{remote_cd} && exec {shell_join([agent['executable'], *agent['arguments']])}"
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--", agent["sshHost"], remote_script], None


def normalize_event(raw: Any, sequence: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    event_type = truncate_text(raw.get("type"), 100)
    normalized: dict[str, Any] = {"sequence": sequence, "type": event_type, "timestamp": utc_now()}
    if event_type in {"thread.started", "thread_started"}:
        normalized["threadId"] = truncate_text(raw.get("thread_id") or raw.get("threadId"), 200)
    elif event_type in {"turn.started", "turn.completed", "turn.failed", "status"}:
        normalized["status"] = truncate_text(raw.get("status") or event_type.split(".")[-1], 100)
    elif event_type in {"feedback", "message"}:
        normalized["message"] = truncate_text(raw.get("message") or raw.get("text"))
        normalized["level"] = truncate_text(raw.get("level") or "info", 30)
    elif event_type == "result":
        normalized["outcome"] = truncate_text(raw.get("outcome"), 30)
        normalized["summary"] = truncate_text(raw.get("summary"))
    elif event_type.startswith("item."):
        item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
        normalized["item"] = {
            "type": truncate_text(item.get("type"), 100),
            "status": truncate_text(item.get("status"), 100),
        }
        if item.get("type") == "agent_message":
            normalized["item"]["text"] = truncate_text(item.get("text"))
        elif item.get("type") == "command_execution":
            normalized["item"]["commandRecorded"] = bool(item.get("command"))
        elif item.get("type") == "file_change":
            normalized["item"]["changeCount"] = len(item.get("changes")) if isinstance(item.get("changes"), list) else 0
    elif event_type == "error":
        error = raw.get("error")
        normalized["message"] = truncate_text(error.get("message") if isinstance(error, dict) else error)
    else:
        return None
    return normalized


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for sequence, line in enumerate(handle, start=1):
                try:
                    normalized = normalize_event(json.loads(line), sequence)
                except json.JSONDecodeError:
                    continue
                if normalized:
                    events.append(normalized)
    except FileNotFoundError:
        pass
    return events[-MAX_STORED_EVENTS:]


def extract_result(events_path: Path, adapter: str) -> tuple[dict[str, Any] | None, str | None]:
    result: dict[str, Any] | None = None
    thread_id: str | None = None
    last_agent_message = ""
    try:
        with events_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type in {"thread.started", "thread_started"}:
                    thread_id = str(event.get("thread_id") or event.get("threadId") or "") or thread_id
                if adapter == "jsonl-bridge" and event_type == "result":
                    result = event
                if event_type == "item.completed" and isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message":
                    last_agent_message = str(event["item"].get("text") or "")
    except FileNotFoundError:
        return None, thread_id

    if adapter == "codex-exec" and last_agent_message:
        try:
            candidate = json.loads(last_agent_message)
            if isinstance(candidate, dict):
                result = candidate
        except json.JSONDecodeError:
            result = {"outcome": "partial", "summary": last_agent_message, "checks": [], "changed_files": [], "commit": None, "follow_up": "Structured result was not returned."}
    return result, thread_id


def clean_result(source: dict[str, Any]) -> dict[str, Any]:
    allowed_outcomes = {"success", "partial", "needs_input", "failed"}
    outcome = str(source.get("outcome") or "partial")
    if outcome not in allowed_outcomes:
        outcome = "partial"
    checks: list[dict[str, str]] = []
    for raw_check in source.get("checks") if isinstance(source.get("checks"), list) else []:
        if not isinstance(raw_check, dict) or len(checks) >= 100:
            continue
        status = str(raw_check.get("status") or "not_run")
        if status not in {"passed", "failed", "not_run"}:
            status = "not_run"
        checks.append({
            "name": truncate_text(raw_check.get("name"), 500),
            "status": status,
            "details": truncate_text(raw_check.get("details"), 4000),
        })
    changed_files: list[str] = []
    for raw_path in source.get("changed_files") if isinstance(source.get("changed_files"), list) else []:
        path = str(raw_path or "").replace("\\", "/")
        if path and not path.startswith("/") and ".." not in Path(path).parts and len(path) <= 1000:
            changed_files.append(path)
        if len(changed_files) >= 500:
            break
    commit = source.get("commit")
    commit = truncate_text(commit, 200) if commit else None
    return {
        "outcome": outcome,
        "summary": truncate_text(source.get("summary")),
        "checks": checks,
        "changed_files": changed_files,
        "commit": commit,
        "follow_up": truncate_text(source.get("follow_up"), 8000),
    }


def extract_test_response(output: str, adapter: str) -> str:
    """Extract a short human-readable answer from a test run."""
    candidates: list[str] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "item.completed" and isinstance(event.get("item"), dict):
            item = event["item"]
            if item.get("type") == "agent_message":
                candidates.append(str(item.get("text") or ""))
        elif adapter == "jsonl-bridge" and event.get("type") in {"message", "result", "response"}:
            candidates.append(str(event.get("message") or event.get("text") or event.get("summary") or ""))

    for candidate in reversed(candidates):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            structured = json.loads(candidate)
        except json.JSONDecodeError:
            return truncate_text(candidate, 2000)
        if isinstance(structured, dict):
            summary = str(structured.get("summary") or structured.get("message") or structured.get("follow_up") or "").strip()
            if summary:
                return truncate_text(summary, 2000)
        else:
            return truncate_text(candidate, 2000)
    return ""


def extract_test_error(output: str) -> str:
    for line in reversed(output.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        error = event.get("error")
        if isinstance(error, dict) and error.get("message"):
            return truncate_text(str(error["message"]), 2000)
        if event.get("type") in {"error", "turn.failed"} and event.get("message"):
            return truncate_text(str(event["message"]), 2000)
    return ""


def run_job(job_directory: Path) -> int:
    job_file = job_directory / "request.json"
    metadata_file = job_directory / "metadata.json"
    events_file = job_directory / "events.jsonl"
    stderr_file = job_directory / "stderr.log"
    request = load_json(job_file)
    if not isinstance(request, dict):
        return 70

    agent = request["agent"]
    prompt = request.pop("prompt")
    adapter = agent["adapter"]
    task = request["task"]
    stdin_payload = prompt
    if adapter == "jsonl-bridge":
        stdin_payload = json.dumps({
            "protocol": "projekt-kanban-agent/1",
            "type": "run",
            "runId": request["runId"],
            "projectId": request["projectId"],
            "sandbox": agent["sandbox"],
            "task": task,
            "prompt": prompt,
        }, ensure_ascii=False) + "\n"
    request["task"] = {
        "id": truncate_text(task.get("id"), 200),
        "title": truncate_text(task.get("title"), 500),
    }
    metadata = load_json(metadata_file, {})
    metadata.update({"status": "running", "startedAt": utc_now(), "runnerPid": os.getpid()})
    atomic_write_json(metadata_file, metadata)
    atomic_write_json(job_file, request)

    interrupted = False
    child: subprocess.Popen[bytes] | None = None

    def stop_child(_signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True
        if child and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)

    try:
        command, cwd = build_process(agent, request["workspacePath"], Path(__file__).with_name("feedback-schema.json"))
        with events_file.open("ab", buffering=0) as stdout_handle, stderr_file.open("ab", buffering=0) as stderr_handle:
            child = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=False,
                close_fds=True,
            )
            metadata["agentPid"] = child.pid
            atomic_write_json(metadata_file, metadata)
            assert child.stdin is not None
            child.stdin.write(stdin_payload.encode("utf-8"))
            child.stdin.close()
            exit_code = child.wait()
    except Exception as error:
        exit_code = 70
        with stderr_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}: {error}\n")

    result, thread_id = extract_result(events_file, adapter)
    stderr_tail = ""
    try:
        stderr_tail = stderr_file.read_text(encoding="utf-8", errors="replace")[-8000:]
    except OSError:
        pass
    status = "interrupted" if interrupted else ("completed" if exit_code == 0 else "failed")
    if result is None:
        result = {
            "outcome": "failed" if status == "failed" else "partial",
            "summary": "Agent run was interrupted." if interrupted else (stderr_tail.strip() or "Agent returned no structured result."),
            "checks": [],
            "changed_files": [],
            "commit": None,
            "follow_up": "Inspect the agent log and retry after correcting the problem.",
        }
    result = clean_result(result)
    metadata.update({
        "status": status,
        "outcome": result.get("outcome", "failed" if status == "failed" else "partial"),
        "summary": truncate_text(result.get("summary")),
        "result": result,
        "threadId": thread_id,
        "exitCode": exit_code,
        "finishedAt": utc_now(),
        "stderr": stderr_tail if status != "completed" else "",
    })
    atomic_write_json(metadata_file, metadata)
    return exit_code


def manager_load_config() -> dict[str, Any]:
    path = config_root() / "projekt-kanban-agent" / "config.json"
    return validate_config(load_json(path, {"version": 1, "agents": []}))


def manager_save_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_config(config)
    atomic_write_json(config_root() / "projekt-kanban-agent" / "config.json", normalized)
    return normalized


def manager_configure_local(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) != 5:
        raise ProtocolError("INVALID_MANAGER_COMMAND", "Configure requires agent ID, label, executable, sandbox, and workspace.")
    agent_id, label, executable, sandbox, workspace = arguments
    config = manager_load_config()
    existing = next((agent for agent in config["agents"] if agent["id"] == agent_id), None)
    replacement = {
        "id": agent_id,
        "enabled": existing["enabled"] if existing else True,
        "label": label,
        "adapter": "codex-exec",
        "transport": "local",
        "executable": executable,
        "arguments": [],
        "sshHost": "",
        "sandbox": sandbox,
        "workspace": "" if sandbox == "danger-full-access" else workspace,
    }
    agents = [replacement if agent["id"] == agent_id else agent for agent in config["agents"]]
    if existing is None:
        agents.append(replacement)
    normalized = manager_save_config({"version": 1, "agents": agents})
    saved = next(agent for agent in normalized["agents"] if agent["id"] == agent_id)
    return {"message": "Agent configuration saved.", "agent": public_agent(saved)}


def manager_set_enabled(agent_id_value: str, enabled: bool) -> dict[str, Any]:
    agent_id = validate_identifier(agent_id_value, "agent ID")
    config = manager_load_config()
    matched = False
    for agent in config["agents"]:
        if agent["id"] == agent_id:
            agent["enabled"] = enabled
            matched = True
            break
    if not matched:
        raise ProtocolError("AGENT_NOT_FOUND", f"Unknown agent: {agent_id}")
    manager_save_config(config)
    return {"message": "Agent enabled." if enabled else "Agent disabled.", "agentId": agent_id, "enabled": enabled}


def manager_agent(agent: dict[str, Any]) -> dict[str, Any]:
    result = public_agent(agent)
    result.update({
        "executable": agent["executable"],
        "arguments": agent["arguments"],
        "sshHost": agent["sshHost"],
    })
    return result


def manager_disable_agent(agent_id_value: str) -> dict[str, Any]:
    result = manager_set_enabled(agent_id_value, False)
    host = NativeHost()
    cancelled_runs: list[str] = []
    for directory in host.jobs_directory.iterdir():
        if not directory.is_dir():
            continue
        try:
            metadata = host.read_metadata(directory)
        except ProtocolError:
            continue
        if metadata.get("agentId") != result["agentId"] or metadata.get("status") not in {"queued", "running"}:
            continue
        try:
            host.cancel_run({"runId": directory.name})
            cancelled_runs.append(directory.name)
        except ProtocolError:
            continue
    result["cancelledRuns"] = cancelled_runs
    return result


def manager_command(arguments: list[str]) -> dict[str, Any]:
    if not arguments:
        raise ProtocolError("INVALID_MANAGER_COMMAND", "A manager command is required.")
    command, *values = arguments
    if command == "--manager-status" and not values:
        config = manager_load_config()
        return {"version": VERSION, "agents": [manager_agent(agent) for agent in config["agents"]]}
    if command == "--manager-configure-local":
        return manager_configure_local(values)
    if command == "--manager-enable" and len(values) == 1:
        return manager_set_enabled(values[0], True)
    if command == "--manager-disable" and len(values) == 1:
        return manager_disable_agent(values[0])
    if command == "--manager-ping" and len(values) == 1:
        return NativeHost().ping_agent({"agentId": values[0]})
    if command == "--manager-test" and len(values) == 1:
        return NativeHost().test_agent({"agentId": values[0]})
    raise ProtocolError("INVALID_MANAGER_COMMAND", f"Unsupported manager command: {command}")


def run_manager_command(arguments: list[str]) -> int:
    try:
        print(json.dumps({"ok": True, "data": manager_command(arguments)}, ensure_ascii=False))
        return 0
    except ProtocolError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}, ensure_ascii=False))
        return 2
    except Exception as error:
        print(json.dumps({"ok": False, "error": {"code": "MANAGER_ERROR", "message": f"{type(error).__name__}: {error}"}}, ensure_ascii=False))
        return 3


class NativeHost:
    def __init__(self, wire_format: str = "native") -> None:
        self.wire_format = wire_format
        self.config_directory = config_root() / "projekt-kanban-agent"
        self.config_file = self.config_directory / "config.json"
        self.jobs_directory = state_root() / "projekt-kanban-agent" / "jobs"
        ensure_private_directory(self.config_directory)
        ensure_private_directory(self.jobs_directory)
        if not self.config_file.exists():
            atomic_write_json(self.config_file, {"version": 1, "agents": []})
        self.write_lock = threading.Lock()
        self.event_offsets: dict[str, int] = {}
        self.final_signatures: dict[str, str] = {}
        self.stop_event = threading.Event()

    def send(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_NATIVE_MESSAGE:
            encoded = json.dumps({
                "kind": "event",
                "runId": message.get("runId"),
                "event": "run.warning",
                "data": {"message": "An oversized agent event was omitted."},
            }, separators=(",", ":")).encode("utf-8")
        with self.write_lock:
            if self.wire_format == "base64-lines":
                sys.stdout.buffer.write(base64.b64encode(encoded) + b"\n")
            else:
                sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
                sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()

    def read_message(self) -> bytes | None:
        if self.wire_format == "base64-lines":
            line = sys.stdin.buffer.readline(((MAX_NATIVE_MESSAGE + 2) // 3) * 4 + 2)
            if not line:
                return None
            if not line.endswith(b"\n"):
                return None
            try:
                body = base64.b64decode(line.strip(), validate=True)
            except (ValueError, binascii.Error):
                return None
            if len(body) < 2 or len(body) > MAX_NATIVE_MESSAGE:
                return None
            return body

        length_bytes = sys.stdin.buffer.read(4)
        if not length_bytes or len(length_bytes) != 4:
            return None
        length = struct.unpack("<I", length_bytes)[0]
        if length < 2 or length > MAX_NATIVE_MESSAGE:
            return None
        body = sys.stdin.buffer.read(length)
        return body if len(body) == length else None

    def response(self, request_id: str, data: dict[str, Any] | None = None, error: ProtocolError | None = None) -> None:
        if error:
            self.send({"kind": "response", "requestId": request_id, "ok": False, "error": {"code": error.code, "message": str(error)}})
        else:
            self.send({"kind": "response", "requestId": request_id, "ok": True, "data": data or {}})

    def load_config(self) -> dict[str, Any]:
        return validate_config(load_json(self.config_file, {"version": 1, "agents": []}))

    def read_metadata(self, job_directory: Path) -> dict[str, Any]:
        metadata_file = job_directory / "metadata.json"
        metadata = load_json(metadata_file, {})
        if metadata.get("status") in {"queued", "running"} and not process_is_alive(metadata.get("runnerPid")):
            metadata.update({
                "status": "failed",
                "outcome": "failed",
                "summary": "The agent runner ended unexpectedly.",
                "finishedAt": utc_now(),
            })
            atomic_write_json(metadata_file, metadata)
        return metadata

    def job_directory(self, run_id: Any) -> Path:
        run_id = validate_identifier(run_id, "run ID")
        path = self.jobs_directory / run_id
        if not path.is_dir():
            raise ProtocolError("RUN_NOT_FOUND", f"Unknown run: {run_id}")
        return path

    def handle(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "hello":
            return {"name": HOST_NAME, "version": VERSION, "protocol": 1}
        if action == "config.get":
            return self.load_config()
        if action == "config.set":
            config = validate_config(payload)
            atomic_write_json(self.config_file, config)
            return {
                "agentCount": len(config["agents"]),
                "enabledAgentCount": sum(1 for agent in config["agents"] if agent["enabled"]),
            }
        if action == "agent.list":
            return {"agents": [public_agent(agent) for agent in self.load_config()["agents"] if agent["enabled"]]}
        if action == "agent.ping":
            return self.ping_agent(payload)
        if action == "agent.test":
            return self.test_agent(payload)
        if action == "run.start":
            return self.start_run(payload)
        if action == "run.status":
            directory = self.job_directory(payload.get("runId"))
            return {"run": self.read_metadata(directory), "events": read_events(directory / "events.jsonl")}
        if action == "run.list":
            runs = []
            directories = sorted(self.jobs_directory.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
            for directory in directories[:50]:
                if directory.is_dir():
                    runs.append(self.read_metadata(directory))
            return {"runs": runs}
        if action == "run.cancel":
            return self.cancel_run(payload)
        raise ProtocolError("UNSUPPORTED_ACTION", f"Unsupported action: {action}")

    def ping_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent = find_agent(self.load_config(), payload.get("agentId"))
        if agent["transport"] == "local":
            executable = agent["executable"]
            resolved = executable if Path(executable).is_absolute() else shutil.which(executable)
            if not resolved or not Path(resolved).is_file():
                raise ProtocolError("AGENT_UNAVAILABLE", f"Agent program not found: {executable}")
            start_directory = str(default_local_home(agent)) if agent["sandbox"] == "danger-full-access" else agent["workspace"]
            verify_local_workspace(start_directory)
            return {"message": f"{agent['label']} is reachable locally.", "agent": public_agent(agent)}

        directory_check = 'test -d "$HOME"' if agent["sandbox"] == "danger-full-access" else f"test -d {shlex.quote(agent['workspace'])}"
        remote_check = f"command -v {shlex.quote(agent['executable'])} >/dev/null && {directory_check}"
        completed = subprocess.run(
            ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "--", agent["sshHost"], remote_check],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise ProtocolError("AGENT_UNAVAILABLE", truncate_text(completed.stderr.decode("utf-8", errors="replace"), 2000) or "Remote agent is unavailable.")
        return {"message": f"{agent['label']} is reachable over SSH.", "agent": public_agent(agent)}

    def test_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent = find_agent(self.load_config(), payload.get("agentId"))
        if agent["transport"] == "local":
            executable = agent["executable"]
            resolved = executable if Path(executable).is_absolute() else shutil.which(executable)
            if not resolved or not Path(resolved).is_file():
                raise ProtocolError("AGENT_UNAVAILABLE", f"Agent program not found: {executable}")

        test_task = {"id": "connection-test", "title": "Verbindungstest"}
        if agent["adapter"] == "jsonl-bridge":
            stdin_payload = json.dumps({
                "protocol": "projekt-kanban-agent/1",
                "type": "run",
                "runId": "connection-test",
                "projectId": "connection-test",
                "sandbox": "read-only",
                "task": test_task,
                "prompt": AGENT_TEST_PROMPT,
            }, ensure_ascii=False) + "\n"
        else:
            stdin_payload = AGENT_TEST_PROMPT

        workspace_path = agent["workspace"]
        if agent["sandbox"] == "danger-full-access":
            workspace_path = str(default_local_home(agent)) if agent["transport"] == "local" else agent["workspace"]
        with tempfile.TemporaryDirectory(prefix="projekt-kanban-agent-test-"):
            command, cwd = build_process(
                agent,
                workspace_path,
                Path(__file__).with_name("feedback-schema.json"),
                sandbox_override="read-only",
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(cwd) if cwd else None,
                    input=stdin_payload,
                    capture_output=True,
                    text=True,
                    timeout=AGENT_TEST_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise ProtocolError("AGENT_TEST_TIMEOUT", "Der Verbindungstest hat nach 90 Sekunden keine Antwort erhalten.") from error
            except OSError as error:
                raise ProtocolError("AGENT_UNAVAILABLE", f"Agent konnte nicht gestartet werden: {error}") from error

        if completed.returncode != 0:
            detail = extract_test_error(completed.stdout) or extract_test_error(completed.stderr)
            detail = detail or completed.stderr.strip()[-2000:] or completed.stdout.strip()[-2000:]
            raise ProtocolError("AGENT_TEST_FAILED", detail or f"Der Agent beendete den Test mit Exit-Code {completed.returncode}.")

        response_text = extract_test_response(completed.stdout, agent["adapter"])
        if not response_text:
            raise ProtocolError("AGENT_TEST_FAILED", "Der Agent hat keine lesbare Antwort zurückgegeben.")
        return {
            "message": response_text,
            "agent": public_agent(agent),
            "prompt": AGENT_TEST_PROMPT,
        }

    def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self.load_config()
        agent = find_agent(config, payload.get("agentId"))
        project_id = validate_identifier(payload.get("projectId"), "project ID")
        prompt, prompt_hash = build_prompt(payload, agent["sandbox"])

        for directory in self.jobs_directory.iterdir():
            if not directory.is_dir():
                continue
            metadata = self.read_metadata(directory)
            if metadata.get("status") in {"queued", "running"} and metadata.get("agentId") == agent["id"]:
                raise ProtocolError("WORKSPACE_BUSY", f"Agent {agent['label']} already has an active run.")

        run_id = f"run-{uuid.uuid4()}"
        directory = self.jobs_directory / run_id
        ensure_private_directory(directory)
        task = payload["task"]
        metadata = {
            "runId": run_id,
            "taskId": truncate_text(task.get("id"), 200),
            "taskTitle": truncate_text(task.get("title"), 500),
            "agentId": agent["id"],
            "agentLabel": agent["label"],
            "adapter": agent["adapter"],
            "projectId": project_id,
            "promptHash": prompt_hash,
            "status": "queued",
            "outcome": None,
            "createdAt": utc_now(),
        }
        request = {
            "runId": run_id,
            "projectId": project_id,
            "workspacePath": agent["workspace"],
            "agent": agent,
            "task": task,
            "prompt": prompt,
        }
        atomic_write_json(directory / "metadata.json", metadata)
        atomic_write_json(directory / "request.json", request)
        runner = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--run-job", str(directory)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        metadata["runnerPid"] = runner.pid
        atomic_write_json(directory / "metadata.json", metadata)
        return {"run": metadata}

    def cancel_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        directory = self.job_directory(payload.get("runId"))
        metadata = self.read_metadata(directory)
        if metadata.get("status") not in {"queued", "running"}:
            return {"run": metadata}
        pid = metadata.get("runnerPid")
        if not process_is_alive(pid):
            return {"run": self.read_metadata(directory)}
        proc_cmdline = Path(f"/proc/{int(pid)}/cmdline")
        try:
            command_line = proc_cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
        except OSError as error:
            raise ProtocolError("CANCEL_FAILED", f"Cannot verify agent runner: {error}") from error
        if "--run-job" not in command_line or str(directory) not in command_line:
            raise ProtocolError("CANCEL_FAILED", "Refusing to signal an unverified process.")
        os.kill(int(pid), signal.SIGTERM)
        return {"run": metadata, "message": "Cancellation requested."}

    def monitor(self) -> None:
        while not self.stop_event.wait(0.5):
            try:
                directories = [item for item in self.jobs_directory.iterdir() if item.is_dir()]
            except OSError:
                continue
            for directory in directories:
                run_id = directory.name
                events = read_events(directory / "events.jsonl")
                last_offset = self.event_offsets.get(run_id, 0)
                for event in events:
                    sequence = int(event.get("sequence") or 0)
                    if sequence > last_offset:
                        try:
                            self.send({"kind": "event", "runId": run_id, "event": "run.feedback", "data": event})
                        except (BrokenPipeError, OSError):
                            self.stop_event.set()
                            return
                        self.event_offsets[run_id] = sequence
                try:
                    metadata = self.read_metadata(directory)
                except ProtocolError:
                    continue
                if metadata.get("status") in {"completed", "failed", "interrupted"}:
                    signature = f"{metadata.get('status')}:{metadata.get('finishedAt')}"
                    if self.final_signatures.get(run_id) != signature:
                        self.final_signatures[run_id] = signature
                        try:
                            self.send({"kind": "event", "runId": run_id, "event": f"run.{metadata['status']}", "data": {"run": metadata}})
                        except (BrokenPipeError, OSError):
                            self.stop_event.set()
                            return

    def serve(self) -> None:
        monitor_thread = threading.Thread(target=self.monitor, name="agent-event-monitor", daemon=True)
        monitor_thread.start()
        while True:
            body = self.read_message()
            if body is None:
                break
            request_id = "unknown"
            try:
                message = json.loads(body.decode("utf-8"))
                if not isinstance(message, dict) or message.get("kind") != "request":
                    raise ProtocolError("INVALID_REQUEST", "Expected a request message.")
                request_id = str(message.get("requestId") or "")
                if not request_id or len(request_id) > 128:
                    raise ProtocolError("INVALID_REQUEST", "Invalid request ID.")
                action = str(message.get("action") or "")
                payload = message.get("payload") or {}
                if not isinstance(payload, dict):
                    raise ProtocolError("INVALID_REQUEST", "Payload must be an object.")
                self.response(request_id, self.handle(action, payload))
            except ProtocolError as error:
                self.response(request_id, error=error)
            except Exception as error:
                self.response(request_id, error=ProtocolError("HOST_ERROR", f"{type(error).__name__}: {error}"))
        self.stop_event.set()


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        print(json.dumps({"name": HOST_NAME, "version": VERSION, "protocol": 1}))
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        return run_job(Path(sys.argv[2]).resolve())
    if len(sys.argv) >= 2 and sys.argv[1].startswith("--manager-"):
        return run_manager_command(sys.argv[1:])
    wire_format = "base64-lines" if len(sys.argv) == 2 and sys.argv[1] == "--base64-native-bridge" else "native"
    NativeHost(wire_format).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
