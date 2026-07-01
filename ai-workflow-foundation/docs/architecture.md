# AI Workflow Foundation Architecture

## Intent

The foundation is a small local control plane for AI workflows.

It should eventually support visual workflow editing and real AI/Agent execution, but the first version proves the stable substrate:

```text
Workflow -> Node -> Artifact -> Review -> Rerun -> Revision
```

## Runtime Shape

```text
CLI / built-in Web UI
  -> CLI or Local HTTP API
    -> WorkflowRunner
    -> WorkflowStore
      -> Executor Adapter
      -> MockAIExecutor
      -> OpenAICompatibleExecutor
      -> CliAcpClient (cursor-agent-acp / codex-agent-acp)
```

## CLI Agent Providers (ACP Session)

CLI providers use **Agent Client Protocol** over stdio (JSON-RPC NDJSON):

- `cursor-agent-acp` — `agent acp` (Windows: PowerShell → `cursor-agent.ps1 acp`)
- `codex-agent-acp` — `codex app-server` (override via `AIWF_CODEX_ACP_CMD`)

Session layers:

| Layer | Scope | Workspace |
|-------|-------|-----------|
| L0 Role | `agent_id` | `.aiwf/agents/assist/<session>/` |
| L1 Assist | `workflow_id` | `.aiwf/assist/<session>/` |
| L2/L3 Node | `run_id:node_id` | run dir + `node_sessions/<node_id>/session.json` |

API providers (`openai-api`, etc.) remain one-shot HTTP `generate()`.

## File Layout

Runtime state lives under `.aiwf/`:

```text
.aiwf/
  runs/
    run_<timestamp>/
      workflow.lock.json
      state.json
      artifacts/
      node_results/
      node_sessions/
      reviews/
      changes/
      revisions/
  revisions/
  skills/
  workflows/
```

The run directory is the source of truth for execution evidence.

## Package Contract

A workflow package is a zip file that contains:

```text
manifest.json
workflows/<workflow_id>.json
skills/<skill_id>.json
```

Export collects the workflow and referenced skill files. Import installs them into `.aiwf/workflows` and `.aiwf/skills` for local use.

## Delivery Gate

`aiwf doctor` is the local delivery gate. It validates the demo workflow, executes the review/change/rerun/revision/package/server paths, and emits a JSON report. A release candidate should not be considered shippable unless `doctor` passes.

## Node Contract

Every node should make these visible:

- id
- name
- type
- skill
- inputs (InputBinding: literal or upstream artifact)
- output contract (from Skill; node-level override is advanced)
- approval mode
- current state
- execution result (summary, assets, changes)
- artifact path (shortcut for primary_ref)

Workflow validation checks required fields, duplicate node ids, supported node types, approval modes, artifact input ordering, and referenced skill files before execution.

### InputBinding

Persisted under `node.inputs`. Supported sources in v0.3:

- `literal` — fixed text value
- `artifact` — upstream node primary artifact (`ref: <node_id>`)
- legacy string — `artifact.<node_id>` or plain literal string

### ExecutionResult

Each node execution (or Session turn) produces:

- `summary` — human-readable one-liner
- `assets[]` —落盘产物记录 (ref, kind, action)
- `changes[]` — Changelist items (create/modify/delete)
- `primary_ref` — main artifact path

Stored in `node_results/<node_id>.json` and `NodeRunState.result`. JSON schemas: `docs/schemas/execution-result.schema.json`.

### NodeSession

Multi-turn iteration before Review. Stored under `node_sessions/<node_id>/`:

- `session.json` — status (`iterating` | `committed` | `abandoned`), overlays
- `turns/turn_NNN.json` — per-turn feedback + ExecutionResult

Schemas: `docs/schemas/node-session.schema.json`, `docs/schemas/session-turn.schema.json`.

## Skill Contract

A skill is a descriptive execution contract, not a plugin SDK.

It must provide enough information for an executor to understand:

- goal
- context
- output expectations
- quality bar

Free-form Skill descriptions are allowed, but output contracts and quality bars are mandatory for reliable review.

## Approval Contract

The first approval modes are:

```text
auto
ai
human
```

Only `auto` and `human` are implemented in the current runner. `ai` will be added when a real evaluator executor exists.

## Revision Contract

A revision is a snapshot of:

- artifacts
- reviews
- state
- workflow.lock.json
- manifest metadata

The current implementation is intentionally lighter than Git. It supports listing revisions, text diff, and rollback. It can later be replaced by or backed by Git without changing the workflow concepts.

## Rerun Contract

Rerun starts execution again from a selected node.

When a node is rerun:

- The selected node and downstream node states are reset.
- Review records for the selected node and downstream nodes are invalidated.
- Upstream completed node states are preserved.
- New node output overwrites the configured artifact path.

## Change Request Contract

A change request is a structured version of human feedback.

The first implementation supports a conservative operation set:

- append feedback to `workflow.node.params.feedback_history`
- set `workflow.node.params.last_feedback`
- set / append `workflow.node.params.extra_prompt`
- merge `workflow.node.inputs` (run-local overlay)

Schema: `docs/schemas/change-operation.schema.json`.

Rejected review feedback can create a proposed change request. The review node can target itself or an upstream node that produced the artifact under review. Applying a change request updates the run-local `workflow.lock.json`, not the global workflow template. This keeps node tuning reversible and scoped to one run until the user commits a revision.

## Workflow Catalog

Workflow definitions are discovered from:

```text
.aiwf/workflows/
examples/workflows/
```

The local API exposes workflow CRUD for workspace copies. Example workflows remain read-only until copied into `.aiwf/workflows/`.

## Skill Orchestration

`SkillExecutor` wraps `mock` or `openai` executors and enriches a node with external `SKILL.md` content referenced by `SkillSpec.ref`.

## Next Technical Steps

1. Add richer change operations for SkillSpec and output contracts.
2. Add optional FastAPI adapter if dependency-based deployment becomes acceptable.
3. Add executor adapters for Cursor Agent / AI Harness / OpenClaw.
4. Optional desktop shell packaging.
