# Security

Please report vulnerabilities privately to the repository owner rather than
opening a public issue containing secrets or exploit details.

## Boundaries

The extension is a transport between one fixed website origin and a user-owned
Native Messaging host. It does not make task text trustworthy. The native host:

- resolves logical IDs through local configuration;
- does not accept filesystem paths or commands from the webpage;
- rejects `danger-full-access`;
- invokes configured programs without a local shell;
- uses `BatchMode` for SSH so passwords are never requested or captured;
- keeps configuration and job state in user-private directories.

The SSH transport necessarily uses a remote shell to start the exact executable
and fixed arguments from local configuration. All values are shell-quoted and
cannot be supplied by a task request.

Users should use dedicated repository mappings, least-privilege sandbox settings,
and provider credentials belonging only to the selected agent environment.
