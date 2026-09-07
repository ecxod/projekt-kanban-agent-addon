from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELAY_SOURCE = ROOT / "native-host-windows-wsl" / "wsl-relay.c"
FAKE_WSL_SOURCE = ROOT / "tests" / "fixtures" / "fake_wsl.c"


@unittest.skipUnless(
    shutil.which("x86_64-w64-mingw32-gcc") and shutil.which("wine") and shutil.which("winepath"),
    "MinGW and Wine are required for the Windows relay integration test.",
)
class WindowsRelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.relay = self.directory / "projekt-kanban-agent-wsl.exe"
        self.fake_wsl = self.directory / "fake-wsl.exe"
        common = [
            "x86_64-w64-mingw32-gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-static", "-s", "-Wl,--no-insert-timestamp",
        ]
        subprocess.run([*common, "-municode", "-o", str(self.relay), str(RELAY_SOURCE)], check=True)
        subprocess.run([*common, "-o", str(self.fake_wsl), str(FAKE_WSL_SOURCE)], check=True)
        wine_environment = os.environ.copy()
        wine_environment["WINEDEBUG"] = "-all"
        self.environment = wine_environment
        windows_fake_wsl = subprocess.run(
            ["winepath", "-w", str(self.fake_wsl)],
            check=True,
            capture_output=True,
            text=True,
            env=self.environment,
        ).stdout.strip()
        (self.directory / "relay-config.txt").write_text(
            f"{windows_fake_wsl}\r\nDevuan\r\n/fake/kanban_agent_host.py\r\n",
            encoding="utf-8",
            newline="",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_relay_self_test_crosses_windows_process_boundary(self) -> None:
        completed = subprocess.run(
            ["wine", str(self.relay), "--self-test"],
            env=self.environment,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))

    def test_firefox_binary_frame_round_trip(self) -> None:
        process = subprocess.Popen(
            ["wine", str(self.relay)],
            env=self.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        request = json.dumps({
            "kind": "request",
            "requestId": "relay-self-test",
            "action": "hello",
            "payload": {},
        }, separators=(",", ":")).encode()
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(struct.pack("<I", len(request)) + request)
        process.stdin.flush()
        header = process.stdout.read(4)
        self.assertEqual(len(header), 4)
        length = struct.unpack("<I", header)[0]
        response = json.loads(process.stdout.read(length))
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["version"], "0.1.3")
        process.stdin.close()
        process.wait(timeout=20)
        process.stdout.close()
        assert process.stderr is not None
        process.stderr.close()


if __name__ == "__main__":
    unittest.main()
