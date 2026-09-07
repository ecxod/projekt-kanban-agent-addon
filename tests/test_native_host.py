from __future__ import annotations

import importlib.util
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
    def __init__(self, environment: dict[str, str]):
        self.process = subprocess.Popen(
            [sys.executable, str(HOST_PATH)],
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
        self.process.stdin.write(struct.pack("<I", len(message)) + message)
        self.process.stdin.flush()
        while True:
            response = self.read()
            if response.get("kind") == "response" and response.get("requestId") == request_id:
                return response

    def read(self) -> dict:
        assert self.process.stdout is not None
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
                "label": "Fake Agent",
                "adapter": "jsonl-bridge",
                "transport": "local",
                "executable": str(FAKE_AGENT),
                "arguments": [],
                "sshHost": "",
                "sandbox": "workspace-write",
                "projects": {"test-project": str(self.project)},
            }],
        }

    def test_rejects_secret_and_dangerous_configuration_fields(self) -> None:
        config = self.config()
        config["agents"][0]["apiKey"] = "secret"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)
        config = self.config()
        config["agents"][0]["sandbox"] = "danger-full-access"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)
        config = self.config()
        config["agents"][0]["transport"] = "ssh"
        config["agents"][0]["sshHost"] = "-oProxyCommand=bad"
        with self.assertRaises(host_module.ProtocolError):
            host_module.validate_config(config)

    def test_prompt_has_boundary_and_snapshot(self) -> None:
        prompt, digest = host_module.build_prompt({"task": {
            "id": "17",
            "title": "Test title",
            "description": "Test description",
            "notes": "Test notes",
            "subtasks": [{"title": "Child"}],
        }})
        self.assertIn("configured sandbox", prompt)
        self.assertIn("Test description", prompt)
        self.assertEqual(len(digest), 64)

    def test_end_to_end_jsonl_bridge_feedback(self) -> None:
        client = NativeClient(self.environment)
        try:
            hello = client.request("hello")
            self.assertTrue(hello["ok"])
            saved = client.request("config.set", self.config())
            self.assertEqual(saved["data"]["agentCount"], 1)
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


if __name__ == "__main__":
    unittest.main()
