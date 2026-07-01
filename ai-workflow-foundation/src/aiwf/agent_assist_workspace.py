from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agent_providers import create_cli_session_provider, normalize_agent_provider
from .cli_acp import AcpSessionScope, SessionRegistry, stream_acp_message
from .storage import WorkflowStore

JsonDict = dict[str, object]

ASSIST_ROOT = "agents/assist"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assist_root(store: WorkflowStore) -> Path:
    return store.aiwf / ASSIST_ROOT


def index_path(store: WorkflowStore) -> Path:
    return assist_root(store) / "index.json"


def _read_index(store: WorkflowStore) -> JsonDict:
    path = index_path(store)
    if not path.exists():
        return {"by_agent_id": {}, "active_agent_id": ""}
    data = store.read_json(path)
    if not isinstance(data, dict):
        return {"by_agent_id": {}, "active_agent_id": ""}
    if not isinstance(data.get("by_agent_id"), dict):
        data["by_agent_id"] = {}
    return data


def _write_index(store: WorkflowStore, index: JsonDict) -> None:
    root = assist_root(store)
    root.mkdir(parents=True, exist_ok=True)
    store.write_json(index_path(store), index)


def session_dir(store: WorkflowStore, session_id: str) -> Path:
    return assist_root(store) / session_id


def resolve_role_session(
    store: WorkflowStore,
    *,
    agent_id: str,
    provider_id: str,
    workspace: Path | None = None,
    session_id: str | None = None,
) -> tuple[str, Path, str | None]:
    """Return (session_id, session_path, chat_id)."""
    agent_key = agent_id.strip()
    if not agent_key:
        raise ValueError("agent_id is required.")
    index = _read_index(store)
    by_agent = index["by_agent_id"]
    assert isinstance(by_agent, dict)
    entry = by_agent.get(agent_key) if isinstance(by_agent.get(agent_key), dict) else None
    sid = session_id or (str(entry.get("session_id")) if entry else "") or f"role_assist_{uuid4().hex[:12]}"
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
        SessionRegistry.get().release_scope(f"role:{agent_key}")
        if session_data is not None:
            session_data["chat_id"] = None
            session_data["provider_id"] = provider_id
            session_data["updated_at"] = _utc_now()
            store.write_json(session_file, session_data)
    ws = workspace or folder
    by_agent[agent_key] = {
        "session_id": sid,
        "chat_id": chat_id,
        "provider_id": provider_id,
        "updated_at": _utc_now(),
    }
    index["active_agent_id"] = agent_key
    _write_index(store, index)
    if not session_file.exists():
        store.write_json(
            session_file,
            {
                "session_id": sid,
                "agent_id": agent_key,
                "provider_id": provider_id,
                "chat_id": chat_id or None,
                "workspace": str(ws),
                "created_at": _utc_now(),
            },
        )
    return sid, folder, chat_id or None


def write_context_bootstrap(folder: Path, *, agent_id: str, content: str) -> None:
    path = folder / "context.md"
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def default_role_context(agent_id: str) -> str:
    return "\n".join(
        [
            f"# Role Assist Session: {agent_id}",
            "",
            "You edit the role definition for an AI workflow agent.",
            "",
            "Files in this workspace:",
            "- `role.json` — the role agent definition (id, label, provider, ident, soul)",
            "- `summary.md` — brief Chinese summary of your last change",
            "",
            "Rules:",
            "- Update only `role.json` and `summary.md` in this directory.",
            "- Keep valid JSON in role.json matching the schema.",
            "- Write summary in concise Chinese.",
            "- Do not output JSON in chat; write files directly.",
        ]
    )


def sync_draft_to_role_json(folder: Path, draft: JsonDict | None) -> None:
    path = folder / "role.json"
    if draft:
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif not path.exists():
        path.write_text("{}\n", encoding="utf-8")


def read_role_result(folder: Path) -> tuple[JsonDict, str]:
    role_path = folder / "role.json"
    summary_path = folder / "summary.md"
    if not role_path.exists():
        raise ValueError("role.json was not created in assist workspace.")
    raw = json.loads(role_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("role.json must be a JSON object.")
    summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    return raw, summary


def clear_role_chat_id(store: WorkflowStore, agent_id: str, session_id: str) -> None:
    agent_key = agent_id.strip()
    index = _read_index(store)
    by_agent = index["by_agent_id"]
    assert isinstance(by_agent, dict)
    entry = by_agent.get(agent_key) if isinstance(by_agent.get(agent_key), dict) else {}
    entry = dict(entry)
    entry.update({"session_id": session_id, "chat_id": "", "updated_at": _utc_now()})
    by_agent[agent_key] = entry
    _write_index(store, index)
    session_file = session_dir(store, session_id) / "session.json"
    if session_file.exists():
        data = store.read_json(session_file)
        if isinstance(data, dict):
            data["chat_id"] = None
            data["updated_at"] = _utc_now()
            store.write_json(session_file, data)


def persist_chat_id(store: WorkflowStore, agent_id: str, session_id: str, chat_id: str) -> None:
    index = _read_index(store)
    by_agent = index["by_agent_id"]
    assert isinstance(by_agent, dict)
    entry = by_agent.get(agent_id) if isinstance(by_agent.get(agent_id), dict) else {}
    entry = dict(entry)
    entry.update({"session_id": session_id, "chat_id": chat_id, "updated_at": _utc_now()})
    by_agent[agent_id] = entry
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


def stream_role_assist_message(
    store: WorkflowStore,
    *,
    agent_id: str,
    provider_id: str,
    description: str,
    draft: JsonDict | None = None,
    session_id: str | None = None,
    workspace: Path | None = None,
):
    sid, folder, chat_id = resolve_role_session(
        store,
        agent_id=agent_id,
        provider_id=provider_id,
        workspace=workspace,
        session_id=session_id,
    )
    yield {"type": "session", "session_id": sid, "chat_id": chat_id or "", "agent_id": agent_id}
    write_context_bootstrap(folder, agent_id=agent_id, content=default_role_context(agent_id))
    sync_draft_to_role_json(folder, draft)
    scope_key = f"role:{agent_id}"
    user_text = "\n".join(
        [
            description.strip(),
            "",
            f"Workspace: {folder}",
            "Update role.json and summary.md per context.md.",
        ]
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
                persist_chat_id(store, agent_id, sid, active_chat_id)
                scope = AcpSessionScope(
                    provider_id=provider_id,
                    scope_key=scope_key,
                    workspace=folder,
                    chat_id=active_chat_id,
                )
                yield {"type": "session", "session_id": sid, "chat_id": active_chat_id, "agent_id": agent_id}
            for event in stream_acp_message(scope, user_text):
                if event.get("type") == "assistant":
                    yield {"type": "log", "line": str(event.get("text") or "")}
                elif event.get("type") == "progress":
                    yield event
                elif event.get("type") == "done":
                    raw, summary = read_role_result(folder)
                    yield {
                        "type": "done",
                        "summary": summary,
                        "agent": raw,
                        "session_id": sid,
                        "chat_id": scope.chat_id or "",
                    }
            return
        except RuntimeError as exc:
            if attempt == 0 and active_chat_id and _is_recoverable_acp_error(exc):
                clear_role_chat_id(store, agent_id, sid)
                SessionRegistry.get().release_scope(scope_key)
                active_chat_id = None
                continue
            raise RuntimeError(_friendly_acp_error(exc)) from exc
