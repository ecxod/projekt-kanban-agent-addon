[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9._ -]*$')]
    [string]$Distribution = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HostName = 'de.projekt_kanban.agent'
$ExtensionId = 'projekt-kanban-agent@ecxod.de'
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDirectory = Split-Path -Parent $ScriptDirectory
$SourceHost = Join-Path $PackageDirectory 'native-host\kanban_agent_host.py'
$SourceSchema = Join-Path $PackageDirectory 'native-host\feedback-schema.json'
$WslCommand = Get-Command 'wsl.exe' -ErrorAction Stop

if (-not (Test-Path -LiteralPath $SourceHost -PathType Leaf) -or
    -not (Test-Path -LiteralPath $SourceSchema -PathType Leaf)) {
    throw 'The native-host files are missing. Extract the complete Windows-WSL release ZIP first.'
}

$InstallDirectory = Join-Path $env:LOCALAPPDATA 'ProjektKanbanAgent'
$InstalledHost = Join-Path $InstallDirectory 'kanban_agent_host.py'
$InstalledSchema = Join-Path $InstallDirectory 'feedback-schema.json'
$BatchPath = Join-Path $InstallDirectory 'projekt-kanban-agent-wsl.bat'
$ManifestPath = Join-Path $InstallDirectory "$HostName.json"
$RegistryPath = "HKCU:\Software\Mozilla\NativeMessagingHosts\$HostName"

New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
Copy-Item -LiteralPath $SourceHost -Destination $InstalledHost -Force
Copy-Item -LiteralPath $SourceSchema -Destination $InstalledSchema -Force

$DistributionArguments = @()
if ($Distribution) {
    $DistributionArguments = @('--distribution', $Distribution)
}

$WslPathOutput = @(& $WslCommand.Path @DistributionArguments --exec wslpath -a -u $InstalledHost)
if ($LASTEXITCODE -ne 0 -or $WslPathOutput.Count -eq 0) {
    throw 'WSL could not translate the installed host path. Check the selected distribution.'
}
$WslHostPath = [string]$WslPathOutput[-1]
$WslHostPath = $WslHostPath.Trim()
if (-not $WslHostPath.StartsWith('/')) {
    throw "WSL returned an invalid host path: $WslHostPath"
}

$SelfTestOutput = @(& $WslCommand.Path @DistributionArguments --exec python3 $WslHostPath --self-test)
if ($LASTEXITCODE -ne 0 -or $SelfTestOutput.Count -eq 0) {
    throw 'The native host self-test failed in WSL. Ensure python3 is installed in the selected distribution.'
}
$SelfTest = ($SelfTestOutput -join "`n") | ConvertFrom-Json
if ($SelfTest.name -ne $HostName -or $SelfTest.protocol -ne 1) {
    throw 'The WSL native host returned an unexpected self-test response.'
}

$DistributionPart = ''
if ($Distribution) {
    $DistributionPart = "--distribution `"$Distribution`" "
}
$BatchContent = "@echo off`r`n`"$($WslCommand.Path)`" $DistributionPart--exec python3 `"$WslHostPath`"`r`n"
[System.IO.File]::WriteAllText($BatchPath, $BatchContent, [System.Text.UTF8Encoding]::new($false))

$Manifest = [ordered]@{
    name = $HostName
    description = 'Connect Windows Firefox to user-owned coding agents in WSL'
    path = $BatchPath
    type = 'stdio'
    allowed_extensions = @($ExtensionId)
}
$ManifestJson = $Manifest | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($ManifestPath, $ManifestJson + "`r`n", [System.Text.UTF8Encoding]::new($false))

New-Item -Path $RegistryPath -Force | Out-Null
Set-Item -Path $RegistryPath -Value $ManifestPath

Write-Host "Windows-WSL Native Host installed: $BatchPath"
Write-Host "Firefox manifest registered: $ManifestPath"
Write-Host "WSL host verified: $WslHostPath (version $($SelfTest.version))"
Write-Host 'Restart Firefox, then open the add-on settings.'
