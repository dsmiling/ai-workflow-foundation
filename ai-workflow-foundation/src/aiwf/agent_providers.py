from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen


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
        id="cursor-agent-cli",
        label="Cursor Agent CLI",
        kind="cli",
        description="本机 Cursor Agent CLI。",
        requires=("AIWF_CURSOR_AGENT_CMD|agent",),
    ),
    AgentProviderSpec(
        id="codex-cli",
        label="Codex CLI",
        kind="cli",
        description="本机 Codex CLI。",
        requires=("AIWF_CODEX_CLI_CMD|codex",),
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
    return os.environ.get("AIWF_AGENT_PROVIDER", "openai-api")


def normalize_agent_provider(provider: str | None) -> str:
    value = (provider or default_agent_provider()).strip().lower()
    aliases = {
        "openai": "openai-api",
        "anthropic": "anthropic-api",
        "claude": "anthropic-api",
        "cursor": "cursor-agent-cli",
        "cursor-cli": "cursor-agent-cli",
        "codex": "codex-cli",
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


def build_cli_argv(command: str, prompt: str) -> list[str]:
    argv = shlex.split(command, posix=os.name != "nt")
    if not argv:
        raise RuntimeError("CLI command is empty.")
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    return [*argv, prompt]


def check_requirement(requirement: str) -> tuple[bool, str]:
    parts = [part.strip() for part in requirement.split("|") if part.strip()]
    if not parts:
        return True, ""
    if len(parts) == 1:
        name = parts[0]
        if _env_set(name):
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
    test_prompt = (prompt or "Reply with exactly: AIWF agent ok").strip()
    try:
        provider = create_agent_provider(provider_id)
        output = provider.generate(test_prompt)
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
    if provider == "cursor-agent-cli":
        return CursorAgentCliProvider()
    if provider == "codex-cli":
        return CodexCliProvider()
    raise ValueError(f"Unknown agent provider: {provider_id}")


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


class CursorAgentCliProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "cursor-agent-cli")

    def generate(self, prompt: str) -> str:
        command = os.environ.get(
            "AIWF_CURSOR_AGENT_CMD",
            "agent --trust --print --output-format text",
        )
        return run_cli_prompt(command, prompt, timeout=int(os.environ.get("AIWF_CURSOR_AGENT_TIMEOUT", "300")))


class CodexCliProvider:
    spec = next(item for item in AGENT_PROVIDER_SPECS if item.id == "codex-cli")

    def generate(self, prompt: str) -> str:
        command = os.environ.get(
            "AIWF_CODEX_CLI_CMD",
            "codex exec --sandbox workspace-write --skip-git-repo-check",
        )
        return run_codex_prompt(command, prompt, timeout=int(os.environ.get("AIWF_CODEX_CLI_TIMEOUT", "300")))


def run_codex_prompt(command: str, prompt: str, *, timeout: int) -> str:
    argv = shlex.split(command, posix=os.name != "nt")
    if not argv:
        raise RuntimeError("CLI command is empty.")
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    has_output_flag = "--output-last-message" in argv or "-o" in argv
    output_path: str | None = None
    run_argv = list(argv)
    if not has_output_flag:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp:
            output_path = tmp.name
        run_argv.extend(["-o", output_path])
    completed = subprocess.run(
        [*run_argv, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if output_path:
            Path(output_path).unlink(missing_ok=True)
        raise RuntimeError(detail or f"CLI exited with code {completed.returncode}")
    content = ""
    if output_path and Path(output_path).exists():
        content = Path(output_path).read_text(encoding="utf-8").strip()
        Path(output_path).unlink(missing_ok=True)
    if not content:
        content = (completed.stdout or "").strip()
    if not content:
        raise RuntimeError("CLI did not return artifact content.")
    return content.rstrip() + "\n"


def run_cli_prompt(command: str, prompt: str, *, timeout: int) -> str:
    output = ""
    for event in stream_cli_prompt(command, prompt, timeout=timeout):
        if event.get("kind") == "complete":
            output = str(event.get("output") or "")
    if not output.strip():
        raise RuntimeError("CLI did not return artifact content.")
    return output


def stream_cli_prompt(command: str, prompt: str, *, timeout: int) -> Iterator[dict[str, object]]:
    argv = build_cli_argv(command, prompt)
    yield {"kind": "progress", "stage": "cli", "message": f"启动 {Path(argv[0]).name}...", "percent": 12}
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=False,
        stdin=subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    line_queue: queue.Queue[tuple[str, str] | None] = queue.Queue()

    def pump(stream, label: str) -> None:
        for line in iter(stream.readline, ""):
            line_queue.put((label, line.rstrip("\r\n")))
        stream.close()
        line_queue.put(None)

    threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True).start()
    threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True).start()
    finished_streams = 0
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    deadline = time.time() + timeout
    while finished_streams < 2:
        if time.time() > deadline:
            proc.kill()
            raise RuntimeError(f"CLI timed out after {timeout} seconds")
        try:
            item = line_queue.get(timeout=0.2)
        except queue.Empty:
            if proc.poll() is not None and line_queue.empty():
                break
            continue
        if item is None:
            finished_streams += 1
            continue
        label, text = item
        if not text:
            continue
        if label == "stdout":
            stdout_lines.append(text)
            yield {"kind": "log", "text": text}
        else:
            stderr_lines.append(text)
            yield {"kind": "log", "text": f"[stderr] {text}"}
    return_code = proc.wait(timeout=5)
    if return_code != 0:
        detail = "\n".join((stderr_lines or stdout_lines)[-20:]).strip()
        raise RuntimeError(detail or f"CLI exited with code {return_code}")
    content = "\n".join(stdout_lines).strip()
    if not content:
        content = "\n".join(stderr_lines).strip()
    if not content:
        raise RuntimeError("CLI did not return artifact content.")
    yield {"kind": "complete", "output": content.rstrip() + "\n"}


def stream_provider_generate(provider_id: str, prompt: str) -> Iterator[dict[str, object]]:
    provider = normalize_agent_provider(provider_id)
    if provider == "cursor-agent-cli":
        command = os.environ.get(
            "AIWF_CURSOR_AGENT_CMD",
            "agent --trust --print --output-format text",
        )
        timeout = int(os.environ.get("AIWF_CURSOR_AGENT_TIMEOUT", "300"))
        yield from stream_cli_prompt(command, prompt, timeout=timeout)
        return
    if provider == "codex-cli":
        command = os.environ.get(
            "AIWF_CODEX_CLI_CMD",
            "codex exec --sandbox workspace-write --skip-git-repo-check",
        )
        timeout = int(os.environ.get("AIWF_CODEX_CLI_TIMEOUT", "300"))
        yield {"kind": "progress", "stage": "cli", "message": "启动 codex...", "percent": 12}
        output = run_codex_prompt(command, prompt, timeout=timeout)
        for line in output.splitlines()[:30]:
            yield {"kind": "log", "text": line}
        yield {"kind": "complete", "output": output}
        return
    yield {"kind": "progress", "stage": "api", "message": "调用 API...", "percent": 20}
    output = create_agent_provider(provider).generate(prompt)
    preview = output.strip().splitlines()
    for line in preview[:24]:
        yield {"kind": "log", "text": line}
    if len(preview) > 24:
        yield {"kind": "log", "text": f"... 共 {len(preview)} 行"}
    yield {"kind": "complete", "output": output}
