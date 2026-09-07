[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HostName = 'de.projekt_kanban.agent'
$InstallDirectory = Join-Path $env:LOCALAPPDATA 'ProjektKanbanAgent'
$RegistryPath = "HKCU:\Software\Mozilla\NativeMessagingHosts\$HostName"

if (Test-Path -LiteralPath $RegistryPath) {
    Remove-Item -LiteralPath $RegistryPath -Force
}

foreach ($Name in @(
    'kanban_agent_host.py',
    'feedback-schema.json',
    'projekt-kanban-agent-wsl.bat',
    'projekt-kanban-agent-wsl.exe',
    'relay-config.txt',
    'relay.log',
    "$HostName.json"
)) {
    $Path = Join-Path $InstallDirectory $Name
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Remove-Item -LiteralPath $Path -Force
    }
}

if (Test-Path -LiteralPath $InstallDirectory -PathType Container) {
    $Remaining = @(Get-ChildItem -LiteralPath $InstallDirectory -Force)
    if ($Remaining.Count -eq 0) {
        Remove-Item -LiteralPath $InstallDirectory
    }
}

Write-Host 'Projekt Kanban Windows-WSL Native Host removed.'
Write-Host 'Agent settings and run history inside WSL were retained.'
