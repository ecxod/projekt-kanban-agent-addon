# Projekt Kanban page protocol

The content script exposes a narrowly scoped `window.postMessage` protocol only
on `https://projekt-kanban.de`. Protocol messages never contain agent
credentials, executable paths, SSH destinations, or user-configured workspace paths.

## Detect the add-on

```js
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.data?.source !== "projekt-kanban-agent-addon") return;
  if (event.data.type === "ready") console.log(event.data.capabilities);
});
```

## Request configured agents

```js
const requestId = crypto.randomUUID();
window.postMessage({
  source: "projekt-kanban",
  version: 1,
  type: "request",
  requestId,
  action: "agent.list",
  payload: {}
}, location.origin);
```

## Start a run

Starting a run always opens an add-on-controlled confirmation dialog. Only after
the user confirms are the task fields sent to the native host. An agent configured
with `danger-full-access` additionally requires a warning checkbox for every run.

```js
window.postMessage({
  source: "projekt-kanban",
  version: 1,
  type: "request",
  requestId: crypto.randomUUID(),
  action: "run.start",
  payload: {
    agentId: "local-codex",
    projectId: "projekt-kanban",
    task: {
      id: "task-42",
      title: "Add keyboard navigation",
      description: "Make the task dialog keyboard accessible.",
      notes: "Do not change the visual design.",
      subtasks: []
    }
  }
}, location.origin);
```

## Responses and feedback

Responses use the original `requestId`. Agent progress is delivered separately
and can be stored in the task's `agentRuns` array. Consumers should deduplicate
feedback by `runId` plus `data.sequence`.

```json
{
  "source": "projekt-kanban-agent-addon",
  "version": 1,
  "type": "event",
  "runId": "run-uuid",
  "event": "run.feedback",
  "data": {
    "sequence": 3,
    "type": "feedback",
    "message": "Running browser tests."
  }
}
```

Supported actions are `agent.list`, `agent.ping`, `run.start`, `run.status`,
`run.list`, and `run.cancel`.
