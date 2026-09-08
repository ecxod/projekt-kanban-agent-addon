from __future__ import annotations

import importlib.util
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST_PATH = ROOT / "native-host" / "kanban_agent_host.py"
FAKE_AGENT = ROOT / "tests" / "fixtures" / "fake_agent.py"
SPEC = importlib.util.spec_from_file_location("kanban_agent_host", HOST_PATH)
assert SPEC and SPEC.loader
host_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host_module)


class NativeClient:
    def __init__(self, environment: dict[str, str], base64_transport: bool = False):
        self.base64_transport = base64_transport
        self.process = subprocess.Popen(
            [sys.executable, str(HOST_PATH), *(["--base64-native-bridge"] if base64_transport else [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        self.counter = 0

    def request(self, action: str, payload: dict | None = None) -> dict:
        self.counter += 1
        request_id = f"test-{self.counter}"
        message = json.dumps({
            "kind": "request",
            "requestId": request_id,
            "action": action,
            "payload": payload or {},
        }).encode()
        assert self.process.stdin is not None
        if self.base64_transport:
            self.process.stdin.write(base64.b64encode(message) + b"\n")
        else:
            self.process.stdin.write(struct.pack("<I", len(message)) + message)
        self.process.stdin.flush()
        while True:
            response = self.read()
            if response.get("kind") == "response" and response.get("requestId") == request_id:
                return response

    def read(self) -> dict:
        assert self.process.stdout is not None
        if self.base64_transport:
            line = self.process.stdout.readline()
            if not line:
                stderr = self.process.stderr.read().decode(errors="replace") if self.process.stderr else ""
                raise AssertionError(f"native host ended unexpectedly: {stderr}")
            return json.loads(base64.b64decode(line.strip(), validate=True))
        header = self.process.stdout.read(4)
        if len(header) != 4:
            stderr = self.process.stderr.read().decode(errors="replace") if self.process.stderr else ""
            raise AssertionError(f"native host ended unexpectedly: {stderr}")
        length = struct.unpack("<I", header)[0]
        body = self.process.stdout.read(length)
        return json.loads(body)

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()


class HostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.project = self.base / "repo"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        FAKE_AGENT.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment["XDG_CONFIG_HOME"] = str(self.base / "config")
        self.environment["XDG_STATE_HOME"] = str(self.base / "state")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def config(self) -> dict:
        return {
            "version": 1,
            "agents": [{
                "id": "fake-agent",
                "enabled": True,
                "label": "Fake Agent",
                "adapter": "jsonl-bridge",
                "transport": "local",
                "executable": str(FAKE_AGENT),
                "arguments": [],
                "sshHost": "",
                "sandbox": "workspace-write",
                "workspace": str(self.base),
            }],
        }

    def test_self_test_reports_native_host_identity(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HOST_PATH), "--self-test"],
            check=True,
            capture_output=True,
            text=True,
        )
        response = json.loads(completed.stdout)
        self.assertEqual(response, {
            "name": "de.projekt_kanban.agent",
            "version": "0.1.8.3",
            "protocol": 1,
        })

    def test_rejects_secret_and_invalid_configuration_fields(self) -> None:
        config = self.config()
        config["agents"][0]["apiKey"] = "secret"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)
        config = self.config()
        config["agents"][0]["transport"] = "ssh"
        config["agents"][0]["sshHost"] = "-oProxyCommand=bad"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)
        config = self.config()
        config["agents"][0]["enabled"] = "false"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)

    def test_prompt_has_boundary_and_snapshot(self) -> None:
        prompt, digest = host_module.build_prompt({"task": {
            "id": "17",
            "title": "Test title",
            "description": "Test description",
            "notes": "Test notes",
            "subtasks": [{"title": "Child"}],
        }}, "workspace-write")
        self.assertIn("configured sandbox", prompt)
        self.assertIn("Test description", prompt)
        self.assertEqual(len(digest), 64)

    def test_unrestricted_sandbox_is_preserved_and_warned_in_prompt(self) -> None:
        config = self.config()
        config["agents"][0]["sandbox"] = "danger-full-access"
        config["agents"][0].pop("workspace")
        normalized = host_module.validate_config(config)
        self.assertEqual(normalized["agents"][0]["sandbox"], "danger-full-access")
        self.assertEqual(normalized["agents"][0]["workspace"], "")
        self.assertEqual(
            host_module.public_agent(normalized["agents"][0])["startDirectory"],
            str(host_module.default_local_home(normalized["agents"][0])),
        )
        prompt, _digest = host_module.build_prompt({"task": {
            "id": "18",
            "title": "Unrestricted test",
            "description": "Inspect another directory.",
            "subtasks": [],
        }}, "danger-full-access")
        self.assertIn("sandbox is unrestricted", prompt)
        self.assertNotIn("Work only inside", prompt)

    def test_legacy_project_mapping_migrates_to_workspace(self) -> None:
        config = self.config()
        config["agents"][0].pop("workspace")
        config["agents"][0]["projects"] = {"test-project": str(self.project)}
        normalized = host_module.validate_config(config)
        self.assertEqual(normalized["agents"][0]["workspace"], str(self.project))
        self.assertNotIn("projects", normalized["agents"][0])

    def test_end_to_end_jsonl_bridge_feedback(self) -> None:
        client = NativeClient(self.environment)
        try:
            hello = client.request("hello")
            self.assertTrue(hello["ok"])
            saved = client.request("config.set", self.config())
            self.assertEqual(saved["data"]["agentCount"], 1)
            self.assertEqual(saved["data"]["enabledAgentCount"], 1)
            agents = client.request("agent.list")
            self.assertEqual(agents["data"]["agents"][0]["adapter"], "jsonl-bridge")
            started = client.request("run.start", {
                "agentId": "fake-agent",
                "projectId": "test-project",
                "task": {
                    "id": "task-1",
                    "title": "Exercise fake bridge",
                    "description": "Return deterministic feedback.",
                    "notes": "",
                    "subtasks": [],
                },
            })
            self.assertTrue(started["ok"])
            run_id = started["data"]["run"]["runId"]
            deadline = time.monotonic() + 8
            status = None
            while time.monotonic() < deadline:
                response = client.request("run.status", {"runId": run_id})
                self.assertTrue(response["ok"])
                status = response["data"]
                if status["run"]["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            self.assertIsNotNone(status)
            self.assertEqual(status["run"]["status"], "completed")
            self.assertEqual(status["run"]["outcome"], "success")
            self.assertEqual(status["run"]["result"]["summary"], "Fake agent completed the task.")
            self.assertTrue(any(event["type"] == "feedback" for event in status["events"]))
            self.assertEqual(len(status["run"]["promptHash"]), 64)
            request_state = json.loads((self.base / "state" / "projekt-kanban-agent" / "jobs" / run_id / "request.json").read_text())
            self.assertNotIn("prompt", request_state)
            self.assertNotIn("description", request_state["task"])
        finally:
            client.close()

    def test_connection_test_sends_prompt_and_returns_agent_response(self) -> None:
        host_module.manager_save_config(self.config())
        result = host_module.NativeHost().test_agent({"agentId": "fake-agent"})
        self.assertEqual(result["prompt"], host_module.AGENT_TEST_PROMPT)
        self.assertEqual(result["message"], "Fake agent completed the task.")

    def test_disabled_agent_is_preserved_but_unavailable(self) -> None:
        client = NativeClient(self.environment)
        try:
            config = self.config()
            config["agents"][0]["enabled"] = False
            saved = client.request("config.set", config)
            self.assertEqual(saved["data"], {"agentCount": 1, "enabledAgentCount": 0})
            stored = client.request("config.get")
            self.assertFalse(stored["data"]["agents"][0]["enabled"])
            listed = client.request("agent.list")
            self.assertEqual(listed["data"]["agents"], [])
            ping = client.request("agent.ping", {"agentId": "fake-agent"})
            self.assertFalse(ping["ok"])
            self.assertEqual(ping["error"]["code"], "AGENT_DISABLED")
        finally:
            client.close()

    def test_base64_transport_for_windows_relay(self) -> None:
        client = NativeClient(self.environment, base64_transport=True)
        try:
            response = client.request("hello")
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["version"], "0.1.8.3")
        finally:
            client.close()

    def test_manager_cli_configures_and_toggles_agent(self) -> None:
        configured = subprocess.run(
            [
                sys.executable,
                str(HOST_PATH),
                "--manager-configure-local",
                "managed-codex",
                "Managed Codex",
                str(FAKE_AGENT),
                "workspace-write",
                str(self.base),
            ],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)
        self.assertTrue(json.loads(configured.stdout)["ok"])

        disabled = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-disable", "managed-codex"],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(disabled.returncode, 0, disabled.stdout + disabled.stderr)
        disabled_data = json.loads(disabled.stdout)["data"]
        self.assertFalse(disabled_data["enabled"])
        self.assertEqual(disabled_data["cancelledRuns"], [])

        status = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-status"],
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
        )
        agents = json.loads(status.stdout)["data"]["agents"]
        self.assertEqual([(agent["id"], agent["enabled"]) for agent in agents], [("managed-codex", False)])

        enabled = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-enable", "managed-codex"],
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertTrue(json.loads(enabled.stdout)["data"]["enabled"])

    def test_manager_configures_tests_and_disables_local_agent(self) -> None:
        configure = subprocess.run(
            [
                sys.executable, str(HOST_PATH), "--manager-configure-local",
                "managed-codex", "Managed Codex", str(FAKE_AGENT),
                "workspace-write", str(self.base),
            ],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(configure.returncode, 0, configure.stdout + configure.stderr)
        configured = json.loads(configure.stdout)
        self.assertTrue(configured["ok"])
        self.assertEqual(configured["data"]["agent"]["id"], "managed-codex")

        ping = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-ping", "managed-codex"],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(ping.returncode, 0, ping.stdout + ping.stderr)
        self.assertTrue(json.loads(ping.stdout)["ok"])

        disabled = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-disable", "managed-codex"],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(disabled.returncode, 0, disabled.stdout + disabled.stderr)
        self.assertFalse(json.loads(disabled.stdout)["data"]["enabled"])

        status = subprocess.run(
            [sys.executable, str(HOST_PATH), "--manager-status"],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        saved_agent = json.loads(status.stdout)["data"]["agents"][0]
        self.assertFalse(saved_agent["enabled"])
        self.assertEqual(saved_agent["workspace"], str(self.base))


if __name__ == "__main__":
    unittest.main()
