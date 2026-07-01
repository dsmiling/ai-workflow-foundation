from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .agent_providers import inspect_agent_provider, is_acp_provider, normalize_agent_provider
from .assist_workspace import append_workflow_assist_messages, load_workflow_assist_session, stream_workflow_assist_acp
from .agents import extract_json_object, normalize_generate_messages
from .skills import list_skills
from .storage import WorkflowStore
from .validation import ValidationReport, validate_workflow_data
from .workflows import find_workflow_path

JsonDict = dict[str, object]

NO_WORKFLOW_CHANGE_FALLBACK = (
    "这次没有产生可应用的工作流修改。"
    "若要改节点配置，请说明具体字段，例如：@requirement_analysis 把 raw_requirement 改成你的需求描述。"
)
ALLOWED_NODE_TYPES = {"ai", "skill", "tool", "review", "route"}
ALLOWED_APPROVAL_MODES = {"auto", "ai", "human"}
ALLOWED_APPROVAL_LEVELS = {"optional", "required"}

_EDIT_ACTION_PATTERN = re.compile(
    r"改成|改为|修改为|换成|添加|删除|移除|新增|调整|设置|"
    r"rename|add|remove|delete|insert|update|set|change",
    re.IGNORECASE,
)


def _slugify_node_id(value: str, fallback: str = "node") -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return slug or fallback


def _skill_catalog(store: WorkflowStore, skill_dirs: list[Path]) -> list[JsonDict]:
    items: list[JsonDict] = []
    for item in list_skills(store, skill_dirs):
        items.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "goal": item.get("goal", ""),
                "source": item.get("source"),
            }
        )
    return items


def _example_workflow(store: WorkflowStore) -> JsonDict | None:
    try:
        path = find_workflow_path(store, "simple_foundation")
        return store.read_json(path)
    except FileNotFoundError:
        return None


def _canonical_workflow_snapshot(workflow: JsonDict) -> str:
    return json.dumps(workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_assist_workflows(
    store: WorkflowStore,
    skill_dirs: list[Path],
    *,
    baseline: JsonDict | None,
    candidate: JsonDict,
    refine: bool = False,
) -> tuple[JsonDict, JsonDict]:
    base_norm: JsonDict = {}
    cand_norm: JsonDict = {}
    if isinstance(baseline, dict) and baseline:
        try:
            base_norm = normalize_generated_workflow(
                store,
                {"workflow": baseline},
                skill_dirs,
                draft=baseline,
                refine=refine,
            )["workflow"]
        except ValueError:
            base_norm = baseline
    if isinstance(candidate, dict) and candidate:
        try:
            cand_norm = normalize_generated_workflow(
                store,
                {"workflow": candidate},
                skill_dirs,
                draft=baseline if isinstance(baseline, dict) else None,
                refine=refine,
            )["workflow"]
        except ValueError:
            cand_norm = candidate
    return base_norm, cand_norm


def workflow_draft_changed(
    store: WorkflowStore,
    skill_dirs: list[Path],
    *,
    baseline: JsonDict | None,
    candidate: JsonDict,
    refine: bool = False,
) -> bool:
    if not isinstance(candidate, dict) or not candidate:
        return False
    if not isinstance(baseline, dict) or not baseline:
        return True
    base_norm, cand_norm = _normalize_assist_workflows(
        store,
        skill_dirs,
        baseline=baseline,
        candidate=candidate,
        refine=refine,
    )
    if not cand_norm:
        return False
    if not base_norm:
        return True
    return _canonical_workflow_snapshot(base_norm) != _canonical_workflow_snapshot(cand_norm)


def _transition_key(item: JsonDict) -> tuple[str, str, str]:
    return (
        str(item.get("from") or ""),
        str(item.get("to") or ""),
        str(item.get("when") or "always"),
    )


def _append_dict_field_changes(
    changes: list[JsonDict],
    *,
    node_id: str,
    prefix: str,
    old: dict[str, object],
    new: dict[str, object],
) -> None:
    for key in sorted(set(old) | set(new)):
        old_has = key in old
        new_has = key in new
        old_value = old.get(key)
        new_value = new.get(key)
        if isinstance(old_value, str) and isinstance(new_value, str):
            before = old_value if old_has else ""
            after = new_value if new_has else ""
        else:
            before = json.dumps(old_value, ensure_ascii=False, sort_keys=True) if old_has else ""
            after = json.dumps(new_value, ensure_ascii=False, sort_keys=True) if new_has else ""
        if before == after:
            continue
        changes.append(
            {
                "kind": "node_field",
                "node_id": node_id,
                "path": f"{prefix}.{key}",
                "before": before,
                "after": after,
            }
        )


def compute_workflow_changes(baseline: JsonDict | None, candidate: JsonDict) -> list[JsonDict]:
    base = baseline if isinstance(baseline, dict) else {}
    cand = candidate if isinstance(candidate, dict) else {}
    changes: list[JsonDict] = []

    for field in ("name", "id", "initial", "workspace_root"):
        before = str(base.get(field) or "")
        after = str(cand.get(field) or "")
        if before != after:
            changes.append(
                {
                    "kind": "workflow",
                    "path": field,
                    "before": before,
                    "after": after,
                }
            )

    base_nodes: dict[str, JsonDict] = {}
    for item in base.get("nodes") or []:
        if isinstance(item, dict) and item.get("id"):
            base_nodes[str(item["id"])] = item
    cand_nodes: dict[str, JsonDict] = {}
    for item in cand.get("nodes") or []:
        if isinstance(item, dict) and item.get("id"):
            cand_nodes[str(item["id"])] = item

    for node_id in sorted(set(base_nodes) - set(cand_nodes)):
        changes.append({"kind": "node_removed", "node_id": node_id})
    for node_id in sorted(set(cand_nodes) - set(base_nodes)):
        changes.append({"kind": "node_added", "node_id": node_id})

    scalar_fields = ("name", "type", "skill", "executor", "agent_ref")
    dict_fields = ("inputs", "outputs", "approval", "review", "params")
    for node_id in sorted(set(base_nodes) & set(cand_nodes)):
        old = base_nodes[node_id]
        new = cand_nodes[node_id]
        for field in scalar_fields:
            before = str(old.get(field) or "")
            after = str(new.get(field) or "")
            if before != after:
                changes.append(
                    {
                        "kind": "node_field",
                        "node_id": node_id,
                        "path": field,
                        "before": before,
                        "after": after,
                    }
                )
        for field in dict_fields:
            old_val = old.get(field) if isinstance(old.get(field), dict) else {}
            new_val = new.get(field) if isinstance(new.get(field), dict) else {}
            _append_dict_field_changes(
                changes,
                node_id=node_id,
                prefix=field,
                old=old_val,
                new=new_val,
            )

    base_trans = {
        _transition_key(item): item
        for item in (base.get("transitions") or [])
        if isinstance(item, dict)
    }
    cand_trans = {
        _transition_key(item): item
        for item in (cand.get("transitions") or [])
        if isinstance(item, dict)
    }
    for key in sorted(set(cand_trans) - set(base_trans)):
        changes.append(
            {
                "kind": "transition_added",
                "from": key[0],
                "to": key[1],
                "when": key[2],
            }
        )
    for key in sorted(set(base_trans) - set(cand_trans)):
        changes.append(
            {
                "kind": "transition_removed",
                "from": key[0],
                "to": key[1],
                "when": key[2],
            }
        )
    return changes


def _clip_change_value(value: str, *, limit: int = 48) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _format_change_delta(path: str, before: str, after: str) -> str:
    before_text = _clip_change_value(before)
    after_text = _clip_change_value(after)
    if not before_text and after_text:
        return f"+ {path}: {after_text}"
    if before_text and not after_text:
        return f"- {path}: {before_text}"
    return f"△ {path}: {before_text} → {after_text}"


def format_workflow_changes(changes: list[JsonDict]) -> str:
    if not changes:
        return "无结构变更"
    lines: list[str] = []
    for item in changes:
        kind = str(item.get("kind") or "")
        if kind == "workflow":
            path = f"workflow.{item.get('path')}"
            lines.append(_format_change_delta(path, str(item.get("before") or ""), str(item.get("after") or "")))
        elif kind == "node_added":
            lines.append(f"+ nodes/{item.get('node_id')}")
        elif kind == "node_removed":
            lines.append(f"- nodes/{item.get('node_id')}")
        elif kind == "node_field":
            path = f"nodes/{item.get('node_id')}/{item.get('path')}"
            lines.append(_format_change_delta(path, str(item.get("before") or ""), str(item.get("after") or "")))
        elif kind == "transition_added":
            when = str(item.get("when") or "always")
            lines.append(f"+ transitions/{item.get('from')}→{item.get('to')} [{when}]")
        elif kind == "transition_removed":
            when = str(item.get("when") or "always")
            lines.append(f"- transitions/{item.get('from')}→{item.get('to')} [{when}]")
    return "\n".join(lines)


def has_workflow_edit_intent(text: str, *, focus_ids: list[str] | None = None) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if extract_node_rename_intent(stripped, focus_ids):
        return True
    if _extract_rename_target(stripped):
        return True
    if _EDIT_ACTION_PATTERN.search(stripped):
        return True
    if extract_mention_ids_from_text(stripped) and len(stripped) > 8:
        return True
    return False


def resolve_assist_focus_detail(
    text: str,
    *,
    focus_ids: list[str] | None = None,
) -> str:
    """Return ACP focus attachment mode: full | compact | none."""
    if extract_mention_ids_from_text(text):
        return "full"
    if focus_ids and has_workflow_edit_intent(text, focus_ids=focus_ids):
        return "compact"
    return "none"


def _build_assist_done_event(
    store: WorkflowStore,
    skill_dirs: list[Path],
    *,
    summary: str,
    baseline: JsonDict | None,
    workflow: JsonDict,
    refine: bool,
    reply: str = "",
    hint: str = "",
    **extra: object,
) -> JsonDict:
    base_norm, cand_norm = _normalize_assist_workflows(
        store,
        skill_dirs,
        baseline=baseline,
        candidate=workflow,
        refine=refine,
    )
    changed = bool(cand_norm) and (
        not base_norm or _canonical_workflow_snapshot(base_norm) != _canonical_workflow_snapshot(cand_norm)
    )
    changes = compute_workflow_changes(base_norm, cand_norm) if changed else []
    if changed:
        message = format_workflow_changes(changes)
        payload_summary = summary
    else:
        message = (reply or summary or "").strip() or NO_WORKFLOW_CHANGE_FALLBACK
        payload_summary = message
    payload: JsonDict = {
        "type": "done",
        "message": message,
        "summary": payload_summary,
        "reply": (reply or "").strip(),
        "changes": changes,
        "changed": changed,
        "output": "",
        "percent": 100,
        **extra,
    }
    if hint.strip():
        payload["hint"] = hint.strip()
    if changed:
        payload["workflow"] = cand_norm or workflow
    return payload


def normalize_workflow_draft(draft: object | None) -> JsonDict:
    if not isinstance(draft, dict):
        return {}
    payload = {
        "id": str(draft.get("id") or "").strip(),
        "name": str(draft.get("name") or "").strip(),
        "workspace_root": str(draft.get("workspace_root") or "").strip(),
        "initial": str(draft.get("initial") or "").strip(),
        "nodes": draft.get("nodes") if isinstance(draft.get("nodes"), list) else None,
        "transitions": draft.get("transitions") if isinstance(draft.get("transitions"), list) else None,
    }
    return {key: value for key, value in payload.items() if value not in ("", None, [])}


def _default_skill_id(skill_catalog: list[JsonDict]) -> str:
    for source in ("workspace", "example"):
        for item in skill_catalog:
            if item.get("source") == source and item.get("id"):
                return str(item["id"])
    if skill_catalog:
        return str(skill_catalog[0].get("id") or "")
    return ""


def _normalize_node(
    node: object,
    *,
    index: int,
    skill_ids: set[str],
    default_skill: str,
    draft_nodes: dict[str, JsonDict],
) -> JsonDict:
    if not isinstance(node, dict):
        node = {}
    draft = {}
    raw_id = str(node.get("id") or "").strip()
    if raw_id and raw_id in draft_nodes:
        draft = draft_nodes[raw_id]
    node_id = _slugify_node_id(str(node.get("id") or draft.get("id") or f"node_{index + 1}"))
    node_type = str(node.get("type") or draft.get("type") or "ai").strip()
    if node_type not in ALLOWED_NODE_TYPES:
        node_type = "ai"
    skill = str(node.get("skill") or draft.get("skill") or "").strip()
    if node_type in {"ai", "skill"}:
        if skill not in skill_ids:
            skill = default_skill
    else:
        skill = skill if skill in skill_ids else ""
    approval_raw = node.get("approval") if isinstance(node.get("approval"), dict) else draft.get("approval")
    approval = approval_raw if isinstance(approval_raw, dict) else {}
    mode = str(approval.get("mode") or "auto").strip()
    level = str(approval.get("level") or "optional").strip()
    if mode not in ALLOWED_APPROVAL_MODES:
        mode = "auto"
    if level not in ALLOWED_APPROVAL_LEVELS:
        level = "optional"
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else draft.get("inputs")
    outputs = node.get("outputs") if isinstance(node.get("outputs"), dict) else draft.get("outputs")
    normalized: JsonDict = {
        "id": node_id,
        "name": str(node.get("name") or draft.get("name") or node_id).strip() or node_id,
        "type": node_type,
        "inputs": inputs if isinstance(inputs, dict) else {},
        "approval": {"mode": mode, "level": level},
    }
    if node_type in {"ai", "skill"} and skill:
        normalized["skill"] = skill
    if node_type != "review":
        out = outputs if isinstance(outputs, dict) else {}
        primary = str(out.get("primary") or f"{node_id}.md").strip() or f"{node_id}.md"
        normalized["outputs"] = {"primary": primary}
    review = node.get("review") if isinstance(node.get("review"), dict) else draft.get("review")
    if isinstance(review, dict) and node_type != "review":
        normalized["review"] = review
    params = node.get("params") if isinstance(node.get("params"), dict) else draft.get("params")
    if isinstance(params, dict) and params:
        normalized["params"] = params
    agent_ref = str(node.get("agent_ref") or draft.get("agent_ref") or "").strip()
    if agent_ref:
        normalized["agent_ref"] = agent_ref
    executor = str(node.get("executor") or draft.get("executor") or "").strip()
    if executor:
        normalized["executor"] = executor
    return normalized


def _ensure_unique_node_ids(nodes: list[JsonDict]) -> list[JsonDict]:
    seen: set[str] = set()
    result: list[JsonDict] = []
    for index, node in enumerate(nodes):
        node_id = str(node.get("id") or f"node_{index + 1}")
        if node_id in seen:
            suffix = 2
            while f"{node_id}_{suffix}" in seen:
                suffix += 1
            node_id = f"{node_id}_{suffix}"
            node = {**node, "id": node_id}
        seen.add(node_id)
        result.append(node)
    return result


def _sync_linear_transitions(workflow: JsonDict) -> None:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return
    node_ids = [str(node.get("id") or "") for node in nodes if isinstance(node, dict) and node.get("id")]
    transitions = workflow.get("transitions")
    custom: list[JsonDict] = []
    if isinstance(transitions, list):
        custom = [
            item
            for item in transitions
            if isinstance(item, dict) and str(item.get("when") or "") != "always"
        ]
    linear: list[JsonDict] = []
    for index in range(len(node_ids) - 1):
        linear.append({"from": node_ids[index], "to": node_ids[index + 1], "when": "always"})
    workflow["transitions"] = [*linear, *custom]
    workflow["initial"] = node_ids[0] if node_ids else ""


def normalize_generated_workflow(
    store: WorkflowStore,
    raw: JsonDict,
    skill_dirs: list[Path],
    *,
    draft: JsonDict | None = None,
    refine: bool = False,
) -> JsonDict:
    draft = draft if isinstance(draft, dict) else {}
    skill_catalog = _skill_catalog(store, skill_dirs)
    skill_ids = {str(item.get("id") or "") for item in skill_catalog if item.get("id")}
    default_skill = _default_skill_id(skill_catalog)

    payload = raw.get("workflow") if isinstance(raw.get("workflow"), dict) else raw
    if not isinstance(payload, dict):
        raise ValueError("Generated payload must include a workflow object.")

    draft_nodes: dict[str, JsonDict] = {}
    draft_node_list = draft.get("nodes")
    if isinstance(draft_node_list, list):
        for item in draft_node_list:
            if isinstance(item, dict) and item.get("id"):
                draft_nodes[str(item["id"])] = item

    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raw_nodes = draft.get("nodes") if isinstance(draft.get("nodes"), list) else []
    if not raw_nodes:
        raise ValueError("Generated workflow must contain at least one node.")

    nodes = [
        _normalize_node(
            node,
            index=index,
            skill_ids=skill_ids,
            default_skill=default_skill,
            draft_nodes=draft_nodes,
        )
        for index, node in enumerate(raw_nodes)
    ]
    nodes = _ensure_unique_node_ids(nodes)

    workflow_id = str(payload.get("id") or draft.get("id") or "").strip()
    if refine and draft.get("id"):
        workflow_id = str(draft.get("id"))
    if not workflow_id:
        workflow_id = "new_workflow"

    workflow: JsonDict = {
        "id": workflow_id,
        "name": str(payload.get("name") or draft.get("name") or workflow_id).strip() or workflow_id,
        "nodes": nodes,
    }
    workspace_root = str(payload.get("workspace_root") or draft.get("workspace_root") or "").strip()
    if workspace_root:
        workflow["workspace_root"] = workspace_root
    if isinstance(payload.get("transitions"), list):
        workflow["transitions"] = payload["transitions"]
    elif isinstance(draft.get("transitions"), list):
        workflow["transitions"] = draft["transitions"]
    else:
        workflow["transitions"] = []
    initial = str(payload.get("initial") or draft.get("initial") or "").strip()
    if initial:
        workflow["initial"] = initial
    _sync_linear_transitions(workflow)

    report = ValidationReport()
    validate_workflow_data(store, workflow, report, skill_dirs)
    if not report.ok:
        raise ValueError("; ".join(report.errors))

    summary = str(raw.get("summary") or payload.get("summary") or "").strip()
    return {
        "workflow": workflow,
        "summary": summary,
    }


def normalize_focus_node_ids(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        node_id = str(item or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        result.append(node_id)
    return result


def _focus_nodes_from_draft(draft: JsonDict | None, focus_node_ids: list[str]) -> list[JsonDict]:
    if not focus_node_ids or not isinstance(draft, dict):
        return []
    nodes = draft.get("nodes")
    if not isinstance(nodes, list):
        return []
    by_id = {
        str(node.get("id") or ""): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    return [by_id[node_id] for node_id in focus_node_ids if node_id in by_id]


def _collect_provider_output(events: Iterator[dict[str, object]]) -> tuple[str, list[JsonDict]]:
    streamed: list[JsonDict] = []
    output = ""
    for event in events:
        kind = str(event.get("kind") or "")
        if kind == "progress":
            streamed.append(
                {
                    "type": "progress",
                    "stage": str(event.get("stage") or "llm"),
                    "message": str(event.get("message") or "生成中..."),
                    "percent": int(event.get("percent") or 20),
                }
            )
        elif kind == "log":
            streamed.append({"type": "log", "line": str(event.get("text") or "")})
        elif kind == "complete":
            output = str(event.get("output") or "")
    return output, streamed


def _build_workflow_assist_repair_prompt(original_prompt: str, output: str) -> str:
    clipped = output.strip()
    if len(clipped) > 4000:
        clipped = f"{clipped[:4000]}\n... (truncated)"
    return "\n".join(
        [
            original_prompt,
            "",
            "IMPORTANT: Your previous answer was NOT valid JSON and could not be applied.",
            "Return ONLY one JSON object. No markdown, no tables, no prose before or after the JSON.",
            "If you need a json code fence, use exactly one ```json fence wrapping the object.",
            "",
            "Previous invalid response:",
            clipped,
        ]
    ).rstrip()


_SCHEMA_EXAMPLE_MARKERS = (
    "xxx 或固定值",
    "literal text or artifact",
    "node_id_snake_case",
    "artifact.other_node_id",
    "skill_id (required",
    "显示名称",
    "workflow_id",
    "节点名",
)


def _draft_for_simple_edit(draft: JsonDict | None, draft_payload: JsonDict) -> JsonDict:
    if isinstance(draft, dict) and isinstance(draft.get("nodes"), list) and draft["nodes"]:
        return draft
    if isinstance(draft_payload.get("nodes"), list) and draft_payload["nodes"]:
        return draft_payload
    if isinstance(draft, dict):
        return draft
    return draft_payload


def _payload_looks_like_schema_example(raw: JsonDict) -> bool:
    blob = json.dumps(raw, ensure_ascii=False).lower()
    return any(marker.lower() in blob for marker in _SCHEMA_EXAMPLE_MARKERS)


def _extract_assist_payload(output: str) -> JsonDict | None:
    try:
        raw = extract_json_object(output)
    except ValueError:
        return None
    if _payload_looks_like_schema_example(raw):
        return None
    payload = raw.get("workflow") if isinstance(raw.get("workflow"), dict) else raw
    if not isinstance(payload, dict):
        return None
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    return raw


def _extract_rename_target(text: str) -> str | None:
    patterns = [
        r"把(?:当前)?工作流(?:的)?(?:名字|名称)\s*(?:改成|改为|修改为|换成)\s*(.+)$",
        r"(?:工作流)?(?:名字|名称).{0,16}?(?:改成|改为|修改为|换成)\s*(.+)$",
        r"(?:rename(?:\s+workflow)?(?:\s+name)?\s+to)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.strip(), re.IGNORECASE)
        if not match:
            continue
        new_name = match.group(1).strip().strip("「」\"'").rstrip("。.")
        if new_name:
            return new_name
    return None


def extract_mention_ids_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in re.finditer(r"@([a-zA-Z0-9_]+)", text):
        node_id = match.group(1).strip()
        if node_id and node_id not in seen:
            seen.add(node_id)
            result.append(node_id)
    return result


def extract_node_rename_intent(text: str, focus_ids: list[str] | None = None) -> tuple[str, str] | None:
    focus = normalize_focus_node_ids(focus_ids) or extract_mention_ids_from_text(text)
    stripped = text.strip()
    patterns = [
        r"(?:@)?(?P<node>[a-zA-Z0-9_]+).{0,48}?(?:显示名|节点名|节点名称|名称).{0,24}?(?:改成|改为|修改为|换成)\s*[「\"']?(?P<name>[^「」\"'\n。]+?)[」\"']?\s*$",
        r"(?:把|将).{0,16}?(?:@)?(?P<node>[a-zA-Z0-9_]+).{0,32}?(?:显示名|节点名|节点名称|名称).{0,24}?(?:改成|改为|修改为|换成)\s*[「\"']?(?P<name>[^「」\"'\n。]+?)[」\"']?\s*$",
        r"(?:显示名|节点名|节点名称).{0,24}?(?:由|从).{0,48}?(?:改为|改成|修改为)\s*[「\"']?(?P<name>[^「」\"'\n。]+?)[」\"']?\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, stripped, re.IGNORECASE)
        if not match:
            continue
        groups = match.groupdict()
        new_name = str(groups.get("name") or "").strip().strip("「」\"'").rstrip("。.")
        if not new_name:
            continue
        node_id = str(groups.get("node") or "").strip()
        if node_id:
            return node_id, new_name
        if len(focus) == 1:
            return focus[0], new_name
    return None


def _try_simple_node_rename(
    description: str,
    draft: JsonDict,
    *,
    focus_ids: list[str] | None = None,
) -> JsonDict | None:
    intent = extract_node_rename_intent(description, focus_ids)
    if not intent:
        return None
    node_id, new_name = intent
    workflow = json.loads(json.dumps(draft, ensure_ascii=False))
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if isinstance(node, dict) and str(node.get("id") or "") == node_id:
            node["name"] = new_name
            return {"summary": "", "workflow": workflow}
    return None


def reconcile_assist_workflow(
    baseline: JsonDict,
    candidate: JsonDict,
    *,
    focus_node_ids: list[str],
    rename_only_node_id: str | None = None,
) -> JsonDict:
    if not focus_node_ids:
        return candidate
    if not isinstance(baseline, dict) or not baseline:
        return candidate
    result = json.loads(json.dumps(candidate, ensure_ascii=False))
    focus_set = set(focus_node_ids)
    base_by_id = {
        str(node.get("id") or ""): node
        for node in (baseline.get("nodes") or [])
        if isinstance(node, dict) and node.get("id")
    }
    merged_nodes: list[JsonDict] = []
    for node in result.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if node_id not in focus_set and node_id in base_by_id:
            merged_nodes.append(json.loads(json.dumps(base_by_id[node_id], ensure_ascii=False)))
            continue
        if rename_only_node_id and node_id == rename_only_node_id and node_id in base_by_id:
            merged = json.loads(json.dumps(base_by_id[node_id], ensure_ascii=False))
            new_name = str(node.get("name") or "").strip()
            if new_name:
                merged["name"] = new_name
            merged_nodes.append(merged)
            continue
        merged_nodes.append(node)
    result["nodes"] = merged_nodes
    for key in ("id", "name", "initial", "workspace_root", "transitions"):
        if key in baseline:
            result[key] = json.loads(json.dumps(baseline[key], ensure_ascii=False))
    return result


def _try_simple_workflow_edit(
    description: str,
    draft: JsonDict,
    *,
    focus_ids: list[str] | None = None,
) -> JsonDict | None:
    if not draft:
        return None
    text = description.strip()
    if not text:
        return None
    node_rename = _try_simple_node_rename(description, draft, focus_ids=focus_ids)
    if node_rename is not None:
        return node_rename
    new_name = _extract_rename_target(text)
    if new_name:
        workflow = json.loads(json.dumps(draft, ensure_ascii=False))
        workflow["name"] = new_name
        return {
            "summary": f"已将工作流名称改为「{new_name}」。",
            "workflow": workflow,
        }
    return None


def _normalize_assist_result(
    store: WorkflowStore,
    raw: JsonDict,
    skill_dirs: list[Path],
    *,
    draft: JsonDict | None,
    refine: bool,
) -> JsonDict:
    return normalize_generated_workflow(
        store,
        raw,
        skill_dirs,
        draft=draft,
        refine=refine,
    )


def build_workflow_assist_prompt(
    description: str,
    *,
    draft: JsonDict | None = None,
    skills: list[JsonDict] | None = None,
    example: JsonDict | None = None,
    messages: list[JsonDict] | None = None,
    selected_node_id: str | None = None,
    focus_node_ids: list[str] | None = None,
) -> str:
    skill_lines = []
    for item in skills or []:
        skill_lines.append(
            f"- {item.get('id')}: {item.get('name')} · {str(item.get('goal') or '')[:120]}"
        )
    example_block = json.dumps(example, ensure_ascii=False, indent=2) if example else "{}"
    lines = [
        "You edit AI Workflow Foundation workflow JSON for the user.",
        "Return ONLY one JSON object. Do not explain workflow format, do not use markdown tables, and do not add prose.",
        "If you must use a fence, wrap the JSON in a single ```json code block and nothing else.",
        "",
        "Response schema:",
        "{",
        '  "summary": "用中文简要说明本次修改（2-5 句）",',
        '  "workflow": {',
        '    "id": "workflow_id",',
        '    "name": "显示名称",',
        '    "workspace_root": "",',
        '    "initial": "first_node_id",',
        '    "transitions": [{"from":"a","to":"b","when":"always|approved|rejected"}],',
        '    "nodes": [',
        "      {",
        '        "id": "node_id_snake_case",',
        '        "name": "节点名",',
        '        "type": "ai|skill|review|tool|route",',
        '        "skill": "skill_id (required for ai/skill nodes)",',
        '        "inputs": {"param": "literal text or artifact.other_node_id"},',
        '        "outputs": {"primary": "artifact.md"},',
        '        "approval": {"mode": "auto|ai|human", "level": "optional|required"}',
        "      }",
        "    ]",
        "  }",
        "}",
        "",
        "Rules:",
        "- Prefer type=ai nodes with valid skill ids from the catalog below.",
        "- inputs values are either literal strings or artifact.<upstream_node_id> references.",
        "- For linear pipelines, use transitions with when=always between consecutive nodes.",
        "- Use review nodes with type=review and approval.mode=human when human gate is needed.",
        "- Keep workflow.id stable when refining an existing draft unless user asks to rename.",
        "- Node ids must be unique snake_case.",
        "- Return the complete final workflow object, not a patch.",
        "",
        "Available skills:",
        "\n".join(skill_lines) if skill_lines else "(none)",
        "",
        "Example workflow:",
        example_block,
    ]
    if draft:
        lines.extend(
            [
                "",
                "Current workflow draft (refine instead of replacing blindly):",
                json.dumps(draft, ensure_ascii=False, indent=2),
            ]
        )
    focus_ids = normalize_focus_node_ids(focus_node_ids)
    focus_nodes = _focus_nodes_from_draft(draft, focus_ids)
    if focus_nodes:
        lines.extend(
            [
                "",
                "Explicitly mentioned focus nodes (prioritize edits here unless user asks to change the whole workflow):",
            ]
        )
        for node in focus_nodes:
            lines.append(json.dumps(node, ensure_ascii=False, indent=2))
    if selected_node_id and selected_node_id not in focus_ids:
        lines.extend(["", f"User is currently viewing node in the canvas: {selected_node_id}"])
    elif selected_node_id and not focus_nodes:
        lines.extend(["", f"User is currently focused on node: {selected_node_id}"])
    if messages:
        lines.extend(["", "Conversation history:"])
        for item in messages:
            role = "User" if item["role"] == "user" else "Assistant"
            lines.append(f"{role}: {item['content']}")
    lines.extend(
        [
            "",
            "Latest user request:",
            description.strip(),
            "",
            "Requirements:",
            "- If a draft exists, preserve valid structure and only change what the user asks.",
            "- summary must explain changes in concise Chinese.",
            "- Ensure every ai/skill node has a valid skill from the catalog.",
            "- Ensure artifact references only point to upstream nodes in the graph.",
            "- When focus nodes are provided, change them first; keep unrelated nodes stable.",
        ]
    )
    return "\n".join(lines).rstrip()


def _persist_workflow_assist_turn(
    store: WorkflowStore,
    *,
    workflow_id: str,
    session_id: str | None,
    user_text: str,
    assistant_text: str,
    pending_summary: str = "",
) -> None:
    wf_id = workflow_id.strip()
    if not wf_id:
        return
    sid = (session_id or "").strip()
    if not sid:
        sid = str(load_workflow_assist_session(store, wf_id).get("session_id") or "").strip()
    if not sid:
        return
    append_workflow_assist_messages(
        store,
        workflow_id=wf_id,
        session_id=sid,
        user_text=user_text,
        assistant_text=assistant_text,
        pending_summary=pending_summary,
    )


def stream_workflow_assist(
    store: WorkflowStore,
    skill_dirs: list[Path],
    *,
    description: str,
    provider_id: str | None = None,
    draft: JsonDict | None = None,
    messages: list[JsonDict] | None = None,
    selected_node_id: str | None = None,
    focus_node_ids: list[str] | None = None,
    workflow_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[JsonDict]:
    text = description.strip()
    if not text:
        raise ValueError("description is required.")
    draft_payload = normalize_workflow_draft(draft)
    prompt_draft = draft if isinstance(draft, dict) else (draft_payload or None)
    edit_draft = _draft_for_simple_edit(prompt_draft, draft_payload)
    refine = bool(draft_payload) or bool(messages)
    focus_ids = normalize_focus_node_ids(focus_node_ids)
    simple = _try_simple_workflow_edit(text, edit_draft, focus_ids=focus_ids)
    if simple is not None:
        yield {
            "type": "progress",
            "stage": "local",
            "message": "识别为简单修改，直接更新草稿...",
            "percent": 60,
        }
        try:
            result = _normalize_assist_result(
                store,
                simple,
                skill_dirs,
                draft=draft_payload or edit_draft,
                refine=True,
            )
        except ValueError as exc:
            yield {"type": "error", "message": f"本地应用修改失败：{exc}"}
            return
        summary = str(result.get("summary") or "").strip()
        wf_id = (workflow_id or str(draft_payload.get("id") or "")).strip() or f"workflow_{uuid4().hex[:8]}"
        done_event = _build_assist_done_event(
            store,
            skill_dirs,
            summary=summary,
            baseline=edit_draft or draft_payload or None,
            workflow=result["workflow"],
            refine=True,
            workflow_id=wf_id,
            session_id=session_id or "",
        )
        _persist_workflow_assist_turn(
            store,
            workflow_id=wf_id,
            session_id=session_id,
            user_text=text,
            assistant_text=str(done_event.get("message") or ""),
            pending_summary=summary if done_event.get("changed") else "",
        )
        yield done_event
        return
    provider = normalize_agent_provider(provider_id or "cursor-agent-acp")
    if not is_acp_provider(provider):
        raise ValueError("工作流助手仅支持 cursor-agent-acp 或 codex-agent-acp。")
    inspection = inspect_agent_provider(provider)
    if not inspection["ready"]:
        raise ValueError(str(inspection["detail"]))
    wf_id = (workflow_id or str(draft_payload.get("id") or "")).strip() or f"workflow_{uuid4().hex[:8]}"
    baseline_draft = edit_draft or draft_payload or (prompt_draft if isinstance(prompt_draft, dict) else None)
    rename_intent = extract_node_rename_intent(text, focus_ids)
    rename_only_node_id = rename_intent[0] if rename_intent else None
    focus_detail = resolve_assist_focus_detail(text, focus_ids=focus_ids)
    mention_ids = extract_mention_ids_from_text(text)
    acp_focus_ids = mention_ids if mention_ids else focus_ids
    if focus_detail == "full" and mention_ids:
        focus_nodes = _focus_nodes_from_draft(
            baseline_draft if isinstance(baseline_draft, dict) else None,
            mention_ids,
        )
    else:
        focus_nodes = None
    focus_hint = ""
    if selected_node_id and focus_detail != "none":
        focus_hint = f"User is viewing node: {selected_node_id}"
    if focus_detail != "none" and acp_focus_ids:
        nodes_line = f"Focus nodes: {', '.join(acp_focus_ids)}"
        focus_hint = (focus_hint + f"\n{nodes_line}").strip() if focus_hint else nodes_line
    yield {
        "type": "progress",
        "stage": "prepare",
        "message": "准备 ACP 会话...",
        "percent": 8,
    }
    for event in stream_workflow_assist_acp(
        store,
        workflow_id=wf_id,
        provider_id=provider,
        description=text,
        draft=prompt_draft if isinstance(prompt_draft, dict) else draft_payload or None,
        session_id=session_id,
        focus_hint=focus_hint,
        focus_node_ids=acp_focus_ids,
        focus_nodes=focus_nodes,
        focus_detail=focus_detail,
    ):
        if event.get("type") == "session":
            yield event
            continue
        if event.get("type") == "log":
            yield event
            continue
        if event.get("type") == "assistant":
            yield event
            continue
        if event.get("type") == "progress":
            yield event
            continue
        if event.get("type") == "workspace_done":
            raw = {"summary": event.get("summary"), "workflow": event.get("workflow")}
            try:
                result = _normalize_assist_result(
                    store,
                    raw,
                    skill_dirs,
                    draft=draft_payload or edit_draft,
                    refine=refine,
                )
            except ValueError as exc:
                yield {"type": "error", "message": f"工作流草稿校验失败：{exc}"}
                return
            workflow = result["workflow"]
            if isinstance(baseline_draft, dict) and baseline_draft and focus_ids:
                workflow = reconcile_assist_workflow(
                    baseline_draft,
                    workflow,
                    focus_node_ids=focus_ids,
                    rename_only_node_id=rename_only_node_id,
                )
            summary = str(result.get("summary") or "").strip()
            reply = str(event.get("assistant_reply") or "").strip()
            done_event = _build_assist_done_event(
                store,
                skill_dirs,
                summary=summary,
                baseline=baseline_draft,
                workflow=workflow,
                refine=refine,
                reply=reply,
                session_id=event.get("session_id"),
                chat_id=event.get("chat_id"),
                workflow_id=wf_id,
            )
            _persist_workflow_assist_turn(
                store,
                workflow_id=wf_id,
                session_id=str(event.get("session_id") or session_id or ""),
                user_text=text,
                assistant_text=str(done_event.get("message") or reply or ""),
                pending_summary=summary if done_event.get("changed") else "",
            )
            yield done_event
            return
    raise RuntimeError("Workflow assist stream ended without done event.")
