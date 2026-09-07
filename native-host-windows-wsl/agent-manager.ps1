[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDirectory = Split-Path -Parent $ScriptDirectory
$InstallScript = Join-Path $ScriptDirectory 'install.ps1'
$UninstallScript = Join-Path $ScriptDirectory 'uninstall.ps1'
$InstallDirectory = Join-Path $env:LOCALAPPDATA 'ProjektKanbanAgent'
$InstalledHost = Join-Path $InstallDirectory 'kanban_agent_host.py'
$WslCommand = Get-Command 'wsl.exe' -ErrorAction Stop

function Add-Label {
    param([string]$Text, [int]$Top)
    $Label = New-Object System.Windows.Forms.Label
    $Label.Text = $Text
    $Label.Left = 24
    $Label.Top = $Top
    $Label.Width = 180
    $Label.Height = 24
    $Label.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $Form.Controls.Add($Label)
    return $Label
}

function New-TextBox {
    param([int]$Top, [string]$Value = '')
    $Control = New-Object System.Windows.Forms.TextBox
    $Control.Left = 205
    $Control.Top = $Top - 3
    $Control.Width = 455
    $Control.Height = 28
    $Control.Text = $Value
    $Control.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $Form.Controls.Add($Control)
    return $Control
}

function Write-Status {
    param([string]$Message, [bool]$Error = $false)
    $StatusBox.ForeColor = if ($Error) { [System.Drawing.Color]::DarkRed } else { [System.Drawing.Color]::DarkGreen }
    $StatusBox.Text = $Message
    $StatusBox.SelectionStart = $StatusBox.TextLength
    $StatusBox.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

function Get-Distribution {
    $Value = [string]$DistributionBox.Text
    $Value = $Value.Trim()
    if (-not $Value) {
        throw 'Bitte eine WSL-Distribution auswählen.'
    }
    return $Value
}

function Get-WslHostPath {
    param([string]$Distribution)
    if (-not (Test-Path -LiteralPath $InstalledHost -PathType Leaf)) {
        throw 'Die Bridge ist noch nicht installiert. Bitte zuerst „Installieren / aktualisieren“ wählen.'
    }
    $Output = @(& $WslCommand.Path --distribution $Distribution --exec wslpath -a -u $InstalledHost)
    if ($LASTEXITCODE -ne 0 -or $Output.Count -eq 0) {
        throw 'Der installierte Host-Pfad konnte nicht nach WSL übersetzt werden.'
    }
    return ([string]$Output[-1]).Trim()
}

function Invoke-ManagerHost {
    param([string[]]$Arguments)
    $Distribution = Get-Distribution
    $HostPath = Get-WslHostPath $Distribution
    $Output = @(& $WslCommand.Path --distribution $Distribution --exec python3 $HostPath @Arguments 2>&1)
    $Text = ($Output -join "`n").Trim()
    if (-not $Text) {
        throw 'Der Native Host hat nicht geantwortet.'
    }
    try {
        $Response = $Text | ConvertFrom-Json
    } catch {
        throw "Ungültige Antwort des Native Host: $Text"
    }
    if ($LASTEXITCODE -ne 0 -or -not $Response.ok) {
        $Message = if ($Response.error.message) { [string]$Response.error.message } else { $Text }
        throw $Message
    }
    return $Response.data
}

function Get-SandboxValue {
    switch ([string]$SandboxBox.SelectedItem) {
        'Nur lesen (Dry-Run)' { return 'read-only' }
        'Arbeitsbereich schreiben' { return 'workspace-write' }
        'Uneingeschränkter Zugriff' { return 'danger-full-access' }
        default { throw 'Bitte eine Zugriffsart auswählen.' }
    }
}

function Save-AgentConfiguration {
    $AgentId = $AgentIdBox.Text.Trim()
    $Label = $AgentLabelBox.Text.Trim()
    $Executable = $ExecutableBox.Text.Trim()
    $Sandbox = Get-SandboxValue
    $Workspace = $WorkspaceBox.Text.Trim()
    if (-not $AgentId -or -not $Label -or -not $Executable) {
        throw 'Agent-ID, Anzeigename und Agentenprogramm müssen ausgefüllt sein.'
    }
    if ($Sandbox -ne 'danger-full-access' -and -not $Workspace) {
        throw 'Für diesen Modus muss ein Arbeitsbereich angegeben werden.'
    }
    if ($Sandbox -eq 'danger-full-access') {
        $Workspace = '__HOME__'
    }
    $Data = Invoke-ManagerHost @(
        '--manager-configure-local', $AgentId, $Label, $Executable, $Sandbox, $Workspace
    )
    return $Data
}

function Refresh-Status {
    try {
        $Data = Invoke-ManagerHost @('--manager-status')
        $Agent = @($Data.agents | Where-Object { $_.id -eq $AgentIdBox.Text.Trim() }) | Select-Object -First 1
        if ($null -eq $Agent) {
            Write-Status "Bridge $($Data.version) ist installiert. Der Agent ist noch nicht konfiguriert."
        } else {
            $AgentLabelBox.Text = [string]$Agent.label
            $ExecutableBox.Text = [string]$Agent.executable
            if ([string]$Agent.workspace) { $WorkspaceBox.Text = [string]$Agent.workspace }
            switch ([string]$Agent.sandbox) {
                'read-only' { $SandboxBox.SelectedItem = 'Nur lesen (Dry-Run)' }
                'workspace-write' { $SandboxBox.SelectedItem = 'Arbeitsbereich schreiben' }
                'danger-full-access' { $SandboxBox.SelectedItem = 'Uneingeschränkter Zugriff' }
            }
            $State = if ($Agent.enabled) { 'AKTIV' } else { 'DEAKTIVIERT' }
            Write-Status "Bridge $($Data.version) verbunden.`r`nAgent „$($Agent.label)“: $State"
        }
    } catch {
        Write-Status $_.Exception.Message $true
    }
}

$Form = New-Object System.Windows.Forms.Form
$Form.Text = 'Projekt Kanban Agent Manager'
$Form.StartPosition = 'CenterScreen'
$Form.ClientSize = New-Object System.Drawing.Size(710, 600)
$Form.MinimumSize = New-Object System.Drawing.Size(726, 639)
$Form.Font = New-Object System.Drawing.Font('Segoe UI', 10)

$Title = New-Object System.Windows.Forms.Label
$Title.Text = 'Projekt Kanban Agent Manager'
$Title.Left = 24
$Title.Top = 18
$Title.Width = 650
$Title.Height = 34
$Title.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 18)
$Form.Controls.Add($Title)

$Description = New-Object System.Windows.Forms.Label
$Description.Text = 'Installiert die Windows-WSL-Bridge und verwaltet einen lokalen Codex-Agenten.'
$Description.Left = 26
$Description.Top = 55
$Description.Width = 650
$Description.Height = 25
$Description.ForeColor = [System.Drawing.Color]::DimGray
$Form.Controls.Add($Description)

Add-Label 'WSL-Distribution' 98 | Out-Null
$DistributionBox = New-Object System.Windows.Forms.ComboBox
$DistributionBox.Left = 205
$DistributionBox.Top = 94
$DistributionBox.Width = 455
$DistributionBox.DropDownStyle = 'DropDown'
$Form.Controls.Add($DistributionBox)

try {
    $Distributions = @(& $WslCommand.Path --list --quiet) | ForEach-Object { ([string]$_).Replace([char]0, '').Trim() } | Where-Object { $_ }
    foreach ($Distribution in $Distributions) { [void]$DistributionBox.Items.Add($Distribution) }
    if ($DistributionBox.Items.Count -gt 0) { $DistributionBox.SelectedIndex = 0 }
} catch {}

Add-Label 'Agent-ID' 140 | Out-Null
$AgentIdBox = New-TextBox 140 'local-codex'
Add-Label 'Anzeigename' 182 | Out-Null
$AgentLabelBox = New-TextBox 182 'Codex in WSL'
Add-Label 'Agentenprogramm (WSL)' 224 | Out-Null
$ExecutableBox = New-TextBox 224 "/mnt/c/Users/$env:USERNAME/.codex/bin/wsl/codex"
Add-Label 'Zugriffsart' 266 | Out-Null
$SandboxBox = New-Object System.Windows.Forms.ComboBox
$SandboxBox.Left = 205
$SandboxBox.Top = 262
$SandboxBox.Width = 455
$SandboxBox.DropDownStyle = 'DropDownList'
[void]$SandboxBox.Items.Add('Nur lesen (Dry-Run)')
[void]$SandboxBox.Items.Add('Arbeitsbereich schreiben')
[void]$SandboxBox.Items.Add('Uneingeschränkter Zugriff')
$SandboxBox.SelectedIndex = 1
$Form.Controls.Add($SandboxBox)

$WorkspaceLabel = Add-Label 'Arbeitsbereich (WSL)' 308
$WorkspaceBox = New-TextBox 308 "/mnt/c/Users/$env:USERNAME/workspace"
$WorkspaceHint = New-Object System.Windows.Forms.Label
$WorkspaceHint.Left = 205
$WorkspaceHint.Top = 337
$WorkspaceHint.Width = 455
$WorkspaceHint.Height = 36
$WorkspaceHint.Text = 'Enthält beliebig viele Projekte. Bei uneingeschränktem Zugriff wird automatisch das Benutzer-Home verwendet.'
$WorkspaceHint.ForeColor = [System.Drawing.Color]::DimGray
$WorkspaceHint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$Form.Controls.Add($WorkspaceHint)

$StatusBox = New-Object System.Windows.Forms.TextBox
$StatusBox.Left = 24
$StatusBox.Top = 385
$StatusBox.Width = 636
$StatusBox.Height = 78
$StatusBox.Multiline = $true
$StatusBox.ReadOnly = $true
$StatusBox.ScrollBars = 'Vertical'
$StatusBox.Text = 'Bereit.'
$Form.Controls.Add($StatusBox)

$ButtonPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$ButtonPanel.Left = 20
$ButtonPanel.Top = 480
$ButtonPanel.Width = 650
$ButtonPanel.Height = 80
$ButtonPanel.AutoSize = $false
$ButtonPanel.WrapContents = $true
$Form.Controls.Add($ButtonPanel)

function Add-ActionButton {
    param([string]$Text, [int]$Width, [scriptblock]$Action)
    $Button = New-Object System.Windows.Forms.Button
    $Button.Text = $Text
    $Button.Width = $Width
    $Button.Height = 34
    $Button.Add_Click($Action)
    $ButtonPanel.Controls.Add($Button)
    return $Button
}

Add-ActionButton 'Installieren / aktualisieren' 190 {
    try {
        if (Get-Process -Name 'projekt-kanban-agent-wsl' -ErrorAction SilentlyContinue) {
            throw 'Firefox verwendet die Bridge noch. Bitte Firefox vollständig schließen und danach erneut installieren.'
        }
        Write-Status 'Bridge wird installiert und geprüft …'
        $Distribution = Get-Distribution
        $Output = @(& $InstallScript -Distribution $Distribution 2>&1)
        if ($LASTEXITCODE -ne 0) { throw ($Output -join "`n") }
        [void](Save-AgentConfiguration)
        Write-Status (($Output -join "`r`n") + "`r`nAgentenkonfiguration gespeichert.")
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

Add-ActionButton 'Konfiguration speichern' 180 {
    try {
        [void](Save-AgentConfiguration)
        Write-Status 'Agentenkonfiguration wurde gespeichert.'
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

Add-ActionButton 'Verbindung testen' 145 {
    try {
        [void](Save-AgentConfiguration)
        $Data = Invoke-ManagerHost @('--manager-ping', $AgentIdBox.Text.Trim())
        Write-Status ([string]$Data.message)
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

Add-ActionButton 'Agent starten (aktivieren)' 190 {
    try {
        [void](Save-AgentConfiguration)
        [void](Invoke-ManagerHost @('--manager-enable', $AgentIdBox.Text.Trim()))
        Write-Status 'Agent ist aktiviert. Firefox startet ihn automatisch für freigegebene Tasks.'
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

Add-ActionButton 'Agent stoppen (deaktivieren)' 205 {
    try {
        $Data = Invoke-ManagerHost @('--manager-disable', $AgentIdBox.Text.Trim())
        $Stopped = @($Data.cancelledRuns).Count
        Write-Status "Agent ist deaktiviert. Laufende Agentenprozesse beendet: $Stopped."
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

Add-ActionButton 'Deinstallieren' 120 {
    $Choice = [System.Windows.Forms.MessageBox]::Show(
        'Bridge wirklich deinstallieren? Agenteneinstellungen und Laufhistorie in WSL bleiben erhalten.',
        'Projekt Kanban Agent Manager',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    )
    if ($Choice -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    try {
        $Output = @(& $UninstallScript 2>&1)
        if ($LASTEXITCODE -ne 0) { throw ($Output -join "`n") }
        Write-Status ($Output -join "`r`n")
    } catch { Write-Status $_.Exception.Message $true }
} | Out-Null

$SandboxBox.Add_SelectedIndexChanged({
    $Restricted = ([string]$SandboxBox.SelectedItem) -ne 'Uneingeschränkter Zugriff'
    $WorkspaceLabel.Enabled = $Restricted
    $WorkspaceBox.Enabled = $Restricted
})
$DistributionBox.Add_SelectedIndexChanged({ Refresh-Status })
$Form.Add_Shown({ Refresh-Status })

[void]$Form.ShowDialog()
