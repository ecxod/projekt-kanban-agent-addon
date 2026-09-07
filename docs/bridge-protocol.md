# Projekt Kanban Agent Bridge Protocol 1

The `jsonl-bridge` adapter allows any user-owned agent to work with the Firefox
connector. The native host starts the configured executable without a shell,
sets its working directory to the configured repository, writes one JSON object
to standard input, and reads JSON Lines from standard output.

The bridge must never read credentials from the input object. Provider login and
secret storage are the bridge's responsibility.

## Input

```json
{
  "protocol": "projekt-kanban-agent/1",
  "type": "run",
  "runId": "run-uuid",
  "projectId": "website",
  "sandbox": "workspace-write",
  "task": {
    "id": "task-17",
    "title": "Add export",
    "description": "Add a CSV export.",
    "notes": "Keep the current JSON export.",
    "subtasks": []
  },
  "prompt": "Complete prompt prepared by the native host"
}
```

## Output events

Write one JSON object per line and flush after each line. Unknown event types are
ignored. Do not put protocol messages on standard error.

```json
{"type":"status","status":"running"}
{"type":"feedback","level":"info","message":"Inspecting the export module."}
{"type":"result","outcome":"success","summary":"CSV export added.","checks":[{"name":"unit tests","status":"passed","details":"18 tests passed"}],"changed_files":["src/export.js"],"commit":null,"follow_up":"Review and commit the change."}
```

`outcome` must be one of `success`, `partial`, `needs_input`, or `failed`.
Check statuses are `passed`, `failed`, or `not_run`. Paths returned in
`changed_files` should be repository-relative. The process exit code must be
zero for a technically successful bridge execution.

This protocol is intentionally provider-neutral. A Gemini, local-model, or
other coding-agent wrapper only needs to translate this input and its provider's
events into these JSONL messages.
