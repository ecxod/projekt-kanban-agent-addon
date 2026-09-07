[CmdletBinding()]
param(
    [string]$InitialDistribution = ''
)

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

function Normalize-DistributionName {
    param([string]$Name)
    return $Name.Replace([string][char]0, [string]::Empty).Trim([char]0xfeff).Trim()
}

function Get-WslDistributions {
    $Names = New-Object System.Collections.Generic.List[string]
    try {
        $Raw = ((& $WslCommand.Path --list --quiet 2>$null) | Out-String).Replace([string][char]0, [string]::Empty)
        foreach ($Line in ($Raw -split "`r?`n")) {
            $Name = Normalize-DistributionName $Line
            if ($Name -and -not $Names.Contains($Name)) { $Names.Add($Name) }
        }
    } catch {}

    try {
        $LxssPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
        $Lxss = Get-ItemProperty -LiteralPath $LxssPath -ErrorAction Stop
        if ($Lxss.DefaultDistribution) {
            $DefaultPath = Join-Path $LxssPath ([string]$Lxss.DefaultDistribution)
            $DefaultName = Normalize-DistributionName ([string](Get-ItemProperty -LiteralPath $DefaultPath -ErrorAction Stop).DistributionName)
            if ($DefaultName) {
                if ($Names.Contains($DefaultName)) { [void]$Names.Remove($DefaultName) }
                $Names.Insert(0, $DefaultName)
            }
        }
    } catch {}
    return $Names.ToArray()
}

function Add-Label {
    param([string]$Text, [int]$Top, [System.Windows.Forms.TabPage]$Page)
    $Label = New-Object System.Windows.Forms.Label
    $Label.Text = $Text
    $Label.Left = 16
    $Label.Top = $Top
    $Label.Width = 180
    $Label.Height = 24
    $Label.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $Page.Controls.Add($Label)
    return $Label
}

function New-TextBox {
    param([int]$Top, [string]$Value = '', [System.Windows.Forms.TabPage]$Page)
    $Control = New-Object System.Windows.Forms.TextBox
    $Control.Left = 205
    $Control.Top = $Top - 3
    $Control.Width = 455
    $Control.Height = 28
    $Control.Text = $Value
    $Control.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $Page.Controls.Add($Control)
    return $Control
}

function Write-Log {
    param([string]$Message)
    if ($null -eq $LogBox) {
        return
    }
    $Timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $LogBox.AppendText("[$Timestamp] $Message`r`n")
    $LogBox.SelectionStart = $LogBox.TextLength
    $LogBox.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

function Write-Status {
    param([string]$Message)
    $StatusBox.ForeColor = [System.Drawing.Color]::DarkGreen
    $StatusBox.Text = $Message
    $StatusBox.SelectionStart = $StatusBox.TextLength
    $StatusBox.ScrollToCaret()
    Write-Log "INFO: $Message"
    [System.Windows.Forms.Application]::DoEvents()
}

function Write-ErrorStatus {
    param([string]$Message)
    $StatusBox.ForeColor = [System.Drawing.Color]::DarkRed
    $StatusBox.Text = $Message
    $StatusBox.SelectionStart = $StatusBox.TextLength
    $StatusBox.ScrollToCaret()
    Write-Log "ERROR: $Message"
    [System.Windows.Forms.Application]::DoEvents()
}

function Get-Distribution {
    $Value = [string]$DistributionBox.Text
    $Value = $Value.Trim()
    if (-not $Value) {
        throw 'Please select a WSL distribution.'
    }
    return $Value
}

function Get-WslHostPath {
    param([string]$Distribution)
    if (-not (Test-Path -LiteralPath $InstalledHost -PathType Leaf)) {
        throw 'The bridge is not installed yet. Click "Install / update bridge" first.'
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
        'Read-only (Dry Run)' { return 'read-only' }
        'Workspace write' { return 'workspace-write' }
        'Unrestricted access' { return 'danger-full-access' }
        default { throw 'Please select an access mode.' }
    }
}

function Save-AgentConfiguration {
    $AgentId = $AgentIdBox.Text.Trim()
    $Label = $AgentLabelBox.Text.Trim()
    $Executable = $ExecutableBox.Text.Trim()
    $Sandbox = Get-SandboxValue
    $Workspace = $WorkspaceBox.Text.Trim()
    if (-not $AgentId -or -not $Label -or -not $Executable) {
        throw 'Agent ID, display name, and executable are required.'
    }
    if ($Sandbox -ne 'danger-full-access' -and -not $Workspace) {
        throw 'A workspace is required for this access mode.'
    }
    if ($Sandbox -eq 'danger-full-access') {
        $Workspace = '__HOME__'
    }
    $Data = Invoke-ManagerHost @(
        '--manager-configure-local', $AgentId, $Label, $Executable, $Sandbox, $Workspace
    )
    return $Data
}

$SaveButton = $null
$TestButton = $null
$EnableButton = $null
$DisableButton = $null
$UninstallButton = $null

function Update-ActionButtons {
    param([bool]$BridgeAvailable, [object]$Agent)
    $hasAgent = $null -ne $Agent
    $agentEnabled = $hasAgent -and [bool]$Agent.enabled
    if ($null -ne $SaveButton) { $SaveButton.Enabled = $BridgeAvailable }
    if ($null -ne $TestButton) { $TestButton.Enabled = $BridgeAvailable -and $agentEnabled }
    if ($null -ne $EnableButton) { $EnableButton.Enabled = $BridgeAvailable -and $hasAgent -and -not $agentEnabled }
    if ($null -ne $DisableButton) { $DisableButton.Enabled = $BridgeAvailable -and $agentEnabled }
    if ($null -ne $UninstallButton) { $UninstallButton.Enabled = $BridgeAvailable }
}

function Refresh-Status {
    try {
        $Data = Invoke-ManagerHost @('--manager-status')
        $Agent = @($Data.agents | Where-Object { $_.id -eq $AgentIdBox.Text.Trim() }) | Select-Object -First 1
        if ($null -eq $Agent) {
            Update-ActionButtons $true $null
            Write-Status "Bridge $($Data.version) is installed. The agent is not configured yet."
        } else {
            $AgentLabelBox.Text = [string]$Agent.label
            $ExecutableBox.Text = [string]$Agent.executable
            if ([string]$Agent.workspace) { $WorkspaceBox.Text = [string]$Agent.workspace }
            switch ([string]$Agent.sandbox) {
                'read-only' { $SandboxBox.SelectedItem = 'Read-only (Dry Run)' }
                'workspace-write' { $SandboxBox.SelectedItem = 'Workspace write' }
                'danger-full-access' { $SandboxBox.SelectedItem = 'Unrestricted access' }
            }
            $State = if ($Agent.enabled) { 'ENABLED' } else { 'DISABLED' }
            Update-ActionButtons $true $Agent
            Write-Status "Bridge $($Data.version) connected.`r`nAgent '$($Agent.label)': $State"
        }
    } catch {
        Update-ActionButtons $false $null
        Write-ErrorStatus $_.Exception.Message
    }
}

$Form = New-Object System.Windows.Forms.Form
$Form.Text = 'Projekt Kanban Agent Manager'
$Form.StartPosition = 'CenterScreen'
$Form.ClientSize = New-Object System.Drawing.Size(710, 600)
$Form.MinimumSize = New-Object System.Drawing.Size(726, 639)
$Form.Font = New-Object System.Drawing.Font('Segoe UI', 10)

$Tabs = New-Object System.Windows.Forms.TabControl
$Tabs.Left = 8
$Tabs.Top = 6
$Tabs.Width = 694
$Tabs.Height = 588
$ManagerPage = New-Object System.Windows.Forms.TabPage
$ManagerPage.Text = 'Manager'
$SettingsPage = New-Object System.Windows.Forms.TabPage
$SettingsPage.Text = 'Settings'
$LogPage = New-Object System.Windows.Forms.TabPage
$LogPage.Text = 'Log'
$HelpPage = New-Object System.Windows.Forms.TabPage
$HelpPage.Text = 'Help'
[void]$Tabs.TabPages.Add($ManagerPage)
[void]$Tabs.TabPages.Add($SettingsPage)
[void]$Tabs.TabPages.Add($LogPage)
[void]$Tabs.TabPages.Add($HelpPage)
$Form.Controls.Add($Tabs)

$Title = New-Object System.Windows.Forms.Label
$Title.Text = 'Projekt Kanban Agent Manager'
$Title.Left = 16
$Title.Top = 18
$Title.Width = 650
$Title.Height = 34
$Title.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 18)
$ManagerPage.Controls.Add($Title)

$Description = New-Object System.Windows.Forms.Label
$Description.Text = 'Installs the Windows-WSL bridge and manages a local Codex agent.'
$Description.Left = 18
$Description.Top = 55
$Description.Width = 650
$Description.Height = 25
$Description.ForeColor = [System.Drawing.Color]::DimGray
$ManagerPage.Controls.Add($Description)

$SettingsTitle = New-Object System.Windows.Forms.Label
$SettingsTitle.Text = 'Agent settings'
$SettingsTitle.Left = 16
$SettingsTitle.Top = 18
$SettingsTitle.Width = 650
$SettingsTitle.Height = 34
$SettingsTitle.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 18)
$SettingsPage.Controls.Add($SettingsTitle)

Add-Label 'WSL distribution' 98 $SettingsPage | Out-Null
$DistributionBox = New-Object System.Windows.Forms.ComboBox
$DistributionBox.Left = 205
$DistributionBox.Top = 94
$DistributionBox.Width = 455
$DistributionBox.DropDownStyle = 'DropDown'
$SettingsPage.Controls.Add($DistributionBox)

$InitialDistribution = Normalize-DistributionName $InitialDistribution
$Distributions = @(Get-WslDistributions)
foreach ($Distribution in $Distributions) { [void]$DistributionBox.Items.Add($Distribution) }
if ($InitialDistribution -and $DistributionBox.Items.Contains($InitialDistribution)) {
    $DistributionBox.SelectedItem = $InitialDistribution
} elseif ($DistributionBox.Items.Count -gt 0) {
    $DistributionBox.SelectedIndex = 0
} elseif ($InitialDistribution) {
    [void]$DistributionBox.Items.Add($InitialDistribution)
    $DistributionBox.SelectedItem = $InitialDistribution
}

Add-Label 'Agent ID' 140 $SettingsPage | Out-Null
$AgentIdBox = New-TextBox 140 'local-codex' $SettingsPage
Add-Label 'Display name' 182 $SettingsPage | Out-Null
$AgentLabelBox = New-TextBox 182 'Codex in WSL' $SettingsPage
Add-Label 'Agent executable (WSL)' 224 $SettingsPage | Out-Null
$ExecutableBox = New-TextBox 224 "/mnt/c/Users/$env:USERNAME/.codex/bin/wsl/codex" $SettingsPage
Add-Label 'Access mode' 266 $SettingsPage | Out-Null
$SandboxBox = New-Object System.Windows.Forms.ComboBox
$SandboxBox.Left = 205
$SandboxBox.Top = 262
$SandboxBox.Width = 455
$SandboxBox.DropDownStyle = 'DropDownList'
[void]$SandboxBox.Items.Add('Read-only (Dry Run)')
[void]$SandboxBox.Items.Add('Workspace write')
[void]$SandboxBox.Items.Add('Unrestricted access')
$SandboxBox.SelectedIndex = 1
$SettingsPage.Controls.Add($SandboxBox)

$WorkspaceLabel = Add-Label 'Workspace (WSL)' 308 $SettingsPage
$WorkspaceBox = New-TextBox 308 "/mnt/c/Users/$env:USERNAME/projekt-kanban" $SettingsPage
$WorkspaceHint = New-Object System.Windows.Forms.Label
$WorkspaceHint.Left = 205
$WorkspaceHint.Top = 337
$WorkspaceHint.Width = 455
$WorkspaceHint.Height = 36
$WorkspaceHint.Text = 'Can contain multiple projects. Unrestricted access uses the agent user home automatically.'
$WorkspaceHint.ForeColor = [System.Drawing.Color]::DimGray
$WorkspaceHint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$SettingsPage.Controls.Add($WorkspaceHint)

$StatusBox = New-Object System.Windows.Forms.TextBox
$StatusBox.Left = 16
$StatusBox.Top = 90
$StatusBox.Width = 662
$StatusBox.Height = 300
$StatusBox.Multiline = $true
$StatusBox.ReadOnly = $true
$StatusBox.ScrollBars = 'Both'
$StatusBox.WordWrap = $false
$StatusBox.Text = 'Ready.'
$ManagerPage.Controls.Add($StatusBox)

$LogBox = New-Object System.Windows.Forms.TextBox
$LogBox.Multiline = $true
$LogBox.ReadOnly = $true
$LogBox.ScrollBars = 'Both'
$LogBox.WordWrap = $false
$LogBox.Dock = 'Fill'
$LogBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$LogPage.Controls.Add($LogBox)

$HelpBox = New-Object System.Windows.Forms.TextBox
$HelpBox.Multiline = $true
$HelpBox.ReadOnly = $true
$HelpBox.ScrollBars = 'Vertical'
$HelpBox.WordWrap = $true
$HelpBox.Dock = 'Fill'
$HelpBox.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$HelpBox.Text = @'
Help for the Projekt Kanban Agent Manager

Tabs
Manager: Run actions and view the current status.
Settings: Configure the WSL distribution, agent, executable, access mode, and workspace.
Log: View timestamped information and error messages.
Help: View this explanation.

Settings
WSL distribution: The Linux distribution where the Native Host and Codex run.
Agent ID: The unique internal identifier of the agent.
Display name: The readable name used in status messages.
Agent executable (WSL): The absolute WSL path to the Codex executable.
Access mode: Controls what the agent is allowed to change.
Workspace (WSL): The directory where the agent is allowed to work.

Access modes
Read-only (Dry Run): The agent may analyze, but cannot change files.
Workspace write: The agent may read and write inside the configured workspace.
Unrestricted access: The agent may access the entire agent user's account.
Use this option only when you explicitly accept the additional risk.

Buttons
Install / update bridge: Installs the Windows-WSL bridge and runs its self-test.
Save agent configuration: Saves the Settings values in WSL.
Test Codex connection: Checks whether Codex and the workspace are reachable.
Enable agent for tasks: Allows new tasks for this agent.
Disable agent and cancel runs: Prevents new tasks and cancels active tasks.
Uninstall Windows bridge: Removes the Windows bridge but keeps settings and run history.

The agent does not run permanently. Firefox starts Codex only after a task
has been confirmed and sent from the Kanban page.
'@
$HelpPage.Controls.Add($HelpBox)

$ButtonPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$ButtonPanel.Left = 10
$ButtonPanel.Top = 400
$ButtonPanel.Width = 674
$ButtonPanel.Height = 100
$ButtonPanel.AutoSize = $false
$ButtonPanel.WrapContents = $true
$ManagerPage.Controls.Add($ButtonPanel)

$SettingsButtonPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$SettingsButtonPanel.Left = 10
$SettingsButtonPanel.Top = 400
$SettingsButtonPanel.Width = 674
$SettingsButtonPanel.Height = 100
$SettingsButtonPanel.AutoSize = $false
$SettingsButtonPanel.WrapContents = $true
$SettingsPage.Controls.Add($SettingsButtonPanel)

function Add-ActionButton {
    param([string]$Text, [int]$Width, [scriptblock]$Action, [System.Windows.Forms.FlowLayoutPanel]$Panel = $ButtonPanel)
    $Button = New-Object System.Windows.Forms.Button
    $Button.Text = $Text
    $Button.Width = $Width
    $Button.Height = 34
    $Button.Add_Click($Action)
    $Panel.Controls.Add($Button)
    return $Button
}

$InstallButton = Add-ActionButton 'Install / update bridge' 210 {
    try {
        if (Get-Process -Name 'projekt-kanban-agent-wsl' -ErrorAction SilentlyContinue) {
            throw 'Firefox is still using the bridge. Close Firefox completely and try again.'
        }
        Write-Status 'Installing and testing the bridge …'
        $Distribution = Get-Distribution
        $Output = @(& $InstallScript -Distribution $Distribution 2>&1)
        if ($LASTEXITCODE -ne 0) { throw ($Output -join "`n") }
        $Saved = Save-AgentConfiguration
        Write-Status (($Output -join "`r`n") + "`r`nAgent configuration saved.")
        Update-ActionButtons $true $Saved.agent
    } catch { Write-ErrorStatus $_.Exception.Message }
}

$SaveButton = Add-ActionButton 'Save agent configuration' 210 {
    try {
        $Saved = Save-AgentConfiguration
        Write-Status 'Agent configuration saved.'
        Update-ActionButtons $true $Saved.agent
    } catch { Write-ErrorStatus $_.Exception.Message }
} -Panel $SettingsButtonPanel

$EnableButton = Add-ActionButton 'Enable agent for tasks' 180 {
    try {
        $Saved = Save-AgentConfiguration
        [void](Invoke-ManagerHost @('--manager-enable', $AgentIdBox.Text.Trim()))
        Write-Status 'Agent enabled. Firefox will start it automatically for confirmed tasks.'
        Update-ActionButtons $true ([pscustomobject]@{ enabled = $true })
    } catch { Write-ErrorStatus $_.Exception.Message }
}

$DisableButton = Add-ActionButton 'Disable agent and cancel runs' 220 {
    try {
        $Data = Invoke-ManagerHost @('--manager-disable', $AgentIdBox.Text.Trim())
        $Stopped = @($Data.cancelledRuns).Count
        Write-Status "Agent disabled. Active agent processes cancelled: $Stopped."
        Update-ActionButtons $true ([pscustomobject]@{ enabled = $false })
    } catch { Write-ErrorStatus $_.Exception.Message }
}

$UninstallButton = Add-ActionButton 'Uninstall Windows bridge' 190 {
    $Choice = [System.Windows.Forms.MessageBox]::Show(
        'Uninstall the bridge? Agent settings and run history in WSL will be kept.',
        'Projekt Kanban Agent Manager',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    )
    if ($Choice -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    try {
        $Output = @(& $UninstallScript 2>&1)
        if ($LASTEXITCODE -ne 0) { throw ($Output -join "`n") }
        Write-Status ($Output -join "`r`n")
        Update-ActionButtons $false $null
    } catch { Write-ErrorStatus $_.Exception.Message }
}

$TestButton = Add-ActionButton 'Test Codex connection' 180 {
    try {
        $Saved = Save-AgentConfiguration
        $Data = Invoke-ManagerHost @('--manager-ping', $AgentIdBox.Text.Trim())
        Write-Status ([string]$Data.message)
        Update-ActionButtons $true $Saved.agent
    } catch { Write-ErrorStatus $_.Exception.Message }
}

$SandboxBox.Add_SelectedIndexChanged({
    $Restricted = ([string]$SandboxBox.SelectedItem) -ne 'Unrestricted access'
    $WorkspaceLabel.Enabled = $Restricted
    $WorkspaceBox.Enabled = $Restricted
})
$DistributionBox.Add_SelectedIndexChanged({ Refresh-Status })
$Form.Add_Shown({ Refresh-Status })

[void]$Form.ShowDialog()
