from __future__ import annotations

import hashlib
from pathlib import Path

from .models import AssetRecord, ChangeItem, ExecutionResult, NodeSpec, SkillSpec


def artifact_kind_for_ref(ref: str) -> str:
    lower = ref.lower()
    if lower.endswith(".md"):
        return "markdown"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".txt"):
        return "text"
    return "other"


def normalize_artifact_ref(ref: str) -> str:
    if "/" not in ref:
        return f"artifacts/{ref}"
    return ref.replace("\\", "/")


def infer_summary(content: str, node: NodeSpec) -> str:
    stripped = content.strip()
    if not stripped:
        return f"{node.name} produced an empty artifact."
    for line in stripped.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:240]
    return f"{node.name} execution completed."


def build_execution_result(
    node: NodeSpec,
    content: str,
    primary_ref: str,
    *,
    structured_ref: str | None = None,
    action: str = "create",
    run_dir: Path | None = None,
) -> ExecutionResult:
    primary = normalize_artifact_ref(primary_ref)
    assets: list[AssetRecord] = []
    changes: list[ChangeItem] = []

    def add_asset(ref: str, summary: str) -> None:
        normalized = normalize_artifact_ref(ref)
        size = 0
        sha = ""
        if run_dir is not None:
            path = run_dir / normalized
            if path.exists():
                data = path.read_bytes()
                size = len(data)
                sha = hashlib.sha256(data).hexdigest()
        assets.append(
            AssetRecord(
                ref=normalized,
                kind=artifact_kind_for_ref(normalized),
                action=action,
                size=size,
                sha256=sha,
            )
        )
        changes.append(ChangeItem(action=action, target=normalized, summary=summary))

    primary_summary = "新增主产物" if action == "create" else "更新主产物"
    add_asset(primary, primary_summary)

    if structured_ref:
        structured_summary = "新增结构化侧车" if action == "create" else "更新结构化侧车"
        add_asset(structured_ref, structured_summary)

    return ExecutionResult(
        summary=infer_summary(content, node),
        assets=assets,
        changes=changes,
        primary_ref=primary,
    )


def synthesize_from_artifact(
    node_id: str,
    artifact_ref: str | None,
    *,
    run_dir: Path | None = None,
) -> ExecutionResult | None:
    if not artifact_ref:
        return None
    primary = normalize_artifact_ref(artifact_ref)
    size = 0
    sha = ""
    summary = f"Legacy artifact for {node_id}."
    if run_dir is not None:
        path = run_dir / primary
        if path.exists():
            data = path.read_bytes()
            size = len(data)
            sha = hashlib.sha256(data).hexdigest()
            try:
                text = data.decode("utf-8")
                for line in text.splitlines():
                    cleaned = line.strip().lstrip("#").strip()
                    if cleaned:
                        summary = cleaned[:240]
                        break
            except UnicodeDecodeError:
                summary = f"Binary artifact for {node_id}."
    asset = AssetRecord(
        ref=primary,
        kind=artifact_kind_for_ref(primary),
        action="create",
        size=size,
        sha256=sha,
    )
    change = ChangeItem(action="create", target=primary, summary="从历史 artifact 合成")
    return ExecutionResult(
        summary=summary,
        assets=[asset],
        changes=[change],
        primary_ref=primary,
    )


def structured_output_name(node: NodeSpec, skill: SkillSpec | None) -> str | None:
    structured = node.outputs.get("structured")
    if isinstance(structured, str) and structured.strip():
        return structured.strip()
    if skill and skill.output:
        skill_structured = skill.output.get("structured")
        if isinstance(skill_structured, str) and skill_structured.strip():
            return skill_structured.strip()
        if isinstance(skill_structured, dict):
            name = skill_structured.get("name")
            if isinstance(name, str) and name.strip():
                return name.replace("{node_id}", node.id)
    return None


def primary_output_name(node: NodeSpec, skill: SkillSpec | None) -> str:
    primary = node.outputs.get("primary")
    if isinstance(primary, str) and primary.strip():
        return primary.strip()
    if skill and skill.output:
        skill_primary = skill.output.get("primary")
        if isinstance(skill_primary, str) and skill_primary.strip():
            return skill_primary.strip()
        if isinstance(skill_primary, dict):
            name = skill_primary.get("name")
            if isinstance(name, str) and name.strip():
                return name.replace("{node_id}", node.id)
    return f"{node.id}.md"
