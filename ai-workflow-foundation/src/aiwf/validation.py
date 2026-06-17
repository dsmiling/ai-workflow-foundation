from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .storage import WorkflowStore
from .workflow_graph import ALLOWED_WHEN, WorkflowGraph
from .models import WorkflowSpec


JsonDict = dict[str, Any]

ALLOWED_NODE_TYPES = {"ai", "skill", "tool", "review", "route"}
ALLOWED_APPROVAL_MODES = {"auto", "ai", "human"}
ALLOWED_APPROVAL_LEVELS = {"optional", "required"}


@dataclass(slots=True)
class ValidationReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> JsonDict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_workflow_file(
    store: WorkflowStore,
    workflow_path: Path,
    skill_dirs: list[Path] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    skill_dirs = skill_dirs or [store.root / "examples" / "skills", store.aiwf / "skills"]
    try:
        data = store.read_json(workflow_path)
    except Exception as exc:
        report.error(f"Workflow JSON cannot be read: {exc}")
        return report
    validate_workflow_data(store, data, report, skill_dirs)
    return report


def validate_workflow_data(
    store: WorkflowStore,
    data: JsonDict,
    report: ValidationReport,
    skill_dirs: list[Path],
) -> None:
    if not isinstance(data, dict):
        report.error("Workflow root must be an object.")
        return
    require_string(data, "id", "workflow", report)
    require_string(data, "name", "workflow", report, warning_only=True)
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        report.error("workflow.nodes must be a non-empty list.")
        return

    seen: set[str] = set()
    node_specs: list[JsonDict] = []
    for index, node in enumerate(nodes):
        context = f"node[{index}]"
        if not isinstance(node, dict):
            report.error(f"{context} must be an object.")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            report.error(f"{context}.id must be a non-empty string.")
            continue
        context = f"node[{node_id}]"
        if node_id in seen:
            report.error(f"{context} duplicates another node id.")
        seen.add(node_id)

        node_type = node.get("type", "ai")
        if node_type not in ALLOWED_NODE_TYPES:
            report.error(f"{context}.type must be one of {sorted(ALLOWED_NODE_TYPES)}.")
        if node_type in {"ai", "skill"}:
            skill_id = node.get("skill")
            if not isinstance(skill_id, str) or not skill_id.strip():
                report.error(f"{context}.skill is required for {node_type} nodes.")
            else:
                validate_skill_reference(store, skill_id, skill_dirs, report, context)
        if node_type == "review" and node.get("skill"):
            report.warn(f"{context}.skill is ignored for review nodes.")

        approval = node.get("approval", {})
        if approval is not None and not isinstance(approval, dict):
            report.error(f"{context}.approval must be an object.")
        else:
            approval = approval or {}
            mode = approval.get("mode", "auto")
            level = approval.get("level", "optional")
            if mode not in ALLOWED_APPROVAL_MODES:
                report.error(f"{context}.approval.mode must be one of {sorted(ALLOWED_APPROVAL_MODES)}.")
            if level not in ALLOWED_APPROVAL_LEVELS:
                report.error(f"{context}.approval.level must be one of {sorted(ALLOWED_APPROVAL_LEVELS)}.")

        inputs = node.get("inputs", {})
        if inputs is not None and not isinstance(inputs, dict):
            report.error(f"{context}.inputs must be an object.")

        outputs = node.get("outputs", {})
        if outputs is not None and not isinstance(outputs, dict):
            report.error(f"{context}.outputs must be an object.")
        elif node_type != "review" and not (outputs or {}).get("primary"):
            report.warn(f"{context}.outputs.primary is not set; default artifact path will be used.")

        node_specs.append(node)

    validate_transitions(data, seen, report)
    try:
        graph = WorkflowGraph.from_workflow(WorkflowSpec.from_dict(data))
    except Exception as exc:
        report.error(f"workflow graph cannot be built: {exc}")
        return
    for node in node_specs:
        node_id = str(node.get("id"))
        context = f"node[{node_id}]"
        inputs = node.get("inputs", {})
        if inputs is not None and not isinstance(inputs, dict):
            continue
        validate_artifact_inputs(inputs or {}, graph.ancestors(node_id), report, context)


def validate_transitions(data: JsonDict, node_ids: set[str], report: ValidationReport) -> None:
    transitions = data.get("transitions")
    if transitions in (None, []):
        if len(node_ids) > 1:
            report.warn("workflow.transitions is empty; linear transitions will be derived from nodes order.")
        return
    if not isinstance(transitions, list):
        report.error("workflow.transitions must be a list.")
        return

    initial = data.get("initial", "")
    if initial and (not isinstance(initial, str) or initial not in node_ids):
        report.error("workflow.initial must reference an existing node id.")

    for index, transition in enumerate(transitions):
        context = f"transition[{index}]"
        if not isinstance(transition, dict):
            report.error(f"{context} must be an object.")
            continue
        from_id = transition.get("from")
        to_id = transition.get("to")
        when = transition.get("when", "always")
        if not isinstance(from_id, str) or from_id not in node_ids:
            report.error(f"{context}.from must reference an existing node id.")
        if not isinstance(to_id, str) or to_id not in node_ids:
            report.error(f"{context}.to must reference an existing node id.")
        if when not in ALLOWED_WHEN:
            report.error(f"{context}.when must be one of {sorted(ALLOWED_WHEN)}.")

    try:
        graph = WorkflowGraph.from_workflow(WorkflowSpec.from_dict(data))
    except Exception as exc:
        report.error(f"workflow transitions cannot be parsed: {exc}")
        return

    if graph.initial and graph.initial not in node_ids:
        report.error("workflow.initial must reference an existing node id.")

    unreachable = node_ids - graph.collect_reachable_from(graph.initial)
    if unreachable:
        report.warn(
            "Some nodes are unreachable from workflow.initial: "
            + ", ".join(sorted(unreachable))
        )


def validate_skill_data(skill: JsonDict, report: ValidationReport) -> None:
    if not isinstance(skill, dict):
        report.error("Skill root must be an object.")
        return
    require_string(skill, "id", "skill", report)
    require_string(skill, "name", "skill", report, warning_only=True)
    require_string(skill, "goal", "skill", report, warning_only=True)
    output = skill.get("output", {})
    if output is not None and not isinstance(output, dict):
        report.error("skill.output must be an object.")
    elif not (output or {}).get("primary"):
        report.warn("skill.output.primary is not set.")
    quality = skill.get("quality", [])
    if quality is not None and not isinstance(quality, list):
        report.error("skill.quality must be a list.")
    executor = skill.get("executor", "")
    if executor and executor not in {"mock", "agent", "skill", "openai"}:
        report.warn(f"skill.executor has unknown value: {executor}")


def validate_skill_reference(
    store: WorkflowStore,
    skill_id: str,
    skill_dirs: list[Path],
    report: ValidationReport,
    context: str,
) -> None:
    try:
        skill = store.load_skill(skill_id, skill_dirs)
    except Exception as exc:
        report.error(f"{context}.skill `{skill_id}` cannot be loaded: {exc}")
        return
    if not skill.goal.strip():
        report.warn(f"skill[{skill_id}].goal is empty.")
    if not skill.output:
        report.warn(f"skill[{skill_id}].output is empty.")
    if not skill.quality:
        report.warn(f"skill[{skill_id}].quality is empty.")


def validate_artifact_inputs(
    inputs: JsonDict,
    ancestors: set[str],
    report: ValidationReport,
    context: str,
) -> None:
    for input_name, value in inputs.items():
        if isinstance(value, str) and value.startswith("artifact."):
            source = value.removeprefix("artifact.")
            if not source:
                report.error(f"{context}.inputs.{input_name} has an empty artifact reference.")
            elif source not in ancestors:
                report.error(
                    f"{context}.inputs.{input_name} references `{source}`, which is not an upstream node."
                )


def require_string(
    data: JsonDict,
    key: str,
    context: str,
    report: ValidationReport,
    warning_only: bool = False,
) -> None:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return
    message = f"{context}.{key} must be a non-empty string."
    if warning_only:
        report.warn(message)
    else:
        report.error(message)

