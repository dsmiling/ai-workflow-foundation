from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agent_providers import create_cli_session_provider, normalize_agent_provider
from .cli_acp import AcpSessionScope, SessionRegistry, stream_acp_message
from .storage import WorkflowStore

JsonDict = dict[str, object]

ASSIST_ROOT = "assist"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assist_root(store: WorkflowStore) -> Path:
    return store.aiwf / ASSIST_ROOT


def index_path(store: WorkflowStore) -> Path:
    return assist_root(store) / "index.json"


def _read_index(store: WorkflowStore) -> JsonDict:
    path = index_path(store)
    if not path.exists():
        return {"by_workflow_id": {}, "active_workflow_id": ""}
    data = store.read_json(path)
    if not isinstance(data, dict):
        return {"by_workflow_id": {}, "active_workflow_id": ""}
    if not isinstance(data.get("by_workflow_id"), dict):
        data["by_workflow_id"] = {}
    return data


def _write_index(store: WorkflowStore, index: JsonDict) -> None:
    root = assist_root(store)
    root.mkdir(parents=True, exist_ok=True)
    store.write_json(index_path(store), index)


def session_dir(store: WorkflowStore, session_id: str) -> Path:
    return assist_root(store) / session_id


def resolve_workflow_session(
    store: WorkflowStore,
    *,
    workflow_id: str,
    provider_id: str,
    session_id: str | None = None,
) -> tuple[str, Path, str | None]:
    wf_key = workflow_id.strip()
    if not wf_key:
        raise ValueError("workflow_id is required.")
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(wf_key) if isinstance(by_workflow.get(wf_key), dict) else None
    sid = session_id or (str(entry.get("session_id")) if entry else "") or f"assist_{uuid4().hex[:12]}"
    chat_id = str(entry.get("chat_id") or "") if entry else ""
    if session_id and session_id != sid:
        sid = session_id
        chat_id = ""
    folder = session_dir(store, sid)
    folder.mkdir(parents=True, exist_ok=True)
    session_file = folder / "session.json"
    session_data: JsonDict | None = None
    if session_file.exists():
        raw_session = store.read_json(session_file)
        if isinstance(raw_session, dict):
            session_data = raw_session
            if session_data.get("chat_id"):
                chat_id = str(session_data["chat_id"])
    incoming_provider = normalize_agent_provider(provider_id)
    stored_provider_raw = ""
    if session_data and session_data.get("provider_id"):
        stored_provider_raw = str(session_data["provider_id"])
    elif entry and entry.get("provider_id"):
        stored_provider_raw = str(entry["provider_id"])
    stored_provider = (
        normalize_agent_provider(stored_provider_raw) if stored_provider_raw.strip() else ""
    )
    if stored_provider and stored_provider != incoming_provider and chat_id:
        chat_id = ""
        SessionRegistry.get().release_scope(f"workflow:{wf_key}")
        if session_data is not None:
            session_data["chat_id"] = None
            session_data["provider_id"] = provider_id
            session_data["updated_at"] = _utc_now()
            store.write_json(session_file, session_data)
    by_workflow[wf_key] = {
        "session_id": sid,
        "chat_id": chat_id,
        "provider_id": provider_id,
        "updated_at": _utc_now(),
    }
    index["active_workflow_id"] = wf_key
    _write_index(store, index)
    if not session_file.exists():
        store.write_json(
            session_file,
            {
                "session_id": sid,
                "workflow_id": wf_key,
                "provider_id": provider_id,
                "chat_id": chat_id or None,
                "workspace": str(folder),
                "created_at": _utc_now(),
            },
        )
    return sid, folder, chat_id or None


def default_workflow_context(workflow_id: str) -> str:
    return "\n".join(
        [
            f"# Workflow Assist Session: {workflow_id}",
            "",
            "You assist users with workflow orchestration in a local AI workflow editor.",
            "",
            "Files:",
            "- `draft.json` — workflow draft (id, name, nodes, transitions, initial)",
            "- `summary.md` — optional one-line internal note",
            "",
            "Rules:",
            "- Reply naturally in chat when the user discusses requirements, asks questions, or explores ideas.",
            "- Only modify draft.json when the user explicitly requests workflow structure changes.",
            "- When not editing the workflow, leave draft.json unchanged and respond conversationally.",
            "- When focus nodes are specified for an edit, change only fields the user explicitly requests.",
            "- Do NOT translate or rewrite literal input values unless asked.",
            "- Do NOT modify non-focus nodes during targeted edits.",
            "- For structural edits, update draft.json; the UI shows a structural diff when the draft changes.",
            "- Do not paste full JSON in chat; write files directly.",
            "- summary.md is internal only; keep it to one line or leave empty.",
        ]
    )


def write_context_bootstrap(folder: Path, *, workflow_id: str) -> None:
    path = folder / "context.md"
    if not path.exists():
        path.write_text(default_workflow_context(workflow_id), encoding="utf-8")


def sync_draft_to_workspace(folder: Path, draft: JsonDict | None) -> None:
    path = folder / "draft.json"
    if draft:
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif not path.exists():
        path.write_text("{}\n", encoding="utf-8")


def read_workflow_result(folder: Path) -> tuple[JsonDict, str]:
    draft_path = folder / "draft.json"
    summary_path = folder / "summary.md"
    if not draft_path.exists():
        raise ValueError("draft.json was not created in assist workspace.")
    raw = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("draft.json must be a JSON object.")
    summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    return raw, summary


def _normalize_chat_messages(raw: object) -> list[JsonDict]:
    if not isinstance(raw, list):
        return []
    messages: list[JsonDict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def load_workflow_assist_session(store: WorkflowStore, workflow_id: str) -> JsonDict:
    wf_key = workflow_id.strip()
    if not wf_key:
        raise ValueError("workflow_id is required.")
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(wf_key) if isinstance(by_workflow.get(wf_key), dict) else {}
    session_id = str(entry.get("session_id") or "")
    chat_id = str(entry.get("chat_id") or "")
    provider_id = str(entry.get("provider_id") or "")
    messages: list[JsonDict] = []
    pending_summary = ""
    if session_id:
        session_file = session_dir(store, session_id) / "session.json"
        if session_file.exists():
            data = store.read_json(session_file)
            if isinstance(data, dict):
                if data.get("chat_id"):
                    chat_id = str(data["chat_id"])
                if data.get("provider_id"):
                    provider_id = str(data["provider_id"])
                messages = _normalize_chat_messages(data.get("messages"))
                pending_summary = str(data.get("pending_summary") or "").strip()
    return {
        "workflow_id": wf_key,
        "session_id": session_id,
        "chat_id": chat_id,
        "provider_id": provider_id,
        "messages": messages,
        "pending_summary": pending_summary,
    }


def append_workflow_assist_messages(
    store: WorkflowStore,
    *,
    workflow_id: str,
    session_id: str,
    user_text: str,
    assistant_text: str,
    pending_summary: str = "",
) -> None:
    wf_key = workflow_id.strip()
    session_file = session_dir(store, session_id) / "session.json"
    data: JsonDict
    if session_file.exists():
        raw = store.read_json(session_file)
        data = dict(raw) if isinstance(raw, dict) else {}
    else:
        data = {"session_id": session_id, "workflow_id": wf_key}
    messages = _normalize_chat_messages(data.get("messages"))
    user_content = user_text.strip()
    assistant_content = assistant_text.strip()
    if user_content:
        messages.append({"role": "user", "content": user_content})
    if assistant_content:
        messages.append({"role": "assistant", "content": assistant_content})
    data["messages"] = messages
    if pending_summary.strip():
        data["pending_summary"] = pending_summary.strip()
    data["updated_at"] = _utc_now()
    store.write_json(session_file, data)
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(wf_key) if isinstance(by_workflow.get(wf_key), dict) else {}
    entry = dict(entry)
    entry.update({"session_id": session_id, "updated_at": _utc_now()})
    by_workflow[wf_key] = entry
    _write_index(store, index)


def clear_workflow_assist_session(store: WorkflowStore, workflow_id: str) -> JsonDict:
    wf_key = workflow_id.strip()
    if not wf_key:
        raise ValueError("workflow_id is required.")
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(wf_key) if isinstance(by_workflow.get(wf_key), dict) else {}
    session_id = str(entry.get("session_id") or "")
    provider_id = str(entry.get("provider_id") or "")
    if session_id:
        session_file = session_dir(store, session_id) / "session.json"
        if session_file.exists():
            raw = store.read_json(session_file)
            data = dict(raw) if isinstance(raw, dict) else {}
            data["session_id"] = session_id
            data["workflow_id"] = wf_key
            data["provider_id"] = provider_id
            data["chat_id"] = None
            data["messages"] = []
            data["pending_summary"] = ""
            data["updated_at"] = _utc_now()
            store.write_json(session_file, data)
        summary_path = session_dir(store, session_id) / "summary.md"
        if summary_path.exists():
            summary_path.write_text("", encoding="utf-8")
    SessionRegistry.get().release_scope(f"workflow:{wf_key}")
    if wf_key in by_workflow:
        updated = dict(entry)
        updated["chat_id"] = ""
        updated["updated_at"] = _utc_now()
        by_workflow[wf_key] = updated
        _write_index(store, index)
    return {
        "workflow_id": wf_key,
        "session_id": session_id,
        "provider_id": provider_id,
        "messages": [],
        "pending_summary": "",
        "chat_id": "",
    }


def clear_workflow_chat_id(store: WorkflowStore, workflow_id: str, session_id: str) -> None:
    wf_key = workflow_id.strip()
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(wf_key) if isinstance(by_workflow.get(wf_key), dict) else {}
    entry = dict(entry)
    entry.update({"session_id": session_id, "chat_id": "", "updated_at": _utc_now()})
    by_workflow[wf_key] = entry
    _write_index(store, index)
    session_file = session_dir(store, session_id) / "session.json"
    if session_file.exists():
        data = store.read_json(session_file)
        if isinstance(data, dict):
            data["chat_id"] = None
            data["updated_at"] = _utc_now()
            store.write_json(session_file, data)


def persist_chat_id(store: WorkflowStore, workflow_id: str, session_id: str, chat_id: str) -> None:
    index = _read_index(store)
    by_workflow = index["by_workflow_id"]
    assert isinstance(by_workflow, dict)
    entry = by_workflow.get(workflow_id) if isinstance(by_workflow.get(workflow_id), dict) else {}
    entry = dict(entry)
    entry.update({"session_id": session_id, "chat_id": chat_id, "updated_at": _utc_now()})
    by_workflow[workflow_id] = entry
    _write_index(store, index)
    session_file = session_dir(store, session_id) / "session.json"
    if session_file.exists():
        data = store.read_json(session_file)
        if isinstance(data, dict):
            data["chat_id"] = chat_id
            data["updated_at"] = _utc_now()
            store.write_json(session_file, data)


def _is_recoverable_acp_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    recoverable_prefixes = ("internal error", "session not found", "invalid session", "unknown session")
    return any(
        message == item or message.startswith(f"{item} ") or message.startswith(f"{item}(")
        for item in recoverable_prefixes
    )


def _friendly_acp_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if _is_recoverable_acp_error(exc):
        return (
            "ACP 会话返回 Internal error，已清理旧会话并重试但仍失败。"
            "请先在“模型/Agent”设置里测试当前 Cursor/Codex ACP，或重启 AIWF 后再试。"
            f"原始错误：{message}"
        )
    return message


def build_workflow_acp_user_text(
    description: str,
    folder: Path,
    *,
    focus_hint: str = "",
    focus_nodes: list[JsonDict] | None = None,
    focus_detail: str = "full",
) -> str:
    lines = [description.strip(), ""]
    mode = (focus_detail or "full").strip().lower()
    constraints = [
        "Constraints:",
        "- Change only fields mentioned in the user request.",
        "- Do NOT translate or rewrite inputs/outputs/skill/approval/params unless asked.",
        "- Keep all other nodes identical to draft.json.",
        "",
    ]
    if mode == "none":
        lines.extend(
            [
                "Mode: conversation (requirement discussion / Q&A).",
                "Reply naturally to the user in chat.",
                "Do NOT read or modify draft.json unless they explicitly ask to change workflow structure.",
                "",
            ]
        )
        if focus_hint:
            lines.extend(
                [
                    "Background context (optional, do not echo verbatim):",
                    focus_hint,
                    "",
                ]
            )
        lines.append(f"Workspace: {folder}")
        return "\n".join(lines)
    elif mode == "full" and focus_nodes:
        lines.extend(
            [
                "Focus nodes (edit only what the user explicitly requests):",
                *[json.dumps(node, ensure_ascii=False, indent=2) for node in focus_nodes],
                "",
                *constraints,
            ]
        )
    elif mode == "compact" and focus_hint:
        lines.extend(
            [
                "Context (internal; do not repeat in chat):",
                focus_hint,
                "",
                *constraints,
            ]
        )
    if mode != "none" and focus_hint and mode == "full" and not focus_nodes:
        lines.extend([focus_hint, ""])
    lines.extend(
        [
            f"Workspace: {folder}",
            "Update draft.json per context.md. summary.md is optional and not shown in chat.",
        ]
    )
    return "\n".join(lines)


def stream_workflow_assist_acp(
    store: WorkflowStore,
    *,
    workflow_id: str,
    provider_id: str,
    description: str,
    draft: JsonDict | None = None,
    session_id: str | None = None,
    focus_hint: str = "",
    focus_node_ids: list[str] | None = None,
    focus_nodes: list[JsonDict] | None = None,
    focus_detail: str = "full",
):
    sid, folder, chat_id = resolve_workflow_session(
        store,
        workflow_id=workflow_id,
        provider_id=provider_id,
        session_id=session_id,
    )
    yield {"type": "session", "session_id": sid, "chat_id": chat_id or "", "workflow_id": workflow_id}
    write_context_bootstrap(folder, workflow_id=workflow_id)
    sync_draft_to_workspace(folder, draft)
    scope_key = f"workflow:{workflow_id}"
    user_text = build_workflow_acp_user_text(
        description,
        folder,
        focus_hint=focus_hint,
        focus_nodes=focus_nodes,
        focus_detail=focus_detail,
    )
    active_chat_id = chat_id
    for attempt in range(2):
        try:
            scope = AcpSessionScope(
                provider_id=provider_id,
                scope_key=scope_key,
                workspace=folder,
                chat_id=active_chat_id,
            )
            if not active_chat_id:
                client = create_cli_session_provider(provider_id).acquire_session(scope)
                active_chat_id = client.create_chat()
                persist_chat_id(store, workflow_id, sid, active_chat_id)
                scope = AcpSessionScope(
                    provider_id=provider_id,
                    scope_key=scope_key,
                    workspace=folder,
                    chat_id=active_chat_id,
                )
                yield {
                    "type": "session",
                    "session_id": sid,
                    "chat_id": active_chat_id,
                    "workflow_id": workflow_id,
                }
            assistant_parts: list[str] = []
            for event in stream_acp_message(scope, user_text):
                if event.get("type") == "assistant":
                    chunk = str(event.get("text") or "")
                    if chunk:
                        assistant_parts.append(chunk)
                        yield {"type": "assistant", "content": chunk}
                elif event.get("type") == "progress":
                    yield event
                elif event.get("type") == "done":
                    raw, summary = read_workflow_result(folder)
                    yield {
                        "type": "workspace_done",
                        "summary": summary,
                        "workflow": raw,
                        "assistant_reply": "".join(assistant_parts).strip(),
                        "session_id": sid,
                        "chat_id": scope.chat_id or "",
                    }
            return
        except RuntimeError as exc:
            if attempt == 0 and active_chat_id and _is_recoverable_acp_error(exc):
                clear_workflow_chat_id(store, workflow_id, sid)
                SessionRegistry.get().release_scope(scope_key)
                active_chat_id = None
                continue
            raise RuntimeError(_friendly_acp_error(exc)) from exc
