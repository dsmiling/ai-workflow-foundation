"""Node-level ACP execution (L2 Turn1 / L3 iterate)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .agent_providers import create_cli_session_provider, is_acp_provider, normalize_agent_provider
from .cli_acp import AcpSessionScope, stream_acp_message
from .execution_result import primary_output_name
from .models import NodeSpec, SkillSpec
from .session import NodeSession, NodeSessionStore
from .unity_aibridge import maybe_collect_unity_context, unity_context_task_section


@dataclass(slots=True)
class NodeAcpContext:
    run_id: str
    run_dir: Path
    workspace: Path
    provider_id: str
    artifact_rel: str
    iterate: bool = False
    feedback: str = ""
    acp_chat_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "workspace": str(self.workspace),
            "provider_id": self.provider_id,
            "artifact_rel": self.artifact_rel,
            "iterate": self.iterate,
            "feedback": self.feedback,
            "acp_chat_id": self.acp_chat_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> NodeAcpContext:
        return cls(
            run_id=str(data.get("run_id") or ""),
            run_dir=Path(str(data.get("run_dir") or ".")),
            workspace=Path(str(data.get("workspace") or ".")),
            provider_id=str(data.get("provider_id") or "cursor-agent-acp"),
            artifact_rel=str(data.get("artifact_rel") or ""),
            iterate=bool(data.get("iterate")),
            feedback=str(data.get("feedback") or ""),
            acp_chat_id=str(data["acp_chat_id"]) if data.get("acp_chat_id") else None,
        )


def _write_task_bootstrap(
    workspace: Path,
    *,
    node: NodeSpec,
    skill: SkillSpec | None,
    inputs: dict[str, str],
    artifact_rel: str,
    unity_written: list[str] | None = None,
    unity_errors: list[str] | None = None,
) -> None:
    lines = [
        f"# Node Task: {node.name} ({node.id})",
        "",
        f"Output artifact (write here): `{artifact_rel}`",
        "",
    ]
    if skill:
        lines.extend([f"Skill: {skill.id}", f"Goal: {skill.goal}", ""])
    if unity_written is not None or unity_errors:
        lines.extend(unity_context_task_section(unity_written or [], unity_errors or []))
    if inputs:
        lines.append("## Inputs")
        lines.append("")
        for key, value in inputs.items():
            preview = value.strip()[:800]
            lines.extend([f"### {key}", "", preview or "(empty)", ""])
    task_path = workspace / "task.md"
    task_path.write_text("\n".join(lines), encoding="utf-8")


def run_node_acp(
    node: NodeSpec,
    skill: SkillSpec | None,
    inputs: dict[str, str],
    context: NodeAcpContext,
    *,
    sessions: NodeSessionStore,
) -> str:
    provider = normalize_agent_provider(context.provider_id)
    if not is_acp_provider(provider):
        raise RuntimeError(f"Node ACP requires cli-session provider, got {provider}")
    workspace = context.workspace
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_path = context.run_dir / context.artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    session = sessions.open_or_get_session(context.run_dir, node)
    chat_id = context.acp_chat_id or session.acp_chat_id
    scope_key = f"{context.run_id}:{node.id}"
    scope = AcpSessionScope(
        provider_id=provider,
        scope_key=scope_key,
        workspace=workspace,
        chat_id=chat_id,
    )
    if not chat_id:
        unity_written, unity_errors = maybe_collect_unity_context(
            context.run_dir,
            node.params,
        )
        _write_task_bootstrap(
            workspace,
            node=node,
            skill=skill,
            inputs=inputs,
            artifact_rel=context.artifact_rel,
            unity_written=unity_written,
            unity_errors=unity_errors,
        )
        client = create_cli_session_provider(provider).acquire_session(scope)
        chat_id = client.create_chat()
        session.acp_chat_id = chat_id
        session.acp_provider_id = provider
        sessions.save_session(context.run_dir, session)
        scope = AcpSessionScope(
            provider_id=provider,
            scope_key=scope_key,
            workspace=workspace,
            chat_id=chat_id,
        )
        user_text = "\n".join(
            [
                f"Execute node `{node.id}` per task.md.",
                f"Write the primary artifact to: {context.artifact_rel}",
            ]
        )
    else:
        if context.iterate:
            if not session.acp_chat_id:
                raise ValueError("节点尚未完成 Turn1 执行，无法 iterate。请先执行节点。")
            user_text = "\n".join(
                [
                    context.feedback.strip() or "Apply feedback to improve the artifact.",
                    f"Update artifact: {context.artifact_rel}",
                ]
            )
        else:
            user_text = "\n".join(
                [
                    f"Re-run node `{node.id}`.",
                    f"Update artifact: {context.artifact_rel}",
                ]
            )
    for event in stream_acp_message(scope, user_text):
        if event.get("type") == "done":
            break
    if artifact_path.exists():
        return artifact_path.read_text(encoding="utf-8").rstrip() + "\n"
    alt = workspace / Path(context.artifact_rel).name
    if alt.exists():
        content = alt.read_text(encoding="utf-8").rstrip() + "\n"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return content
    raise RuntimeError(f"ACP node run did not produce artifact at {context.artifact_rel}")


def build_node_acp_context(
    *,
    run_id: str,
    run_dir: Path,
    node: NodeSpec,
    skill: SkillSpec | None,
    provider_id: str,
    session: NodeSession | None = None,
    iterate: bool = False,
    feedback: str = "",
) -> NodeAcpContext:
    filename = primary_output_name(node, skill)
    artifact_rel = f"artifacts/{node.id}/{filename}"
    workspace = run_dir
    return NodeAcpContext(
        run_id=run_id,
        run_dir=run_dir,
        workspace=workspace,
        provider_id=provider_id,
        artifact_rel=artifact_rel,
        iterate=iterate,
        feedback=feedback,
        acp_chat_id=session.acp_chat_id if session else None,
    )
