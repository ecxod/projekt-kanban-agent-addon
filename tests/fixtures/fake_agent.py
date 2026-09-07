#!/usr/bin/env python3
import json
import sys
import time


request = json.loads(sys.stdin.readline())
print(json.dumps({"type": "status", "status": "running"}), flush=True)
print(json.dumps({"type": "feedback", "level": "info", "message": f"Working on {request['task']['title']}"}), flush=True)
time.sleep(0.05)
print(json.dumps({
    "type": "result",
    "outcome": "success",
    "summary": "Fake agent completed the task.",
    "checks": [{"name": "fake check", "status": "passed", "details": "ok"}],
    "changed_files": ["README.md"],
    "commit": None,
    "follow_up": "Review the result."
}), flush=True)
