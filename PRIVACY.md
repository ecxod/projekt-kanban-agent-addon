# Privacy policy

Last updated: 2026-09-07

Projekt Kanban Agent Connector transmits only the task content that the user
explicitly confirms to a coding agent configured by that user. This may include
the task title, description, notes, subtasks, logical project ID, and a temporary
run ID.

The data is sent from Firefox to a Native Messaging application installed on the
same computer. If the user configured SSH transport, that native application
then sends the task to the user's chosen SSH destination. The operator of
`projekt-kanban.de` does not receive this agent communication through the
extension.

The extension does not collect telemetry, browsing history, advertising data,
cookies, or analytics. It does not sell or share data. It does not store provider
API keys, provider passwords, or SSH passwords.

Agent configuration and run history are stored locally by the Native Messaging
host. A provider invoked by the user may process data according to that
provider's own terms and privacy policy. Users are responsible for choosing and
configuring their agent.

Firefox desktop 140 and later also presents the declared `websiteContent`
transmission during installation. Firefox 128 through 139 does not have that
built-in consent screen; on those versions, the add-on-controlled confirmation
dialog appears before every task transmission. Cancelling it prevents the task
content from leaving the page.

Removing the Native Messaging host does not automatically remove local settings
or run history. They can be deleted manually from the XDG configuration and
state directories.
