[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9._ -]*$')]
    [string]$Distribution = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HostName = 'de.projekt_kanban.agent'
$ExpectedVersion = '0.1.8.3'
$ExtensionId = 'projekt-kanban-agent@ecxod.de'
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDirectory = Split-Path -Parent $ScriptDirectory
$SourceHost = Join-Path $PackageDirectory 'native-host\kanban_agent_host.py'
$SourceSchema = Join-Path $PackageDirectory 'native-host\feedback-schema.json'
$SourceRelay = Join-Path $ScriptDirectory 'projekt-kanban-agent-wsl.exe'
$WslCommand = Get-Command 'wsl.exe' -ErrorAction Stop

if (-not (Test-Path -LiteralPath $SourceHost -PathType Leaf) -or
    -not (Test-Path -LiteralPath $SourceSchema -PathType Leaf) -or
    -not (Test-Path -LiteralPath $SourceRelay -PathType Leaf)) {
    throw 'The native-host or Windows relay files are missing. Extract the complete Windows-WSL release ZIP first.'
}

$InstallDirectory = Join-Path $env:LOCALAPPDATA 'ProjektKanbanAgent'
$InstalledHost = Join-Path $InstallDirectory 'kanban_agent_host.py'
$InstalledSchema = Join-Path $InstallDirectory 'feedback-schema.json'
$RelayPath = Join-Path $InstallDirectory 'projekt-kanban-agent-wsl.exe'
$RelayConfigPath = Join-Path $InstallDirectory 'relay-config.txt'
$LegacyBatchPath = Join-Path $InstallDirectory 'projekt-kanban-agent-wsl.bat'
$ManifestPath = Join-Path $InstallDirectory "$HostName.json"
$RegistryPath = "HKCU:\Software\Mozilla\NativeMessagingHosts\$HostName"

if (Get-Process -Name 'projekt-kanban-agent-wsl' -ErrorAction SilentlyContinue) {
    throw 'The Projekt Kanban relay is still running. Close Firefox completely, then run the installer again.'
}

New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
Copy-Item -LiteralPath $SourceHost -Destination $InstalledHost -Force
Copy-Item -LiteralPath $SourceSchema -Destination $InstalledSchema -Force
Copy-Item -LiteralPath $SourceRelay -Destination $RelayPath -Force

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
if ($SelfTest.version -ne $ExpectedVersion) {
    throw "The installed WSL native host has version $($SelfTest.version), but version $ExpectedVersion is required. Close Firefox and run this installer again."
}

$RelayConfig = "$($WslCommand.Path)`r`n$Distribution`r`n$WslHostPath`r`n"
[System.IO.File]::WriteAllText($RelayConfigPath, $RelayConfig, [System.Text.UTF8Encoding]::new($false))

$RelayOutput = @(& $RelayPath --self-test 2>&1)
$RelayExitCode = $LASTEXITCODE
if ($RelayExitCode -ne 0) {
    $RelayLogPath = Join-Path $InstallDirectory 'relay.log'
    $RelayDetails = ($RelayOutput -join ' ').Trim()
    if (-not $RelayDetails -and (Test-Path -LiteralPath $RelayLogPath -PathType Leaf)) {
        $RelayDetails = (@(Get-Content -LiteralPath $RelayLogPath -Tail 8) -join ' ').Trim()
    }
    if (-not $RelayDetails) { $RelayDetails = 'No diagnostic text was produced.' }
    throw "The Windows-to-WSL relay self-test failed with exit code $RelayExitCode. $RelayDetails"
}

$Manifest = [ordered]@{
    name = $HostName
    description = 'Connect Windows Firefox to user-owned coding agents in WSL'
    path = $RelayPath
    type = 'stdio'
    allowed_extensions = @($ExtensionId)
}
$ManifestJson = $Manifest | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($ManifestPath, $ManifestJson + "`r`n", [System.Text.UTF8Encoding]::new($false))

New-Item -Path $RegistryPath -Force | Out-Null
Set-Item -Path $RegistryPath -Value $ManifestPath

if (Test-Path -LiteralPath $LegacyBatchPath -PathType Leaf) {
    Remove-Item -LiteralPath $LegacyBatchPath -Force
}

Write-Host "Windows-WSL Native Host installed: $RelayPath"
Write-Host "Firefox manifest registered: $ManifestPath"
Write-Host "WSL host verified: $WslHostPath (version $($SelfTest.version))"
Write-Host 'Restart Firefox, then open the add-on settings.'
