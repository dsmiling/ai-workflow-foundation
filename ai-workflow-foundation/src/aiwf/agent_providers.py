from __future__ import annotations

import json
import os
import shlex
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

from .cli_acp import (
    AcpSessionScope,
    CliAcpClient,
    SessionRegistry,
    default_acp_timeout,
    is_acp_provider,
    resolve_spawn_argv,
    stream_acp_message,
)

__all__ = [
    "is_acp_provider",
    "create_cli_session_provider",
    "stream_provider_generate",
]


@dataclass(frozen=True, slots=True)
class AgentProviderSpec:
    id: str
    label: str
    kind: str
    description: str
    requires: tuple[str, ...] = ()


class AgentProvider(Protocol):
    spec: AgentProviderSpec

    def generate(self, prompt: str) -> str:
        ...


class CliSessionProvider(Protocol):
    spec: AgentProviderSpec

    def acquire_session(self, scope: AcpSessionScope) -> CliAcpClient:
        ...


AGENT_PROVIDER_SPECS: tuple[AgentProviderSpec, ...] = (
    AgentProviderSpec(
        id="openai-api",
        label="OpenAI API",
        kind="api",
        description="OpenAI Chat API。",
        requires=("OPENAI_API_KEY|AIWF_OPENAI_API_KEY",),
    ),
    AgentProviderSpec(
        id="anthropic-api",
        label="Anthropic API",
        kind="api",
        description="Claude Messages API。",
        requires=("ANTHROPIC_API_KEY|AIWF_ANTHROPIC_API_KEY",),
    ),
    AgentProviderSpec(
        id="openai-compatible-api",
        label="OpenAI Compatible API",
        kind="api",
        description="OpenAI 兼容网关。",
        requires=("OPENAI_API_KEY|AIWF_OPENAI_API_KEY", "AIWF_OPENAI_BASE_URL"),
    ),
    AgentProviderSpec(
        id="cursor-agent-acp",
        label="Cursor Agent ACP",
        kind="cli-session",
        description="本机 Cursor Agent ACP 长会话。",
        requires=("AIWF_CURSOR_ACP_CMD|agent", "CURSOR_API_KEY|agent login"),
    ),
    AgentProviderSpec(
        id="codex-agent-acp",
        label="Codex Agent ACP",
        kind="cli-session",
        description="本机 Codex app-server ACP 长会话。",
        requires=("AIWF_CODEX_ACP_CMD|codex",),
    ),
)


def list_agent_provider_specs() -> list[dict[str, object]]:
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "description": spec.description,
            "requires": list(spec.requires),
        }
        for spec in AGENT_PROVIDER_SPECS
    ]


def default_agent_provider() -> str:
    return os.environ.get("AIWF_AGENT_PROVIDER", "cursor-agent-acp")


def normalize_agent_provider(provider: str | None) -> str:
    value = (provider or default_agent_provider()).strip().lower()
    aliases = {
        "openai": "openai-api",
        "anthropic": "anthropic-api",
        "claude": "anthropic-api",
        "cursor": "cursor-agent-acp",
        "cursor-cli": "cursor-agent-acp",
        "cursor-agent-cli": "cursor-agent-acp",
        "codex": "codex-agent-acp",
        "codex-cli": "codex-agent-acp",
    }
    value = aliases.get(value, value)
    known = {spec.id for spec in AGENT_PROVIDER_SPECS}
    if value not in known:
        raise ValueError(f"Unknown agent provider: {provider}")
    return value


def _env_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _command_available(command: str) -> bool:
    token = shlex.split(command, posix=os.name != "nt")[0] if command.strip() else ""
    if not token:
        return False
    return shutil.which(token) is not None


def check_requirement(requirement: str) -> tuple[bool, str]:
    parts = [part.strip() for part in requirement.split("|") if part.strip()]
    if not parts:
        return True, ""
    if len(parts) == 1:
        name = parts[0]
        if _env_set(name):
            return True, name
        if _command_available(name):
            return True, name
        return False, name
    env_names = [part for part in parts if part.isupper() or part.startswith("AIWF_")]
    cli_names = [part for part in parts if part not in env_names]
    for name in env_names:
        if _env_set(name):
            return True, name
    for command in cli_names:
        if _command_available(command):
            return True, command
    missing = env_names[0] if env_names else parts[0]
    return False, missing


def inspect_agent_provider(provider_id: str) -> dict[str, object]:
    provider = normalize_agent_provider(provider_id)
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == provider)
    missing: list[str] = []
    satisfied: list[str] = []
    for requirement in spec.requires:
        ok, detail = check_requirement(requirement)
        if ok:
            satisfied.append(detail or requirement)
        else:
            missing.append(detail or requirement)
    ready = not missing
    if ready:
        status = "ready"
        detail = "配置齐全，可测试连接。"
    else:
        status = "missing"
        detail = f"缺少配置：{', '.join(missing)}"
    return {
        "provider": provider,
        "status": status,
        "ready": ready,
        "missing": missing,
        "satisfied": satisfied,
        "detail": detail,
    }


def test_agent_provider(provider_id: str, *, prompt: str | None = None) -> dict[str, object]:
    inspection = inspect_agent_provider(provider_id)
    if not inspection["ready"]:
        return {
            "status": "missing",
            "message": str(inspection["detail"]),
            "output": "",
        }
    provider = normalize_agent_provider(provider_id)
    if is_acp_provider(provider):
        try:
            workspace = Path(os.environ.get("AIWF_CURSOR_WORKSPACE") or os.getcwd())
            scope = AcpSessionScope(
                provider_id=provider,
                scope_key="__aiwf_ping__",
                workspace=workspace,
            )
            registry = SessionRegistry.get()
            client = registry.acquire(scope)
            chat_id = client.create_chat()
            registry.release_scope(scope.scope_key)
            return {
                "status": "ok",
                "message": f"ACP 握手成功（session={chat_id[:12]}…）。",
                "output": chat_id,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": str(exc),
                "output": "",
            }
    test_prompt = (prompt or "Reply with exactly: AIWF agent ok").strip()
    try:
        api_provider = create_agent_provider(provider_id)
        output = api_provider.generate(test_prompt)
        content = output.strip()
        if not content:
            return {
                "status": "error",
                "message": "Agent 未返回内容。",
                "output": "",
            }
        return {
            "status": "ok",
            "message": "测试成功。",
            "output": content,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "output": "",
        }


def create_agent_provider(provider_id: str | None) -> AgentProvider:
    provider = normalize_agent_provider(provider_id)
    if provider == "openai-api":
        return OpenAIApiProvider()
    if provider == "openai-compatible-api":
        return OpenAICompatibleApiProvider()
    if provider == "anthropic-api":
        return AnthropicApiProvider()
    if is_acp_provider(provider):
        raise RuntimeError(
            f"Provider {provider} is cli-session only; use create_cli_session_provider() and ACP session APIs."
        )
    raise ValueError(f"Unknown agent provider: {provider_id}")


def create_cli_session_provider(provider_id: str | None) -> CliSessionProvider:
    provider = normalize_agent_provider(provider_id)
    if provider == "cursor-agent-acp":
        return CursorAgentAcpProvider()
    if provider == "codex-agent-acp":
        return CodexAgentAcpProvider()
    raise ValueError(f"Not a cli-session provider: {provider_id}")


def stream_provider_generate(provider_id: str, prompt: str) -> Iterator[dict[str, object]]:
    """API-only batch generate stream (CLI providers must use ACP session APIs)."""
    provider = normalize_agent_provider(provider_id)
    if is_acp_provider(provider):
        raise RuntimeError(f"Provider {provider} requires ACP session; use stream_acp_message().")
    yield {"kind": "progress", "stage": "api", "message": "调用 API...", "percent": 20}
    output = create_agent_provider(provider).generate(prompt)
    preview = output.strip().splitlines()
    for line in preview[:24]:
        yield {"kind": "log", "text": line}
    if len(preview) > 24:
        yield {"kind": "log", "text": f"... 共 {len(preview)} 行"}
    yield {"kind": "complete", "output": output}


class OpenAIApiProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "openai-api")

    def generate(self, prompt: str) -> str:
        from .executor import OpenAICompatibleExecutor

        return OpenAICompatibleExecutor.from_env().generate(prompt)


class OpenAICompatibleApiProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "openai-compatible-api")

    def generate(self, prompt: str) -> str:
        from .executor import OpenAICompatibleExecutor

        base_url = os.environ.get("AIWF_OPENAI_BASE_URL", "").strip()
        if not base_url:
            raise RuntimeError("AIWF_OPENAI_BASE_URL is required for openai-compatible-api provider.")
        return OpenAICompatibleExecutor.from_env().generate(prompt)


class AnthropicApiProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "anthropic-api")

    def generate(self, prompt: str) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AIWF_ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY or AIWF_ANTHROPIC_API_KEY is required for anthropic-api provider.")
        model = os.environ.get("AIWF_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        base_url = os.environ.get("AIWF_ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        timeout = int(os.environ.get("AIWF_ANTHROPIC_TIMEOUT", "90"))
        payload = {
            "model": model,
            "max_tokens": int(os.environ.get("AIWF_ANTHROPIC_MAX_TOKENS", "4096")),
            "messages": [{"role": "user", "content": prompt}],
            "system": "You execute one node in a local AI workflow. Return only the requested Markdown artifact.",
        }
        request = Request(
            f"{base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "x-api-key": api_key,
                "anthropic-version": os.environ.get("AIWF_ANTHROPIC_VERSION", "2023-06-01"),
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            blocks = data["content"]
            text_parts = [block["text"] for block in blocks if block.get("type") == "text"]
            content = "\n".join(part.strip() for part in text_parts if part.strip())
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Anthropic response shape: {data}") from exc
        if not content:
            raise RuntimeError("Anthropic response did not contain artifact content.")
        return content.rstrip() + "\n"


class CursorAgentAcpProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "cursor-agent-acp")

    def acquire_session(self, scope: AcpSessionScope) -> CliAcpClient:
        return SessionRegistry.get().acquire(scope)


class CodexAgentAcpProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "codex-agent-acp")

    def acquire_session(self, scope: AcpSessionScope) -> CliAcpClient:
        return SessionRegistry.get().acquire(scope)
