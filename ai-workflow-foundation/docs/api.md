# Local HTTP API

The local API is implemented with Python standard-library HTTP primitives.

It is designed as the stable boundary for a future React panel or desktop shell.

Start the server:

```powershell
py -B aiwf_cli.py serve --host 127.0.0.1 --port 8765 --executor mock
```

The server is local-first and should bind to `127.0.0.1` by default.

Open the built-in web panel:

```text
http://127.0.0.1:8765/
```

## Endpoints

### Health

```text
GET /health
```

### Workspace

```text
POST /init
```

### Workflows

```text
GET /workflows
GET /workflows/{workflow_id}
POST /workflows
{
  "workflow": {
    "id": "my_workflow",
    "name": "My Workflow",
    "nodes": []
  }
}
PUT /workflows/{workflow_id}
{
  "workflow": { "...": "..." }
}
DELETE /workflows/{workflow_id}
```

Workspace workflows are stored under `.aiwf/workflows/`. Example workflows under `examples/workflows/` are read-only through the API.

### Skills

```text
GET /skills
GET /skills/{skill_id}
POST /skills
{
  "skill": { "...": "..." },
  "markdown": "# SKILL.md content"
}
PUT /skills/{skill_id}
{
  "skill": { "...": "..." },
  "markdown": "# SKILL.md content"
}
DELETE /skills/{skill_id}
POST /skills/{skill_id}/clone
{
  "new_id": "optional_copy_id"
}
GET /skills/sources/wayland
POST /skills/import/wayland
{
  "skill_id": "cron",
  "wayland_path": "optional absolute path"
}
GET /skills/market/catalog
POST /skills/market/install
{
  "skill_id": "module_mapping"
}
```

Workspace skills are stored under `.aiwf/skills/{skill_id}/skill.json` with optional colocated `SKILL.md`. Example skills under `examples/skills/` are read-only through write APIs.

### Validation

```text
POST /validate
{
  "workflow": "examples/workflows/simple_foundation.json"
}
```

```text
POST /validate
{
  "workflow_id": "unity_activity_create"
}
```

### Packages

```text
POST /packages/export
{
  "workflow": "examples/workflows/simple_foundation.json",
  "package": "packages/simple_foundation.aiwf.zip"
}
```

```text
POST /packages/import
{
  "package": "packages/simple_foundation.aiwf.zip"
}
```

Package format:

```text
manifest.json
workflows/<workflow_id>.json
skills/<skill_id>.json
```

### Runs

```text
POST /runs
{
  "workflow": "examples/workflows/simple_foundation.json",
  "executor": "mock"
}
```

```text
POST /runs
{
  "workflow_id": "unity_activity_create",
  "executor": "skill"
}
```

```text
GET /runs/{run_id}
POST /runs/{run_id}/resume
POST /runs/{run_id}/rerun
{
  "node_id": "module_breakdown",
  "executor": "mock"
}
```

`executor` is optional. Supported values are:

- `mock`
- `openai`
- `skill`

The `openai` executor uses:

- `OPENAI_API_KEY` or `AIWF_OPENAI_API_KEY`
- `AIWF_OPENAI_MODEL`
- `AIWF_OPENAI_BASE_URL`
- `AIWF_OPENAI_TIMEOUT`
- `AIWF_OPENAI_TEMPERATURE`

### Reviews

```text
POST /runs/{run_id}/reviews
{
  "node_id": "review_plan",
  "decision": "reject",
  "target_node": "module_breakdown",
  "feedback": "Split rewards into login, milestone, and ranking modules."
}
```

Rejecting a review can create a structured change request.

### Changes

```text
GET /runs/{run_id}/changes
GET /runs/{run_id}/changes/{change_id}
POST /runs/{run_id}/changes/{change_id}/apply
{
  "rerun": true
}
```

### Revisions

```text
GET /runs/{run_id}/revisions
POST /runs/{run_id}/revisions
{
  "message": "Accepted module breakdown"
}
```

### Diff And Rollback

```text
GET /runs/{run_id}/diff?left={revision_id}
GET /runs/{run_id}/diff?left={left_revision_id}&right={right_revision_id}
POST /runs/{run_id}/rollback
{
  "revision_id": "rev_..."
}
```

### Artifacts

```text
GET /runs/{run_id}/artifacts
```

```text
GET /runs/{run_id}/artifact?ref=artifacts/module_breakdown.md
```

```text
PUT /runs/{run_id}/artifact
{
  "ref": "artifacts/module_breakdown.md",
  "content": "# Updated artifact\n"
}
```

`PUT /runs/{run_id}/artifact` updates a text artifact under `artifacts/` and returns the updated run `state`.

## Response Shape

The API returns JSON objects only.

Common keys:

- `state`
- `change`
- `changes`
- `revision_id`
- `revisions`
- `diff`
- `content`
- `error`
