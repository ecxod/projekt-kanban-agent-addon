@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "WSLDIST="
for /f "usebackq delims=" %%D in (`"%SystemRoot%\System32\wsl.exe" --list --quiet 2^>nul`) do if not defined WSLDIST set "WSLDIST=%%D"
if defined WSLDIST (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -ExecutionPolicy Bypass -File "%SCRIPT_DIR%agent-manager.ps1" -InitialDistribution "%WSLDIST%"
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -ExecutionPolicy Bypass -File "%SCRIPT_DIR%agent-manager.ps1"
)
if errorlevel 1 pause
