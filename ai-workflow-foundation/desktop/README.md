# AI Workflow Foundation Desktop

Tauri desktop shell for AI Workflow Foundation.

The desktop app is the only supported UI entry point. It:

1. Starts the local Python backend (`aiwf_cli.py serve`)
2. Waits for `/health`
3. Opens the existing web panel in a native window

## Requirements

- Python 3.11+ (`py` launcher on Windows)
- Node.js 18+
- Rust toolchain (`rustup`)

## Launch

From the project root:

```powershell
.\Launch-AIWF.ps1
```

Build release executable (no installer):

```powershell
.\Launch-AIWF.ps1 build
```

Build NSIS installer (requires network to download bundler tools):

```powershell
.\Launch-AIWF.ps1 build:installer
```

## Notes

- Development mode uses the repository files directly.
- Release bundles copy `aiwf_cli.py`, `src/`, `web/`, and `examples/` into app resources.
- The backend still requires a system Python install in v0.1.
