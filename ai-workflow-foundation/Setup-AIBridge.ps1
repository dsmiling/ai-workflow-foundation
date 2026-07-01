#Requires -Version 5.1
<#
.SYNOPSIS
  Configure AIWF + AIBridge Unity context integration on this machine.

.DESCRIPTION
  1. Validates .NET 8 runtime (AIBridge CLI requirement)
  2. Writes AIWF Unity env vars to the current-user registry (optional)
  3. Prints Unity Package Manager install steps for AIBridge

.PARAMETER UnityProjectRoot
  Absolute path to the Unity project that will host AIBridge.

.PARAMETER PersistUserEnv
  Persist AIWF_UNITY_PROJECT_ROOT (and optional AIWF_CURSOR_WORKSPACE) to the user environment.

.EXAMPLE
  .\Setup-AIBridge.ps1 -UnityProjectRoot "G:\Games\MyUnityProject" -PersistUserEnv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $UnityProjectRoot,

    [switch] $PersistUserEnv,

    [string] $AibridgeCli = ""
)

$ErrorActionPreference = "Stop"
$unityRoot = (Resolve-Path -LiteralPath $UnityProjectRoot).Path
$cliDefault = Join-Path $unityRoot ".aibridge\cli\AIBridgeCLI.exe"

Write-Host "== AIWF + AIBridge Setup ==" -ForegroundColor Cyan
Write-Host "Unity project: $unityRoot"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Warning ".NET SDK/runtime not found in PATH. AIBridge CLI requires .NET 8 Runtime."
    Write-Host "Install: https://dotnet.microsoft.com/download/dotnet/8.0"
} else {
    $dotnetVersion = (& dotnet --version) 2>$null
    Write-Host "dotnet: $dotnetVersion"
}

if (Test-Path -LiteralPath $cliDefault) {
    Write-Host "AIBridge CLI: found at $cliDefault" -ForegroundColor Green
} else {
    Write-Host "AIBridge CLI: not found yet (install package in Unity first)." -ForegroundColor Yellow
    Write-Host @"

Unity Package Manager → Add package from git URL:
  https://github.com/liyingsong99/AIBridge.git

Then in Unity Editor:
  AIBridge → Workflows → Skills → select Cursor → Install Selected Integrations

Open the target Unity project once so AIBridge copies CLI to:
  $cliDefault
"@ -ForegroundColor DarkGray
}

if ($PersistUserEnv) {
    [Environment]::SetEnvironmentVariable("AIWF_UNITY_PROJECT_ROOT", $unityRoot, "User")
    [Environment]::SetEnvironmentVariable("AIWF_CURSOR_WORKSPACE", $unityRoot, "User")
    if ($AibridgeCli) {
        [Environment]::SetEnvironmentVariable("AIWF_AIBRIDGE_CLI", $AibridgeCli, "User")
    }
    Write-Host "Persisted user env: AIWF_UNITY_PROJECT_ROOT, AIWF_CURSOR_WORKSPACE" -ForegroundColor Green
} else {
    $env:AIWF_UNITY_PROJECT_ROOT = $unityRoot
    $env:AIWF_CURSOR_WORKSPACE = $unityRoot
    if ($AibridgeCli) {
        $env:AIWF_AIBRIDGE_CLI = $AibridgeCli
    }
    Write-Host "Set session env: AIWF_UNITY_PROJECT_ROOT, AIWF_CURSOR_WORKSPACE" -ForegroundColor Green
}

Write-Host @"

Node params example (workflow JSON):
  "params": {
    "unity_context": {
      "active_scene": true,
      "scene_hierarchy_depth": 3,
      "prefab_filter": "t:Prefab",
      "prefab_max": 5,
      "required": false
    }
  }

Or enable global auto-capture (active scene only):
  AIWF_UNITY_CONTEXT_AUTO=1

Verify:
  py -3 aiwf_cli.py doctor
"@ -ForegroundColor DarkGray
