# Security

Please report vulnerabilities privately to the repository owner rather than
opening a public issue containing secrets or exploit details.

## Boundaries

The extension is a transport between one fixed website origin and a user-owned
Native Messaging host. It does not make task text trustworthy. The native host:

- resolves logical IDs through local configuration;
- does not accept filesystem paths or commands from the webpage;
- accepts `danger-full-access` only from the user-owned configuration and shows
  an additional add-on-controlled warning and checkbox before every such run;
- invokes configured programs without a local shell;
- uses `BatchMode` for SSH so passwords are never requested or captured;
- keeps configuration and job state in user-private directories.

The SSH transport necessarily uses a remote shell to start the exact executable
and fixed arguments from local configuration. All values are shell-quoted and
cannot be supplied by a task request.

Users should choose the sandbox deliberately. `workspace-write` confines writes
to the configured workspace, `read-only` is intended for analysis, and
`danger-full-access` grants the agent the same filesystem reach as its operating
system user. Provider credentials belong only to the selected agent environment.
