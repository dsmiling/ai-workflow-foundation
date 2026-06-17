$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$DesktopDir = Join-Path $ProjectRoot "desktop"

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "node")) {
    throw "Node.js is required. Install Node.js 18+ first."
}

if (-not (Test-Command "py")) {
    throw "Python launcher `py` is required. Install Python 3.11+ first."
}

if (-not (Test-Command "cargo")) {
    $cargoPath = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
    if (Test-Path $cargoPath) {
        $env:Path = "$(Split-Path $cargoPath);$env:Path"
    }
}

if (-not (Test-Command "cargo")) {
    throw "Rust toolchain is required. Install from https://rustup.rs/ and restart the terminal."
}

Push-Location $DesktopDir
try {
    if (-not (Test-Path "node_modules")) {
        npm install
    }

    & (Join-Path $ProjectRoot "Sync-DesktopApp.ps1")

    if ($args.Count -gt 0 -and $args[0] -eq "build") {
        npm run build
    } elseif ($args.Count -gt 0 -and $args[0] -eq "build:installer") {
        npm run build:installer
    } else {
        npm run dev
    }
}
finally {
    Pop-Location
}
