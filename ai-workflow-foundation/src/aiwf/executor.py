from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

from pathlib import Path

from .agent_providers import (
    create_agent_provider,
    default_agent_provider,
    inspect_agent_provider,
    is_acp_provider,
    list_agent_provider_specs,
    normalize_agent_provider,
)
from .models import NodeSpec, SkillSpec
from .storage import WorkflowStore
from .workflows import load_skill_ref_content


class Executor(Protocol):
    def run(self, node: NodeSpec, skill: SkillSpec | None, inputs: dict[str, str]) -> str:
        ...


class MockAIExecutor:
    """Deterministic executor used until real LLM/Agent adapters are wired in."""

    def run(self, node: NodeSpec, skill: SkillSpec | None, inputs: dict[str, str]) -> str:
        lines = [
            f"# {node.name}",
            "",
            "## Node",
            "",
            f"- id: `{node.id}`",
            f"- type: `{node.type}`",
            f"- approval: `{node.approval.mode}`",
            "",
        ]
        if skill:
            lines.extend(
                [
                    "## Skill",
                    "",
                    f"- id: `{skill.id}`",
                    f"- goal: {skill.goal}",
                    "",
                    "## Quality Bar",
                    "",
                ]
            )
            if skill.quality:
                lines.extend([f"- {item}" for item in skill.quality])
            else:
                lines.append("- No explicit quality bar configured.")
            lines.append("")
        if node.params:
            lines.extend(["## Node Parameters", ""])
            last_feedback = node.params.get("last_feedback")
            if last_feedback:
                lines.extend(["### Last Feedback", "", str(last_feedback), ""])
            feedback_history = node.params.get("feedback_history", [])
            if feedback_history:
                lines.extend(["### Feedback History", ""])
                for item in feedback_history:
                    feedback = item.get("feedback", item) if isinstance(item, dict) else item
                    lines.append(f"- {feedback}")
                lines.append("")
        lines.extend(["## Inputs", ""])
        if inputs:
            for key, value in inputs.items():
                preview = value.strip().replace("\r\n", "\n")[:500]
                lines.extend([f"### {key}", "", preview or "(empty)", ""])
        else:
            lines.append("No input artifacts were provided.")
            lines.append("")
        lines.extend(
            [
                "## Draft Output",
                "",
                "This is a mock executor artifact. Replace `MockAIExecutor` with a real LLM or Agent executor when the protocol is stable.",
                "",
                "## Structured Summary",
                "",
                f"- produced_by: `{node.id}`",
                "- status: draft",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"


@dataclass(slots=True)
class OpenAICompatibleExecutor:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 90

    @classmethod
    def from_env(cls) -> "OpenAICompatibleExecutor":
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AIWF_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY or AIWF_OPENAI_API_KEY is required for openai executor.")
        return cls(
            api_key=api_key,
            model=os.environ.get("AIWF_OPENAI_MODEL", "gpt-4.1-mini"),
            base_url=os.environ.get("AIWF_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            timeout=int(os.environ.get("AIWF_OPENAI_TIMEOUT", "90")),
        )

    def run(self, node: NodeSpec, skill: SkillSpec | None, inputs: dict[str, str]) -> str:
        return self.generate(build_executor_prompt(node, skill, inputs))

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You execute one node in a local AI workflow. Return only the requested Markdown artifact.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": float(os.environ.get("AIWF_OPENAI_TEMPERATURE", "0.2")),
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response shape: {data}") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM response did not contain artifact content.")
        return content.rstrip() + "\n"


@dataclass(slots=True)
class AgentExecutor:
    provider_id: str
    agent_ref: str | None = None
    store: WorkflowStore | None = None

    def run(self, node: NodeSpec, skill: SkillSpec | None, inputs: dict[str, str]) -> str:
        acp_raw = (node.params or {}).get("_acp_context")
        if isinstance(acp_raw, dict):
            from .node_acp import NodeAcpContext, run_node_acp
            from .session import NodeSessionStore

            if self.store is None:
                raise RuntimeError("ACP node execution requires WorkflowStore on AgentExecutor.")
            context = NodeAcpContext.from_dict(acp_raw)
            sessions = NodeSessionStore(self.store)
            return run_node_acp(node, skill, inputs, context, sessions=sessions)
        agent_context = self._resolve_agent_context(node)
        prompt = build_executor_prompt(node, skill, inputs, agent_context=agent_context)
        provider = normalize_agent_provider(self.provider_id)
        if is_acp_provider(provider):
            raise RuntimeError("ACP provider requires _acp_context on node params.")
        api_provider = create_agent_provider(self.provider_id)
        return api_provider.generate(prompt)

    def _resolve_agent_context(self, node: NodeSpec) -> str | None:
        if self.store is None:
            return None
        from .agents import build_agent_context, load_role_agent

        agent_ref = resolve_agent_ref(
            node,
            self.agent_ref,
            override=None,
        )
        if not agent_ref:
            return None
        role = load_role_agent(self.store, agent_ref)
        if role is None:
            return None
        context = build_agent_context(role)
        return context or None


@dataclass(slots=True)
class SkillExecutor:
    inner: Executor
    root: Path
    skill_dirs: list[Path]

    def run(self, node: NodeSpec, skill: SkillSpec | None, inputs: dict[str, str]) -> str:
        enriched = enrich_skill_spec(skill, self.root) if skill else None
        content = self.inner.run(node, enriched, inputs)
        if enriched and enriched.ref and "Skill Reference Document" not in content:
            return (
                content.rstrip()
                + "\n\n## Skill Orchestration\n\n"
                + f"- skill_executor: `{enriched.id}`\n"
                + f"- ref: `{enriched.ref}`\n"
            )
        return content


def enrich_skill_spec(skill: SkillSpec, root: Path) -> SkillSpec:
    if not skill.ref:
        return skill
    ref_content = load_skill_ref_content(root, skill.ref)
    description = skill.description.strip()
    if description:
        description += "\n\n"
    description += "## Skill Reference Document\n\n" + ref_content.strip()
    return SkillSpec(
        id=skill.id,
        name=skill.name,
        description=description,
        goal=skill.goal,
        output=skill.output,
        quality=skill.quality,
        ref=skill.ref,
        executor=skill.executor,
    )


def should_use_skill_executor(
    node: NodeSpec,
    skill: SkillSpec | None,
    default_executor_name: str,
) -> bool:
    if default_executor_name == "skill":
        return True
    if node.executor == "skill":
        return True
    return bool(skill and skill.executor == "skill")


def normalize_executor_name(name: str | None) -> str:
    executor_name = (name or os.environ.get("AIWF_EXECUTOR") or "mock").lower()
    aliases = {
        "openai": "agent",
        "openai-compatible": "agent",
        "llm": "agent",
    }
    return aliases.get(executor_name, executor_name)


def resolve_inner_executor_name(node: NodeSpec, default_executor_name: str) -> str:
    if node.executor:
        return normalize_executor_name(node.executor)
    return normalize_executor_name(default_executor_name)


def resolve_agent_ref(
    node: NodeSpec,
    default_agent_ref: str | None,
    *,
    override: str | None = None,
) -> str | None:
    if override:
        return override.strip() or None
    if getattr(node, "agent_provider", None):
        return str(node.agent_provider).strip() or None
    if default_agent_ref:
        return default_agent_ref.strip() or None
    return None


def resolve_agent_provider(
    node: NodeSpec,
    default_executor_name: str,
    default_agent_ref: str | None,
    store: WorkflowStore | None = None,
    *,
    override: str | None = None,
) -> str | None:
    from .agents import resolve_agent_provider_id

    agent_ref = resolve_agent_ref(node, default_agent_ref, override=override)
    inner = resolve_inner_executor_name(node, default_executor_name)
    if inner != "agent":
        return None
    if not agent_ref:
        return normalize_agent_provider(default_agent_provider())
    if store is not None:
        try:
            return resolve_agent_provider_id(store, agent_ref)
        except ValueError:
            pass
    return normalize_agent_provider(agent_ref)


def resolve_node_executor(
    node: NodeSpec,
    skill: SkillSpec | None,
    default_executor_name: str,
    default_agent_ref: str | None = None,
    root: Path | None = None,
    skill_dirs: list[Path] | None = None,
    injected: Executor | None = None,
    store: WorkflowStore | None = None,
    *,
    agent_provider_override: str | None = None,
) -> Executor:
    if injected is not None:
        return injected
    root = root or Path.cwd()
    skill_dirs = skill_dirs or []
    inner_name = resolve_inner_executor_name(node, default_executor_name)
    agent_ref = resolve_agent_ref(node, default_agent_ref, override=agent_provider_override)
    provider = resolve_agent_provider(
        node,
        default_executor_name,
        default_agent_ref,
        store,
        override=agent_provider_override,
    )
    inner = create_executor(inner_name, provider, agent_ref=agent_ref, store=store)
    if should_use_skill_executor(node, skill, default_executor_name):
        return SkillExecutor(inner, root, skill_dirs)
    return inner


def create_executor(
    name: str | None = None,
    agent_provider: str | None = None,
    *,
    agent_ref: str | None = None,
    store: WorkflowStore | None = None,
) -> Executor:
    executor_name = normalize_executor_name(name)
    if executor_name == "mock":
        return MockAIExecutor()
    if executor_name == "agent":
        return AgentExecutor(
            normalize_agent_provider(agent_provider),
            agent_ref=agent_ref,
            store=store,
        )
    if executor_name == "skill":
        return create_executor("mock", agent_provider, agent_ref=agent_ref, store=store)
    raise ValueError(f"Unknown executor: {name}")


def build_executor_prompt(
    node: NodeSpec,
    skill: SkillSpec | None,
    inputs: dict[str, str],
    *,
    agent_context: str | None = None,
    session_context: dict[str, object] | None = None,
) -> str:
    lines = [
        "# Workflow Node Execution",
        "",
        "Produce a Markdown artifact for this node.",
        "",
    ]
    if agent_context:
        lines.extend([agent_context, ""])
    lines.extend(
        [
            "## Node",
            "",
            f"- id: {node.id}",
            f"- name: {node.name}",
            f"- type: {node.type}",
            f"- approval: {node.approval.mode}",
            "",
        ]
    )
    if skill:
        lines.extend(
            [
                "## Skill",
                "",
                f"- id: {skill.id}",
                f"- name: {skill.name}",
                f"- description: {skill.description}",
                f"- goal: {skill.goal}",
                "",
                "## Output Contract",
                "",
                json.dumps(skill.output, ensure_ascii=False, indent=2),
                "",
                "## Quality Bar",
                "",
            ]
        )
        lines.extend([f"- {item}" for item in skill.quality] or ["- No explicit quality bar configured."])
        lines.append("")
    if node.params:
        lines.extend(["## Node Parameters", "", json.dumps(node.params, ensure_ascii=False, indent=2), ""])
    lines.extend(["## Inputs", ""])
    if inputs:
        for key, value in inputs.items():
            lines.extend([f"### {key}", "", value, ""])
    else:
        lines.extend(["No input artifacts were provided.", ""])
    ctx = session_context
    if ctx is None and isinstance(node.params.get("_session_context"), dict):
        ctx = node.params["_session_context"]
    if ctx:
        lines.extend(["## Previous Result", ""])
        if ctx.get("prev_summary"):
            lines.extend([str(ctx["prev_summary"]), ""])
        excerpt = ctx.get("prev_content_excerpt") or ctx.get("prev_content")
        if excerpt:
            lines.extend(["### Previous Artifact (excerpt)", "", str(excerpt), ""])
        feedback = ctx.get("feedback") or node.params.get("last_feedback")
        if feedback:
            lines.extend(["## User Feedback (this turn)", "", str(feedback), ""])
        lines.extend(
            [
                "## Iteration Goal",
                "",
                "Preserve useful content from the previous result and apply the feedback incrementally.",
                "Return the full updated Markdown artifact.",
                "",
            ]
        )
    lines.extend(
        [
            "## Requirements",
            "",
            "- Return Markdown only.",
            "- Make assumptions explicit.",
            "- Include risks and open questions when relevant.",
            "- Keep the output useful for a human reviewer.",
        ]
    )
    return "\n".join(lines).rstrip()


def list_executor_catalog() -> dict[str, object]:
    providers = []
    for item in list_agent_provider_specs():
        status = inspect_agent_provider(str(item["id"]))
        providers.append(
            {
                **item,
                "status": status["status"],
                "ready": status["ready"],
                "missing": status["missing"],
                "status_detail": status["detail"],
            }
        )
    return {
        "executors": [
            {"id": "mock", "label": "Mock", "description": "本地模板，不调用模型。"},
            {"id": "agent", "label": "Agent", "description": "通过子执行器调用 API 或 CLI。"},
            {"id": "skill", "label": "Skill 编排", "description": "注入 SKILL.md 后走内层执行器。"},
        ],
        "agent_providers": providers,
        "defaults": {
            "executor": normalize_executor_name(None),
            "agent_provider": default_agent_provider(),
        },
    }
