"""ACP (Agent Client Protocol) client for Cursor Agent and Codex CLI.

Protocol (verified 2026-06-22, Cursor agent 2026.06.04):
- Transport: stdio, newline-delimited JSON (NDJSON)
- Envelope: JSON-RPC 2.0
- Client -> Agent stdin: requests/notifications
- Agent -> Client stdout: responses/notifications
- Agent logs: stderr

Typical flow:
1. initialize
2. authenticate (methodId: cursor_login) — skip when CURSOR_API_KEY / agent login already set
3. session/new (cwd=workspace) or session/load (sessionId=chat_id)
4. session/prompt — handle session/update chunks, session/request_permission (allow-once)

Windows spawn: PowerShell -> %LOCALAPPDATA%\\cursor-agent\\cursor-agent.ps1 acp
Codex: codex app-server (experimental; override via AIWF_CODEX_ACP_CMD when native acp ships)
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]

ACP_PROVIDER_IDS = frozenset({"cursor-agent-acp", "codex-agent-acp"})


@dataclass(frozen=True, slots=True)
class AcpSessionScope:
    provider_id: str
    scope_key: str
    workspace: Path
    chat_id: str | None = None


def default_acp_timeout() -> int:
    return int(os.environ.get("AIWF_CLI_ACP_TIMEOUT", "600"))


def _windows_powershell() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(candidate) if candidate.exists() else "powershell.exe"


def _default_cursor_acp_argv(workspace: Path) -> list[str]:
    override = os.environ.get("AIWF_CURSOR_ACP_CMD", "").strip()
    if override:
        argv = shlex.split(override, posix=os.name != "nt")
    elif os.name == "nt":
        ps1 = Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "cursor-agent.ps1"
        if not ps1.exists():
            raise RuntimeError(f"cursor-agent.ps1 not found: {ps1}")
        argv = [
            _windows_powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "acp",
        ]
    else:
        argv = ["agent", "acp"]
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    if "--trust" not in argv and "-f" not in argv:
        # Insert trust before acp subcommand when using bare agent.
        if "acp" in argv:
            idx = argv.index("acp")
            argv.insert(idx, "--trust")
    cwd = str(workspace.resolve())
    if cwd and "--workspace" not in argv and "-w" not in argv:
        if "acp" in argv:
            idx = argv.index("acp")
            argv[idx:idx] = ["--workspace", cwd]
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if api_key and "--api-key" not in argv:
        if "acp" in argv:
            idx = argv.index("acp")
            argv[idx:idx] = ["--api-key", api_key]
    return argv


def _default_codex_acp_argv(workspace: Path) -> list[str]:
    override = os.environ.get("AIWF_CODEX_ACP_CMD", "").strip()
    if override:
        argv = shlex.split(override, posix=os.name != "nt")
    else:
        argv = ["codex", "app-server"]
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    cwd = str(workspace.resolve())
    if cwd and "-c" not in argv and "--workspace" not in argv:
        argv.extend(["-c", f'cwd="{cwd}"'])
    return argv


def resolve_spawn_argv(provider_id: str, workspace: Path) -> list[str]:
    if provider_id == "cursor-agent-acp":
        return _default_cursor_acp_argv(workspace)
    if provider_id == "codex-agent-acp":
        return _default_codex_acp_argv(workspace)
    raise ValueError(f"Not an ACP provider: {provider_id}")


def is_acp_provider(provider_id: str) -> bool:
    return provider_id in ACP_PROVIDER_IDS


class CliAcpClient:
    """Long-lived ACP subprocess with JSON-RPC over stdio."""

    def __init__(
        self,
        *,
        provider_id: str,
        workspace: Path,
        scope_key: str,
        timeout: int | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.workspace = workspace.resolve()
        self.scope_key = scope_key
        self.timeout = timeout or default_acp_timeout()
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue[JsonDict]] = {}
        self._write_lock = threading.Lock()
        self._message_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._closed = False
        self._initialized = False
        self._chat_id: str | None = None
        self._assistant_chunks: list[str] = []
        self._prompt_done = threading.Event()
        self._prompt_error: Exception | None = None
        self._prompt_result: JsonDict | None = None
        self._prompt_request_id: int | None = None
        self._stream_buffer: list[str] = []
        self._stderr_tail: deque[str] = deque(maxlen=20)

    @property
    def chat_id(self) -> str | None:
        return self._chat_id

    def start_session(self) -> None:
        if self._proc is not None:
            return
        argv = resolve_spawn_argv(self.provider_id, self.workspace)
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            cwd=str(self.workspace),
        )
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        assert self._proc.stderr is not None
        self._reader_thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()
        self._rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
                "clientInfo": {"name": "aiwf-acp-client", "version": "1.0.0"},
            },
        )
        if self.provider_id == "cursor-agent-acp":
            if not os.environ.get("CURSOR_API_KEY", "").strip():
                try:
                    self._rpc("authenticate", {"methodId": "cursor_login"})
                except RuntimeError:
                    pass
        self._initialized = True

    def create_chat(self) -> str:
        self._ensure_running()
        result = self._rpc(
            "session/new",
            {"cwd": str(self.workspace), "mcpServers": []},
        )
        session_id = str(result.get("sessionId") or result.get("session_id") or "")
        if not session_id:
            raise RuntimeError(f"session/new did not return sessionId: {result}")
        self._chat_id = session_id
        return session_id

    def load_chat(self, chat_id: str) -> None:
        self._ensure_running()
        self._rpc("session/load", {"sessionId": chat_id, "cwd": str(self.workspace)})
        self._chat_id = chat_id

    def send_message(self, text: str) -> Iterator[JsonDict]:
        self._ensure_running()
        if not self._chat_id:
            raise RuntimeError("ACP chat not created; call create_chat() or load_chat() first.")
        self._assistant_chunks = []
        self._stream_buffer = []
        self._prompt_done.clear()
        self._prompt_error = None
        self._prompt_result = None
        yield {"type": "progress", "stage": "acp", "message": "发送消息...", "percent": 20}
        prompt_id = self._alloc_id()
        self._prompt_request_id = prompt_id
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": prompt_id,
                "method": "session/prompt",
                "params": {
                    "sessionId": self._chat_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            },
        )
        deadline = time.time() + self.timeout
        last_percent = 20
        emitted = 0
        while not self._prompt_done.is_set():
            if time.time() > deadline:
                raise RuntimeError(f"ACP prompt timed out after {self.timeout} seconds")
            while emitted < len(self._stream_buffer):
                chunk = self._stream_buffer[emitted]
                emitted += 1
                last_percent = min(last_percent + 2, 90)
                yield {"type": "assistant", "text": chunk}
            time.sleep(0.05)
        if self._prompt_error is not None:
            raise self._prompt_error
        while emitted < len(self._stream_buffer):
            chunk = self._stream_buffer[emitted]
            emitted += 1
            yield {"type": "assistant", "text": chunk}
        stop_reason = ""
        if self._prompt_result:
            stop_reason = str(self._prompt_result.get("stopReason") or "")
        yield {
            "type": "done",
            "message": "完成",
            "stop_reason": stop_reason,
            "percent": 100,
        }

    def ping(self) -> bool:
        try:
            self.start_session()
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _ensure_running(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("ACP subprocess is not running.")
        if not self._initialized:
            self.start_session()

    def _alloc_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _send_json(self, payload: JsonDict, *, track_response: bool = True) -> int | None:
        assert self._proc is not None and self._proc.stdin is not None
        msg_id = payload.get("id")
        if track_response and isinstance(msg_id, int):
            self._pending[msg_id] = queue.Queue(maxsize=1)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._write_lock:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        return int(msg_id) if isinstance(msg_id, int) else None

    def _rpc(self, method: str, params: JsonDict) -> JsonDict:
        msg_id = self._alloc_id()
        self._send_json({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        return self._wait_response(msg_id)

    def _wait_response(self, msg_id: int) -> JsonDict:
        pending = self._pending.get(msg_id)
        if pending is None:
            raise RuntimeError(f"No pending request for id {msg_id}")
        try:
            msg = pending.get(timeout=self.timeout)
        finally:
            self._pending.pop(msg_id, None)
        if "error" in msg:
            error = msg["error"]
            raise RuntimeError(self._format_rpc_error(error))
        result = msg.get("result")
        if not isinstance(result, dict):
            return {}
        return result

    def _read_stdout_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for raw_line in iter(self._proc.stdout.readline, ""):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._dispatch_message(msg)
        except Exception as exc:
            self._complete_prompt(error=RuntimeError(f"ACP stdout reader failed: {exc}"))

    def _read_stderr_loop(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw_line in iter(self._proc.stderr.readline, ""):
            text = raw_line.rstrip("\r\n")
            if text:
                self._stderr_tail.append(text)

    def _dispatch_message(self, msg: JsonDict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            msg_id = msg.get("id")
            if isinstance(msg_id, int) and msg_id == self._prompt_request_id:
                if "error" in msg:
                    error = msg["error"]
                    self._complete_prompt(error=RuntimeError(self._format_rpc_error(error)))
                else:
                    result = msg.get("result") if isinstance(msg.get("result"), dict) else {}
                    self._complete_prompt(result=result)
                self._prompt_request_id = None
            if isinstance(msg_id, int):
                pending = self._pending.get(msg_id)
                if pending is not None:
                    pending.put(msg)
            return
        method = msg.get("method")
        if not isinstance(method, str):
            return
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "session/update":
            self._handle_session_update(params)
            return
        if method == "session/request_permission":
            self._respond_request(msg, {"outcome": {"outcome": "selected", "optionId": "allow-once"}})
            return
        if method.startswith("cursor/"):
            self._handle_cursor_extension(msg, method, params)
            return
        if method in {"fs/read_text_file", "fs/write_text_file"}:
            self._handle_fs_request(msg, method, params)

    def _handle_session_update(self, params: JsonDict) -> None:
        update = params.get("update") if isinstance(params.get("update"), dict) else params
        if not isinstance(update, dict):
            return
        session_update = str(update.get("sessionUpdate") or update.get("type") or "")
        if session_update == "agent_message_chunk":
            content = update.get("content") if isinstance(update.get("content"), dict) else {}
            text = content.get("text") if isinstance(content, dict) else ""
            if isinstance(text, str) and text:
                self._assistant_chunks.append(text)
                self._stream_buffer.append(text)
        elif session_update in {"turn_complete", "done", "completed"}:
            if self._prompt_request_id is None:
                self._prompt_done.set()

    def _handle_cursor_extension(self, msg: JsonDict, method: str, params: JsonDict) -> None:
        msg_id = msg.get("id")
        if not isinstance(msg_id, int):
            return
        if method == "cursor/ask_question":
            self._respond_request(msg, {"outcome": {"outcome": "skipped"}})
        elif method == "cursor/create_plan":
            self._respond_request(msg, {"outcome": {"outcome": "accepted"}})
        elif method in {"cursor/update_todos", "cursor/task", "cursor/generate_image"}:
            return
        else:
            self._respond_request(msg, {"outcome": {"outcome": "accepted"}})

    def _handle_fs_request(self, msg: JsonDict, method: str, params: JsonDict) -> None:
        msg_id = msg.get("id")
        if not isinstance(msg_id, int):
            return
        path_value = str(params.get("path") or params.get("filePath") or "")
        target = Path(path_value)
        if not target.is_absolute():
            target = self.workspace / target
        try:
            if method == "fs/read_text_file":
                content = target.read_text(encoding="utf-8")
                self._respond_request(msg, {"content": content})
            elif method == "fs/write_text_file":
                content = str(params.get("content") or "")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                self._respond_request(msg, {"success": True})
            else:
                self._respond_request(msg, {"error": "unsupported"})
        except OSError as exc:
            self._respond_request(msg, {"error": str(exc)})

    def _respond_request(self, msg: JsonDict, result: JsonDict) -> None:
        msg_id = msg.get("id")
        if not isinstance(msg_id, int):
            return
        self._send_json({"jsonrpc": "2.0", "id": msg_id, "result": result}, track_response=False)

    def _complete_prompt(self, result: JsonDict | None = None, error: Exception | None = None) -> None:
        self._prompt_result = result
        self._prompt_error = error
        self._prompt_done.set()

    def _format_rpc_error(self, error: object) -> str:
        if not isinstance(error, dict):
            return str(error)
        message = str(error.get("message") or error).strip()
        code = error.get("code")
        data = error.get("data")
        detail_parts: list[str] = []
        if code not in (None, ""):
            detail_parts.append(f"code={code}")
        if data not in (None, ""):
            try:
                data_text = json.dumps(data, ensure_ascii=False, sort_keys=True)
            except TypeError:
                data_text = str(data)
            if len(data_text) > 500:
                data_text = data_text[:500] + "..."
            detail_parts.append(f"data={data_text}")
        if self._stderr_tail:
            stderr_text = " | ".join(self._stderr_tail)
            if len(stderr_text) > 500:
                stderr_text = stderr_text[-500:]
            detail_parts.append(f"stderr={stderr_text}")
        if not detail_parts:
            return message
        return f"{message} ({'; '.join(detail_parts)})"


class SessionRegistry:
    """In-memory cache of long-lived ACP clients keyed by scope."""

    _instance: SessionRegistry | None = None

    def __init__(self) -> None:
        self._clients: dict[str, CliAcpClient] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    @classmethod
    def get(cls) -> SessionRegistry:
        if cls._instance is None:
            cls._instance = SessionRegistry()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance.close_all()
            cls._instance = None

    def _scope_lock(self, scope_key: str) -> threading.Lock:
        with self._global_lock:
            return self._locks.setdefault(scope_key, threading.Lock())

    def _acquire_client(self, scope: AcpSessionScope) -> CliAcpClient:
        client = self._clients.get(scope.scope_key)
        if client is None or client._proc is None or client._proc.poll() is not None:
            if client is not None:
                client.close()
            client = CliAcpClient(
                provider_id=scope.provider_id,
                workspace=scope.workspace,
                scope_key=scope.scope_key,
            )
            client.start_session()
            self._clients[scope.scope_key] = client
        if scope.chat_id and client.chat_id != scope.chat_id:
            client.load_chat(scope.chat_id)
        return client

    def acquire(self, scope: AcpSessionScope) -> CliAcpClient:
        with self._scope_lock(scope.scope_key):
            return self._acquire_client(scope)

    def resume(self, scope: AcpSessionScope) -> CliAcpClient:
        if not scope.chat_id:
            raise ValueError("chat_id is required to resume an ACP session.")
        return self.acquire(scope)

    def release_scope(self, scope_key: str) -> None:
        with self._global_lock:
            client = self._clients.pop(scope_key, None)
            self._locks.pop(scope_key, None)
        if client is not None:
            client.close()

    def close_all(self) -> None:
        with self._global_lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._locks.clear()
        for client in clients:
            client.close()


def stream_acp_message(
    scope: AcpSessionScope,
    text: str,
    *,
    create_chat: bool = False,
) -> Iterator[JsonDict]:
    registry = SessionRegistry.get()
    with registry._scope_lock(scope.scope_key):
        client = registry._acquire_client(scope)
        if create_chat and not scope.chat_id and not client.chat_id:
            chat_id = client.create_chat()
            yield {"type": "session", "chat_id": chat_id, "scope_key": scope.scope_key}
        yield from client.send_message(text)
