# AI Workflow Foundation

AI Workflow Foundation is a local-first foundation for personal AI workflows.

It is intentionally small in the first version:

- Workflow definitions are files.
- Nodes have explicit inputs, outputs, skills, and approval modes.
- Artifacts are written to disk.
- Runs can pause for review.
- Human feedback is recorded as review data.
- Rejected review feedback becomes a structured change request.
- Nodes can be rerun from a selected point.
- Stable outputs can be committed as revisions.

The current implementation is a local-first Python runner with a Tauri desktop shell. Use `.\Launch-AIWF.ps1` as the primary entry point; the shell starts the Python backend and opens the built-in workflow panel in a native window.

## Current Scope

This project currently supports:

- `workflow.json` definitions.
- `skill.json` descriptions.
- `ai`, `skill`, `review`, and `tool` node types.
- A mock AI executor that produces Markdown artifacts.
- Human review pauses.
- Approve/reject review records.
- Structured change requests from rejected feedback.
- Resume after review.
- Rerun from a selected node.
- Lightweight revision snapshots.
- Revision listing, text diff, and rollback.
- Local HTTP API for future UI integration.
- Built-in no-build web panel.
- Workflow and SkillSpec validation.
- Optional OpenAI-compatible LLM executor.
- Workflow package export/import.
- Artifact edit API and web save.
- Unity activity create example workflow.
- Workflow catalog and workspace CRUD API.
- Web workflow editor with node forms and skill preview.
- Skill orchestration executor with external `SKILL.md` refs.

It does not yet include:

- Embedded Python runtime in the desktop installer.
- YAML parsing.
- Visual graph editing.
- Multi-user collaboration.

## Quick Start

Use the Tauri desktop shell as the primary entry point:

```powershell
cd G:\FF_Wang\ProjectStudy\ai-workflow-foundation\ai-workflow-foundation
.\Launch-AIWF.ps1
```

Requirements:

- Python 3.11+ (`py` launcher on Windows)
- Node.js 18+
- Rust toolchain (`rustup`)

The desktop app starts the local Python backend and opens the built-in workflow panel in a native window.

Use `py`, not `python`, on this machine. `python` currently resolves to Python 2.7.

CLI remains available for automation and delivery checks:

```powershell
py -B aiwf_cli.py init
py -B aiwf_cli.py doctor
py -B aiwf_cli.py validate examples\workflows\simple_foundation.json
py -B aiwf_cli.py run examples\workflows\unity_activity_create.json
```

Use the OpenAI-compatible executor:

```powershell
$env:OPENAI_API_KEY='...'
$env:AIWF_OPENAI_MODEL='gpt-4.1-mini'
py -B aiwf_cli.py run examples\workflows\simple_foundation.json --executor openai
```

Optional environment variables:

```text
AIWF_EXECUTOR=mock|openai
AIWF_OPENAI_API_KEY=<key>
AIWF_OPENAI_MODEL=gpt-4.1-mini
AIWF_OPENAI_BASE_URL=https://api.openai.com/v1
AIWF_OPENAI_TIMEOUT=90
AIWF_OPENAI_TEMPERATURE=0.2
```

The sample workflow pauses at the human review node. Check status:

```powershell
py -B aiwf_cli.py status <run_id>
```

Approve the review node and continue:

```powershell
py -B aiwf_cli.py review <run_id> review_plan approve --feedback "Plan is acceptable for the MVP."
py -B aiwf_cli.py resume <run_id>
py -B aiwf_cli.py commit <run_id> --message "Initial accepted workflow output"
```

Edit an artifact in place:

```powershell
py -B aiwf_cli.py edit-artifact <run_id> artifacts\module_mapping.md --content "# Updated mapping"
```

Rerun a node and all downstream work:

```powershell
py -B aiwf_cli.py rerun <run_id> module_breakdown
```

Inspect or restore revisions:

```powershell
py -B aiwf_cli.py revisions <run_id>
py -B aiwf_cli.py diff <run_id> <revision_id>
py -B aiwf_cli.py diff <run_id> <left_revision_id> <right_revision_id>
py -B aiwf_cli.py rollback <run_id> <revision_id>
```

For manual API debugging only (global flags must come before `serve`):

```powershell
py -B aiwf_cli.py --root . --project-root . serve --host 127.0.0.1 --port 8765 --executor skill
```

Reject feedback produces a structured change request:

```powershell
py -B aiwf_cli.py review <run_id> review_plan reject --target-node module_breakdown --feedback "Split rewards into login, milestone, and ranking modules."
py -B aiwf_cli.py changes <run_id>
py -B aiwf_cli.py show-change <run_id> <change_id>
py -B aiwf_cli.py apply-change <run_id> <change_id> --rerun
```

Export or import a workflow package:

```powershell
py -B aiwf_cli.py export-package examples\workflows\simple_foundation.json packages\simple_foundation.aiwf.zip
py -B aiwf_cli.py import-package packages\simple_foundation.aiwf.zip
```

Run delivery acceptance checks:

```powershell
py -B aiwf_cli.py doctor
```

All runtime data is stored under:

```text
.aiwf/
  runs/
  revisions/
```

`doctor` writes temporary acceptance artifacts under `.doctor-workspace/`.

## Project Layout

```text
ai-workflow-foundation/
  docs/
    architecture.md
    api.md
    delivery.md
  desktop/
    src-tauri/
  Launch-AIWF.ps1
  web/
    index.html          # HTML 壳 + ES module 入口
    styles/
      tokens.css
      base.css
      layout.css
      workflow.css
      settings.css
    js/
      main.js
      core/
      workflow/
      settings/
  examples/
    skills/
    workflows/
  src/
    aiwf/
      cli.py
      doctor.py
      executor.py
      models.py
      packages.py
      runner.py
      server.py
      storage.py
      validation.py
  tests/
```

## Design Bias

This project follows the requirements in:

```text
../docs/ai-workflow-foundation-requirements.md
```

The first implementation optimizes for:

```text
control > reviewability > rollback > configurability > automation speed
```

## Delivery

Use the delivery guide for handoff and release checks:

```text
docs/delivery.md
```
