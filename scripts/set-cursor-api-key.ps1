# Set CURSOR_API_KEY via secure prompt (no echo, not stored in this file)
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\set-cursor-api-key.ps1

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '=== Cursor API Key Setup ===' -ForegroundColor Cyan
Write-Host 'Create a User API Key at: Cursor Dashboard -> Integrations -> User API Keys'
Write-Host 'Input is hidden (like a password).' -ForegroundColor DarkGray
Write-Host ''

$secure = Read-Host 'Paste User API Key' -AsSecureString
if ($secure.Length -eq 0) {
    Write-Host 'Cancelled: empty input.' -ForegroundColor Yellow
    exit 1
}

$bstr = [IntPtr]::Zero
$key = $null
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    $trimmed = $key.Trim()
    if ($trimmed.Length -lt 8) {
        Write-Host 'Key too short. Check that you pasted a valid User API Key.' -ForegroundColor Red
        exit 1
    }

    [Environment]::SetEnvironmentVariable('CURSOR_API_KEY', $trimmed, 'User')
    $env:CURSOR_API_KEY = $trimmed

    Write-Host ''
    $msg = '(OK) CURSOR_API_KEY saved to user environment. Length: {0} chars.' -f $trimmed.Length
    Write-Host $msg -ForegroundColor Green
    Write-Host '(Tip) Fully quit and restart Wayland, then open a new Cursor Agent session.' -ForegroundColor Yellow
    Write-Host '(Tip) Reopen terminals so they pick up the new variable.' -ForegroundColor DarkGray
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $secure.Dispose()
    $key = $null
}

if (Get-Command agent -ErrorAction SilentlyContinue) {
    Write-Host ''
    Write-Host '--- Verify agent CLI (key not shown) ---' -ForegroundColor Cyan
    try {
        & agent about 2>&1
        Write-Host ''
        & agent models 2>&1 | Select-Object -First 12
    }
    catch {
        Write-Host 'Skipped agent verify (not installed or not on PATH).' -ForegroundColor DarkGray
    }
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
