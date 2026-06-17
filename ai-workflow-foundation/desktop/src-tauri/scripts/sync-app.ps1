$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
& (Join-Path $ProjectRoot "Sync-DesktopApp.ps1")
