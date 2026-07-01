from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from .agent_providers import (
    AGENT_PROVIDER_SPECS,
    inspect_agent_provider,
    is_acp_provider,
    normalize_agent_provider,
    test_agent_provider,
)
from .agent_assist_workspace import stream_role_assist_message
from .storage import WorkflowStore

JsonDict = dict[str, Any]

IDENT_FIELDS = ("name", "role", "vibe")


def agents_path(store: WorkflowStore) -> Path:
    return store.aiwf / "agents.json"


def normalize_ident(data: object | None) -> JsonDict:
    source = data if isinstance(data, dict) else {}
    return {field: str(source.get(field) or "").strip() for field in IDENT_FIELDS}


def normalize_soul(agent: JsonDict) -> str:
    soul = str(agent.get("soul") or "").strip()
    if soul:
        return soul
    return str(agent.get("description") or "").strip()


def build_agent_context(agent: JsonDict) -> str:
    ident = normalize_ident(agent.get("ident"))
    soul = normalize_soul(agent)
    lines: list[str] = []
    ident_lines = [f"- {field}: {ident[field]}" for field in IDENT_FIELDS if ident[field]]
    if ident_lines:
        lines.extend(["## Agent Identity", "", *ident_lines, ""])
    if soul:
        lines.extend(["## Agent Soul", "", soul, ""])
    return "\n".join(lines).rstrip()


def agent_templates_dir(project_root: Path) -> Path:
    return project_root / "examples" / "agents"


def list_agent_templates(project_root: Path) -> list[JsonDict]:
    root = agent_templates_dir(project_root)
    if not root.exists():
        return []
    templates: list[JsonDict] = []
    for path in sorted(root.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = WorkflowStore.read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        template_id = str(data.get("template_id") or path.stem).strip()
        if not template_id:
            continue
        templates.append(
            {
                "template_id": template_id,
                "label": str(data.get("label") or template_id).strip(),
                "provider": str(data.get("provider") or "openai-api").strip(),
                "ident": normalize_ident(data.get("ident")),
                "soul": normalize_soul(data),
                "suggested_skills": list(data.get("suggested_skills") or []),
                "path": str(path),
            }
        )
    return templates


def load_custom_agents(store: WorkflowStore) -> list[JsonDict]:
    path = agents_path(store)
    if not path.exists():
        return []
    data = store.read_json(path)
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        return []
    return [item for item in agents if isinstance(item, dict) and item.get("id")]


def save_custom_agents(store: WorkflowStore, agents: list[JsonDict]) -> None:
    store.aiwf.mkdir(parents=True, exist_ok=True)
    store.write_json(agents_path(store), {"agents": agents})


def load_role_agent(store: WorkflowStore, agent_id: str) -> JsonDict | None:
    for item in load_custom_agents(store):
        if item.get("id") == agent_id:
            return item
    return None


def builtin_agent_entries() -> list[JsonDict]:
    entries: list[JsonDict] = []
    for spec in AGENT_PROVIDER_SPECS:
        entries.append(
            {
                "id": spec.id,
                "label": spec.label,
                "provider": spec.id,
                "kind": spec.kind,
                "description": spec.description,
                "requires": list(spec.requires),
                "source": "builtin",
                "tier": "provider",
                "editable": False,
            }
        )
    return entries


def resolve_agent_provider_id(store: WorkflowStore, agent_id: str) -> str:
    for item in load_custom_agents(store):
        if item.get("id") == agent_id:
            provider = item.get("provider")
            if isinstance(provider, str) and provider.strip():
                return normalize_agent_provider(provider)
    normalized = normalize_agent_provider(agent_id)
    known = {spec.id for spec in AGENT_PROVIDER_SPECS}
    if normalized in known:
        return normalized
    raise ValueError(f"Unknown agent: {agent_id}")


def enrich_agent_entry(store: WorkflowStore, entry: JsonDict) -> JsonDict:
    provider_id = str(entry.get("provider") or entry.get("id") or "")
    status = inspect_agent_provider(provider_id)
    enriched = dict(entry)
    enriched["provider"] = provider_id
    enriched["status"] = status["status"]
    enriched["ready"] = status["ready"]
    enriched["missing"] = status["missing"]
    enriched["status_detail"] = status["detail"]
    if entry.get("source") == "workspace":
        enriched["ident"] = normalize_ident(entry.get("ident"))
        enriched["soul"] = normalize_soul(entry)
    return enriched


def workspace_agent_entry(item: JsonDict) -> JsonDict:
    provider = item.get("provider") or item["id"]
    return {
        "id": item["id"],
        "label": item.get("label") or item["id"],
        "provider": provider,
        "kind": next(
            (spec.kind for spec in AGENT_PROVIDER_SPECS if spec.id == provider),
            "api",
        ),
        "ident": normalize_ident(item.get("ident")),
        "soul": normalize_soul(item),
        "requires": next(
            (list(spec.requires) for spec in AGENT_PROVIDER_SPECS if spec.id == provider),
            [],
        ),
        "source": "workspace",
        "tier": "role",
        "editable": True,
    }


def list_agents(store: WorkflowStore) -> list[JsonDict]:
    entries = builtin_agent_entries() + [workspace_agent_entry(item) for item in load_custom_agents(store)]
    return [enrich_agent_entry(store, entry) for entry in entries]


def list_role_agents(store: WorkflowStore) -> list[JsonDict]:
    return [entry for entry in list_agents(store) if entry.get("tier") == "role"]


def get_agent(store: WorkflowStore, agent_id: str) -> JsonDict:
    for entry in list_agents(store):
        if entry["id"] == agent_id:
            return entry
    raise FileNotFoundError(f"Agent not found: {agent_id}")


def save_agent(store: WorkflowStore, agent: JsonDict) -> JsonDict:
    agent_id = str(agent.get("id") or "").strip()
    if not agent_id:
        raise ValueError("Agent id is required.")
    provider = str(agent.get("provider") or "").strip()
    if not provider:
        raise ValueError("Agent provider is required.")
    normalize_agent_provider(provider)
    builtin_ids = {spec.id for spec in AGENT_PROVIDER_SPECS}
    if agent_id in builtin_ids:
        raise ValueError("Built-in agent ids cannot be overwritten.")
    label = str(agent.get("label") or agent_id).strip()
    soul = str(agent.get("soul") or "").strip()
    if not soul:
        soul = str(agent.get("description") or "").strip()
    record = {
        "id": agent_id,
        "label": label,
        "provider": normalize_agent_provider(provider),
        "ident": normalize_ident(agent.get("ident")),
        "soul": soul,
    }
    agents = [item for item in load_custom_agents(store) if item.get("id") != agent_id]
    agents.append(record)
    save_custom_agents(store, agents)
    return {"agent": enrich_agent_entry(store, {**workspace_agent_entry(record)})}


def delete_agent(store: WorkflowStore, agent_id: str) -> None:
    builtin_ids = {spec.id for spec in AGENT_PROVIDER_SPECS}
    if agent_id in builtin_ids:
        raise ValueError("Built-in agents cannot be deleted.")
    agents = [item for item in load_custom_agents(store) if item.get("id") != agent_id]
    if len(agents) == len(load_custom_agents(store)):
        raise FileNotFoundError(f"Agent not found: {agent_id}")
    save_custom_agents(store, agents)


def rename_agent(store: WorkflowStore, old_id: str, agent: JsonDict) -> JsonDict:
    new_id = str(agent.get("id") or "").strip()
    if not new_id:
        raise ValueError("Agent id is required.")
    if new_id == old_id:
        return save_agent(store, agent)
    get_agent(store, old_id)
    try:
        get_agent(store, new_id)
    except FileNotFoundError:
        pass
    else:
        raise ValueError(f"Agent id already exists: {new_id}")
    delete_agent(store, old_id)
    return save_agent(store, agent)


def run_agent_test(store: WorkflowStore, agent_id: str, prompt: str | None = None) -> JsonDict:
    provider_id = resolve_agent_provider_id(store, agent_id)
    result = test_agent_provider(provider_id, prompt=prompt)
    agent = get_agent(store, agent_id)
    return {
        "agent_id": agent_id,
        "provider": provider_id,
        "status": result["status"],
        "message": result["message"],
        "output": result.get("output", ""),
        "agent": agent,
    }


def _balanced_json_span(text: str, start: int = 0) -> tuple[int, int] | None:
    idx = text.find("{", start)
    while idx >= 0:
        depth = 0
        in_string = False
        escape = False
        for pos in range(idx, len(text)):
            ch = text[pos]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return idx, pos
        idx = text.find("{", idx + 1)
    return None


def _load_json_dict(candidate: str) -> JsonDict | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_json_object(text: str) -> JsonDict:
    content = text.strip()
    if not content:
        raise ValueError("LLM response was empty.")
    direct = _load_json_dict(content)
    if direct is not None:
        return direct
    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL | re.IGNORECASE):
        block = match.group(1).strip()
        block_direct = _load_json_dict(block)
        if block_direct is not None:
            return block_direct
        span = _balanced_json_span(block)
        if span is not None:
            parsed = _load_json_dict(block[span[0] : span[1] + 1])
            if parsed is not None:
                return parsed
    search_from = 0
    while True:
        span = _balanced_json_span(content, search_from)
        if span is None:
            break
        parsed = _load_json_dict(content[span[0] : span[1] + 1])
        if parsed is not None:
            return parsed
        search_from = span[0] + 1
    raise ValueError("LLM response did not contain a JSON object.")


def slugify_agent_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        slug = "custom"
    if not slug.startswith("role_"):
        slug = f"role_{slug}"
    return slug


def ensure_unique_agent_id(store: WorkflowStore, agent_id: str) -> str:
    builtin_ids = {spec.id for spec in AGENT_PROVIDER_SPECS}
    existing = {str(item.get("id") or "") for item in load_custom_agents(store)}
    candidate = agent_id
    if candidate not in builtin_ids and candidate not in existing:
        return candidate
    suffix = 2
    while f"{agent_id}_{suffix}" in existing or f"{agent_id}_{suffix}" in builtin_ids:
        suffix += 1
    return f"{agent_id}_{suffix}"


def agent_id_taken(store: WorkflowStore, agent_id: str) -> bool:
    builtin_ids = {spec.id for spec in AGENT_PROVIDER_SPECS}
    if agent_id in builtin_ids:
        return True
    return any(str(item.get("id") or "") == agent_id for item in load_custom_agents(store))


def normalize_generated_agent(
    store: WorkflowStore,
    raw: JsonDict,
    provider: str,
    *,
    draft: JsonDict | None = None,
    refine: bool = False,
) -> JsonDict:
    draft = draft if isinstance(draft, dict) else {}
    merged = {
        "id": str(raw.get("id") or draft.get("id") or "").strip(),
        "label": str(raw.get("label") or draft.get("label") or "").strip(),
        "provider": str(raw.get("provider") or draft.get("provider") or provider).strip(),
        "ident": raw.get("ident") if isinstance(raw.get("ident"), dict) else draft.get("ident"),
        "soul": normalize_soul(raw) or normalize_soul(draft),
    }
    label = merged["label"]
    raw_id = merged["id"]
    agent_id = slugify_agent_id(raw_id or label or "custom")
    draft_id = slugify_agent_id(str(draft.get("id") or "")) if refine else ""
    if refine and draft_id and agent_id == draft_id and not agent_id_taken(store, agent_id):
        pass
    else:
        agent_id = ensure_unique_agent_id(store, agent_id)
    if not label:
        label = agent_id
    soul = merged["soul"]
    if not soul:
        raise ValueError("Generated agent is missing soul content.")
    return {
        "id": agent_id,
        "label": label,
        "provider": normalize_agent_provider(merged["provider"] or provider),
        "ident": normalize_ident(merged.get("ident")),
        "soul": soul,
    }


def normalize_generate_messages(messages: object | None) -> list[JsonDict]:
    if not isinstance(messages, list):
        return []
    normalized: list[JsonDict] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            normalized.append({"role": role, "content": content})
    return normalized


def normalize_generate_draft(draft: object | None) -> JsonDict:
    if not isinstance(draft, dict):
        return {}
    ident = draft.get("ident") if isinstance(draft.get("ident"), dict) else {}
    payload = {
        "id": str(draft.get("id") or "").strip(),
        "label": str(draft.get("label") or "").strip(),
        "provider": str(draft.get("provider") or "").strip(),
        "ident": normalize_ident(ident),
        "soul": normalize_soul(draft),
    }
    return {key: value for key, value in payload.items() if value not in ("", {}, [])}


def build_generate_agent_prompt(
    description: str,
    provider: str,
    example: JsonDict | None,
    *,
    draft: JsonDict | None = None,
    messages: list[JsonDict] | None = None,
) -> str:
    provider_ids = ", ".join(spec.id for spec in AGENT_PROVIDER_SPECS)
    example_block = json.dumps(example, ensure_ascii=False, indent=2) if example else "{}"
    lines = [
        "You design role agents for AI Workflow Foundation.",
        "Return ONLY one JSON object. Do not wrap it in Markdown unless it is a single ```json fence.",
        "",
        "JSON schema:",
        "{",
        '  "id": "role_snake_case_id",',
        '  "label": "显示名称",',
        f'  "provider": "{provider}",',
        '  "ident": { "name": "名称", "role": "职责一句", "vibe": "气质" },',
        '  "soul": "Wayland Rules 风格：身份一句、## 行为、## 边界"',
        "}",
        "",
        f"Allowed provider values: {provider_ids}.",
        "Prefer provider "
        + provider
        + " unless the user clearly needs another connection layer.",
        "",
        "Example:",
        example_block,
    ]
    if draft:
        lines.extend(
            [
                "",
                "Current draft from the user form (refine instead of replacing blindly):",
                json.dumps(draft, ensure_ascii=False, indent=2),
            ]
        )
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
            "- If a draft exists, keep valid fields and only improve what the user asks for.",
            "- soul must be actionable for a workflow node executor, not a chatbot persona only.",
            "- ident.role should summarize the assistant mission in one sentence.",
            "- Use concise Chinese unless the user asks otherwise.",
            "- id must be lowercase snake_case and start with role_.",
            "- Return the complete final JSON object.",
        ]
    )
    return "\n".join(lines).rstrip()


def _example_payload(store: WorkflowStore) -> JsonDict | None:
    templates = list_agent_templates(store.project_root)
    example = next((item for item in templates if item["template_id"] == "requirement_analyst"), None)
    if example is None and templates:
        example = templates[0]
    if not example:
        return None
    return {
        "id": f"role_{example['template_id']}",
        "label": example["label"],
        "provider": example["provider"],
        "ident": example["ident"],
        "soul": example["soul"],
    }


def stream_agent_generate(
    store: WorkflowStore,
    *,
    description: str,
    provider_id: str | None = None,
    draft: JsonDict | None = None,
    messages: list[JsonDict] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[JsonDict]:
    text = description.strip()
    if not text:
        raise ValueError("description is required.")
    provider = normalize_agent_provider(provider_id or "cursor-agent-acp")
    if not is_acp_provider(provider):
        raise ValueError("Role Agent 生成仅支持 cursor-agent-acp 或 codex-agent-acp。")
    inspection = inspect_agent_provider(provider)
    if not inspection["ready"]:
        raise ValueError(str(inspection["detail"]))
    draft_payload = normalize_generate_draft(draft)
    refine = bool(draft_payload) or bool(normalize_generate_messages(messages))
    role_id = (agent_id or str(draft_payload.get("id") or "")).strip() or f"role_{uuid4().hex[:8]}"
    yield {
        "type": "progress",
        "stage": "prepare",
        "message": "准备 Role ACP 会话...",
        "percent": 8,
    }
    for event in stream_role_assist_message(
        store,
        agent_id=role_id,
        provider_id=provider,
        description=text,
        draft=draft_payload or None,
        session_id=session_id,
    ):
        if event.get("type") == "session":
            yield event
            continue
        if event.get("type") == "log":
            yield event
            continue
        if event.get("type") == "progress":
            yield event
            continue
        if event.get("type") == "done":
            raw = event.get("agent")
            if not isinstance(raw, dict):
                raise ValueError("role.json was not produced.")
            agent = normalize_generated_agent(store, raw, provider, draft=draft_payload, refine=refine)
            summary = str(event.get("summary") or "已生成助手草稿。")
            yield {
                "type": "done",
                "message": summary,
                "summary": summary,
                "agent": agent,
                "session_id": event.get("session_id"),
                "chat_id": event.get("chat_id"),
                "percent": 100,
            }
            return
    raise RuntimeError("Role assist stream ended without done event.")


def generate_agent_draft(
    store: WorkflowStore,
    *,
    description: str,
    provider_id: str | None = None,
    draft: JsonDict | None = None,
    messages: list[JsonDict] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> JsonDict:
    result: JsonDict | None = None
    for event in stream_agent_generate(
        store,
        description=description,
        provider_id=provider_id,
        draft=draft,
        messages=messages,
        agent_id=agent_id,
        session_id=session_id,
    ):
        if event.get("type") == "done":
            result = event
    if not result:
        raise ValueError("Agent generation did not complete.")
    return {
        "status": "ok",
        "message": str(result.get("message") or "已生成助手草稿。"),
        "agent": result["agent"],
        "output": result.get("output", ""),
    }
