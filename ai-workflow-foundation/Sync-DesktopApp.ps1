$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$Copies = @(
    @{ Source = "src"; Dest = "src" },
    @{ Source = "web"; Dest = "web" },
    @{ Source = "examples"; Dest = "examples" },
    @{ Source = "aiwf_cli.py"; Dest = "aiwf_cli.py" }
)

$AppRoots = @(
    (Join-Path $ProjectRoot "desktop\src-tauri\target\debug\app"),
    (Join-Path $ProjectRoot "desktop\src-tauri\target\release\app")
)

foreach ($appRoot in $AppRoots) {
    $parent = Split-Path $appRoot -Parent
    if (-not (Test-Path $parent)) {
        continue
    }

    New-Item -ItemType Directory -Force -Path $appRoot | Out-Null

    foreach ($item in $Copies) {
        $source = Join-Path $ProjectRoot $item.Source
        $dest = Join-Path $appRoot $item.Dest
        if (-not (Test-Path $source)) {
            continue
        }

        if (Test-Path $source -PathType Container) {
            if (Test-Path $dest) {
                Remove-Item $dest -Recurse -Force
            }
            Copy-Item $source $dest -Recurse -Force
        } else {
            Copy-Item $source $dest -Force
        }
    }
}

Write-Host "Synced desktop app resources to target/debug/app and target/release/app."
