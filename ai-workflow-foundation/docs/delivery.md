# Delivery Guide

This guide describes how to run, verify, and hand off AI Workflow Foundation.

## Delivery Target

The current deliverable is a local-first MVP:

- no Python package install required
- Tauri desktop shell as the primary UI entry point
- no database service required
- no network required when using the `mock` executor
- local CLI, local HTTP API, and built-in web panel

## Requirements

- Python 3.11 or newer.
- Node.js 18+ and Rust toolchain for the Tauri desktop shell.
- On this Windows machine, use `py`, not `python`.
- Optional: `OPENAI_API_KEY` for the OpenAI-compatible executor.

Check Python:

```powershell
py --version
```

## First Run

```powershell
cd G:\FF_Wang\ProjectStudy\ai-harness-main\ai-harness-main\ai-workflow-foundation
py -B aiwf_cli.py init
py -B aiwf_cli.py doctor
```

`doctor` must return:

```json
{
  "ok": true
}
```

## Start The Desktop App

```powershell
cd G:\FF_Wang\ProjectStudy\ai-workflow-foundation\ai-workflow-foundation
.\Launch-AIWF.ps1
```

The Tauri shell starts the Python backend, waits for `/health`, and opens the built-in workflow panel in a native window.

Build a release executable:

```powershell
.\Launch-AIWF.ps1 build
```

Output:

```text
desktop\src-tauri\target\release\aiwf-desktop.exe
```

## Manual API / Browser Debug

```powershell
py -B aiwf_cli.py --root . --project-root . serve --host 127.0.0.1 --port 8765 --executor mock
```

Open:

```text
http://127.0.0.1:8765/
```

Recommended first UI flow:

1. Click `Init`.
2. Click `Validate`.
3. Click `Run`.
4. Open the generated artifact.
5. Approve or reject `review_plan`.
6. If rejected, apply the generated change and rerun.
7. Commit a revision.
8. Diff or rollback the revision.

## CLI Acceptance Flow

```powershell
py -B aiwf_cli.py validate examples\workflows\simple_foundation.json
py -B aiwf_cli.py run examples\workflows\simple_foundation.json
```

Copy the returned `run_id`, then:

```powershell
py -B aiwf_cli.py review <run_id> review_plan approve --feedback "Accepted."
py -B aiwf_cli.py resume <run_id>
py -B aiwf_cli.py commit <run_id> --message "Accepted output"
py -B aiwf_cli.py revisions <run_id>
```

## Feedback And Rerun Flow

```powershell
py -B aiwf_cli.py review <run_id> review_plan reject --target-node module_breakdown --feedback "Split rewards into login, milestone, and ranking modules."
py -B aiwf_cli.py changes <run_id>
py -B aiwf_cli.py show-change <run_id> <change_id>
py -B aiwf_cli.py apply-change <run_id> <change_id> --rerun
```

The rerun should pause again at `review_plan`.

## OpenAI-Compatible Executor

The default executor is `mock`.

Use `openai` only when a key is configured:

```powershell
$env:OPENAI_API_KEY='...'
$env:AIWF_OPENAI_MODEL='gpt-4.1-mini'
py -B aiwf_cli.py run examples\workflows\simple_foundation.json --executor openai
```

Supported environment variables:

```text
AIWF_EXECUTOR=mock|openai
AIWF_OPENAI_API_KEY=<key>
AIWF_OPENAI_MODEL=gpt-4.1-mini
AIWF_OPENAI_BASE_URL=https://api.openai.com/v1
AIWF_OPENAI_TIMEOUT=90
AIWF_OPENAI_TEMPERATURE=0.2
```

## Package Distribution

Export:

```powershell
py -B aiwf_cli.py export-package examples\workflows\simple_foundation.json packages\simple_foundation.aiwf.zip
```

Import:

```powershell
py -B aiwf_cli.py import-package packages\simple_foundation.aiwf.zip
```

Imported files are installed into:

```text
.aiwf/workflows/
.aiwf/skills/
```

## Runtime Data

Runtime data is local and ignored by source control:

```text
.aiwf/
.test-workspace/
.doctor-workspace/
```

Important run files:

```text
.aiwf/runs/<run_id>/workflow.lock.json
.aiwf/runs/<run_id>/state.json
.aiwf/runs/<run_id>/artifacts/
.aiwf/runs/<run_id>/reviews/
.aiwf/runs/<run_id>/changes/
.aiwf/runs/<run_id>/revisions/
```

## Troubleshooting

### `python` runs Python 2.7

Use:

```powershell
py -B aiwf_cli.py doctor
```

### OpenAI executor fails with missing key

Set:

```powershell
$env:OPENAI_API_KEY='...'
```

Or switch back to:

```powershell
--executor mock
```

### Port already in use

Use another port:

```powershell
py -B aiwf_cli.py serve --port 8766
```

### Workflow fails before running

Run:

```powershell
py -B aiwf_cli.py validate <workflow.json>
```

Fix missing skill files, invalid node types, duplicate ids, or invalid artifact references.

## Release Checklist

Before handing off a build:

- `py -B aiwf_cli.py doctor` passes.
- `py -B aiwf_cli.py validate examples\workflows\simple_foundation.json` passes.
- Web panel opens at `http://127.0.0.1:8765/`.
- README, API docs, architecture docs, and this delivery guide are current.
- Package export/import succeeds for the demo workflow.
- OpenAI executor behavior is documented and optional.

