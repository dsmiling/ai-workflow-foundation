$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$LaunchScript = Join-Path $ProjectRoot "Launch-AIWF.ps1"
$SyncScript = Join-Path $ProjectRoot "Sync-DesktopApp.ps1"

function Stop-AiwfProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'py.exe' OR Name = 'aiwf-desktop.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "aiwf_cli\.py|aiwf-desktop" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    $connections = netstat -ano | Select-String "127\.0\.0\.1:(876[5-9]|877[0-9]|878[0-4]).*LISTENING"
    foreach ($line in $connections) {
        $parts = ($line -replace "\s+", " ").Trim().Split(" ")
        $processId = $parts[-1]
        if ($processId -match "^\d+$") {
            Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Syncing desktop app resources..." -ForegroundColor Cyan
& $SyncScript

Write-Host "Stopping existing AIWF backend/desktop processes..." -ForegroundColor Cyan
Stop-AiwfProcesses
Start-Sleep -Milliseconds 500

Write-Host "Launching AIWF desktop..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $ProjectRoot -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $LaunchScript
)

Write-Host "AIWF desktop launch requested. Check the new PowerShell window." -ForegroundColor Green
