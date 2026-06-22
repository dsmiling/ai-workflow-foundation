from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agent_providers import normalize_agent_provider
from .agents import resolve_agent_provider_id
from .executor import Executor, create_executor, normalize_executor_name, resolve_node_executor
from copy import deepcopy

from .execution_result import (
    build_execution_result,
    primary_output_name,
    structured_output_name,
    synthesize_from_artifact,
)
from .models import ExecutionResult, NodeRunState, NodeSpec, RunState, SkillSpec, WorkflowSpec
from .session import NodeSessionStore, SessionContext
from .storage import WorkflowStore
from .workflow_graph import WorkflowGraph


TERMINAL_NODE_STATUSES = {"completed", "approved", "skipped"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowRunner:
    def __init__(
        self,
        store: WorkflowStore,
        skill_dirs: list[Path] | None = None,
        executor: Executor | None = None,
        executor_name: str | None = None,
        agent_provider: str | None = None,
    ) -> None:
        self.store = store
        self.skill_dirs = skill_dirs or [
            store.project_root / "examples" / "skills",
            store.aiwf / "skills",
        ]
        self.injected_executor = executor
        self.executor_name = normalize_executor_name(executor_name or os.environ.get("AIWF_EXECUTOR"))
        provider_raw = agent_provider or os.environ.get("AIWF_AGENT_PROVIDER")
        self.agent_ref = provider_raw.strip() if isinstance(provider_raw, str) and provider_raw.strip() else None
        if self.agent_ref or self.executor_name == "agent":
            if self.agent_ref:
                try:
                    self.agent_provider = resolve_agent_provider_id(store, self.agent_ref)
                except ValueError:
                    self.agent_provider = normalize_agent_provider(self.agent_ref)
            else:
                self.agent_provider = normalize_agent_provider(None)
        else:
            self.agent_provider = None
        self.executor = executor or create_executor(
            self.executor_name,
            self.agent_provider,
            agent_ref=self.agent_ref,
            store=store,
        )
        self.sessions = NodeSessionStore(store)

    def iterate_node(
        self,
        run_id: str,
        node_id: str,
        feedback: str,
    ) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        node = next((item for item in workflow.nodes if item.id == node_id), None)
        if node is None:
            raise ValueError(f"Node not found in workflow: {node_id}")
        if node.type == "review":
            raise ValueError("Review nodes do not support iteration.")
        state = self.store.load_state(run_dir)
        session_context = self.sessions.build_session_context(run_dir, node_id, feedback)
        if session_context is None:
            node_state = state.nodes.get(node_id)
            if node_state:
                self.sessions.migrate_legacy_session(run_dir, node, node_state)
                session_context = self.sessions.build_session_context(run_dir, node_id, feedback)
        node_state = self._execute_node_core(
            run_dir,
            workflow,
            node,
            state,
            feedback=feedback,
            session_context=session_context,
        )
        state.nodes[node_id] = node_state
        state.current_node = node_id
        state.status = node_state.status if node_state.status in {"paused", "failed"} else "pending"
        self.store.save_state(run_dir, state)
        return state

    def commit_session(self, run_id: str, node_id: str) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        node = next((item for item in workflow.nodes if item.id == node_id), None)
        if node is None:
            raise ValueError(f"Node not found in workflow: {node_id}")
        committed = self.sessions.commit_session(run_dir, node_id)
        state = self.store.load_state(run_dir)
        existing = state.nodes.get(node_id, NodeRunState(id=node_id))
        if self._node_needs_review(node):
            node_state = NodeRunState(
                id=node_id,
                status="paused",
                phase="review",
                artifact=committed.primary_ref,
                result=committed,
                message="Session committed. Waiting for review decision.",
                started_at=existing.started_at,
                finished_at=utc_now_iso(),
            )
        else:
            node_state = NodeRunState(
                id=node_id,
                status="completed",
                phase="execute",
                artifact=committed.primary_ref,
                result=committed,
                message="Session committed.",
                started_at=existing.started_at,
                finished_at=utc_now_iso(),
            )
        state.nodes[node_id] = node_state
        state.current_node = node_id
        state.status = node_state.status
        self.store.save_state(run_dir, state)
        return state

    def revert_session_turn(self, run_id: str, node_id: str, turn: int) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        node = next((item for item in workflow.nodes if item.id == node_id), None)
        if node is None:
            raise ValueError(f"Node not found in workflow: {node_id}")
        if node.type == "review":
            raise ValueError("Review nodes do not support session revert.")
        result = self.sessions.revert_to_turn(run_dir, node_id, turn)
        state = self.store.load_state(run_dir)
        existing = state.nodes.get(node_id, NodeRunState(id=node_id))
        node_state = NodeRunState(
            id=node_id,
            status="paused",
            phase="execute",
            artifact=result.primary_ref,
            result=result,
            message=f"Reverted to turn {turn}.",
            started_at=existing.started_at,
            finished_at=self.store.now(),
        )
        state.nodes[node_id] = node_state
        state.current_node = node_id
        state.status = "paused"
        self.store.save_state(run_dir, state)
        return state

    def start(self, workflow_path: Path, until_node: str | None = None) -> RunState:
        workflow = self.store.load_workflow(workflow_path)
        run_dir = self.store.create_run(workflow_path, workflow)
        return self._execute(run_dir, workflow, until_node=until_node)

    def run_single_node(
        self,
        run_id: str,
        node_id: str,
        *,
        ensure_upstream: bool = True,
    ) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        graph = WorkflowGraph.from_workflow(workflow)
        if node_id not in graph.nodes_by_id:
            raise ValueError(f"Node not found in workflow: {node_id}")
        if ensure_upstream:
            return self._execute(run_dir, workflow, until_node=node_id)
        node = graph.get_node(node_id)
        state = self.store.load_state(run_dir)
        state.status = "running"
        state.current_node = node_id
        if not state.started_at:
            state.started_at = utc_now_iso()
        self.store.save_state(run_dir, state)
        result = self._run_node(run_dir, workflow, node, state)
        result.started_at = utc_now_iso()
        if result.status != "pending":
            result.finished_at = utc_now_iso()
        state.nodes[node_id] = result
        if result.status in {"paused", "failed"}:
            state.status = result.status
        else:
            state.status = "pending"
            state.current_node = None
        self.store.save_state(run_dir, state)
        return state

    def resume(self, run_id: str) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        return self._execute(run_dir, workflow)

    def rerun_from(self, run_id: str, node_id: str) -> RunState:
        run_dir = self.store.get_run_dir(run_id)
        workflow = self.store.load_locked_workflow(run_dir)
        graph = WorkflowGraph.from_workflow(workflow)
        if node_id not in graph.nodes_by_id:
            raise ValueError(f"Node not found in workflow: {node_id}")
        state = self.store.load_state(run_dir)
        for reset_node_id in graph.collect_reachable_from(node_id):
            state.nodes.pop(reset_node_id, None)
            self.store.invalidate_review(run_dir, reset_node_id)
        state.status = "pending"
        state.current_node = node_id
        self.store.save_state(run_dir, state)
        return self._execute(run_dir, workflow)

    def _execute(
        self,
        run_dir: Path,
        workflow: WorkflowSpec,
        until_node: str | None = None,
    ) -> RunState:
        graph = WorkflowGraph.from_workflow(workflow)
        if until_node is not None and until_node not in graph.nodes_by_id:
            raise ValueError(f"Node not found in workflow: {until_node}")

        state = self.store.load_state(run_dir)
        state.status = "running"
        if not state.started_at:
            state.started_at = utc_now_iso()
        current = graph.execution_entry(state.nodes, state.current_node)
        visited_guard: set[str] = set()

        while current:
            if current in visited_guard and state.nodes.get(current, NodeRunState(id=current)).status in TERMINAL_NODE_STATUSES:
                break
            visited_guard.add(current)

            node = graph.get_node(current)
            node_state = state.nodes.get(node.id, NodeRunState(id=node.id))
            if node_state.status in TERMINAL_NODE_STATUSES:
                state.nodes[node.id] = node_state
                if until_node and node.id == until_node:
                    return self._finish_pending(run_dir, state)
                current = graph.resolve_next(node.id, node_state.status)
                continue

            state.current_node = node.id
            state.nodes[node.id] = node_state
            if not node_state.started_at:
                node_state.started_at = utc_now_iso()
            self.store.save_state(run_dir, state)
            result = self._run_node(run_dir, workflow, node, state)
            result.started_at = node_state.started_at or utc_now_iso()
            if result.status != "pending":
                result.finished_at = utc_now_iso()
            state.nodes[node.id] = result

            if result.status == "paused" or result.status == "failed":
                state.status = result.status
                state.current_node = node.id
                self.store.save_state(run_dir, state)
                return state

            if result.status == "rejected":
                next_id = graph.resolve_next(node.id, "rejected")
                if not next_id and node.type != "review":
                    next_id = node.id
                if next_id:
                    if next_id == node.id:
                        state.nodes.pop(node.id, None)
                        self.store.invalidate_review(run_dir, node.id)
                    else:
                        self._reset_subgraph(run_dir, state, graph, next_id)
                    if until_node and node.id == until_node:
                        return self._finish_pending(run_dir, state)
                    current = next_id
                    self.store.save_state(run_dir, state)
                    continue
                state.status = "rejected"
                state.current_node = node.id
                self.store.save_state(run_dir, state)
                return state

            self.store.save_state(run_dir, state)
            if until_node and node.id == until_node:
                return self._finish_pending(run_dir, state)

            current = graph.resolve_next(node.id, result.status)

        state.status = "completed"
        state.current_node = None
        self.store.save_state(run_dir, state)
        return state

    def _finish_pending(self, run_dir: Path, state: RunState) -> RunState:
        state.status = "pending"
        state.current_node = None
        self.store.save_state(run_dir, state)
        return state

    def _reset_subgraph(
        self,
        run_dir: Path,
        state: RunState,
        graph: WorkflowGraph,
        start_node: str,
    ) -> None:
        for reset_node_id in graph.collect_reachable_from(start_node):
            state.nodes.pop(reset_node_id, None)
            self.store.invalidate_review(run_dir, reset_node_id)

    def _review_mode(self, node: NodeSpec) -> str:
        if node.review:
            return node.review.mode
        return node.approval.mode

    def _node_needs_review(self, node: NodeSpec) -> bool:
        if node.type == "review":
            return True
        return self._review_mode(node) in {"human", "ai"}

    def _run_node(
        self,
        run_dir: Path,
        workflow: WorkflowSpec,
        node: NodeSpec,
        state: RunState,
    ) -> NodeRunState:
        try:
            if node.type == "review":
                return self._run_review_node(run_dir, node)

            existing = state.nodes.get(node.id)
            review = self.store.load_review(run_dir, node.id)
            if existing and existing.artifact and self._node_needs_review(node):
                if review:
                    return self._resolve_review_decision(run_dir, node, review, existing)
                if existing.status == "paused":
                    return NodeRunState(
                        id=node.id,
                        status="paused",
                        phase="review",
                        artifact=existing.artifact,
                        result=existing.result or self._load_or_synthesize_result(run_dir, node.id, existing.artifact),
                        message="Execution finished. Waiting for review decision.",
                        started_at=existing.started_at,
                        finished_at=existing.finished_at,
                    )

            return self._execute_node_core(run_dir, workflow, node, state)
        except Exception as exc:
            return NodeRunState(id=node.id, status="failed", phase="execute", message=str(exc))

    def _execute_node_core(
        self,
        run_dir: Path,
        workflow: WorkflowSpec,
        node: NodeSpec,
        state: RunState,
        *,
        feedback: str = "",
        session_context: SessionContext | None = None,
    ) -> NodeRunState:
        existing = state.nodes.get(node.id)
        skill = self._load_skill(node)
        run_node = deepcopy(node)
        if session_context:
            params = dict(run_node.params)
            params["_session_context"] = session_context.to_dict()
            if feedback:
                params["last_feedback"] = feedback
            run_node.params = params
        inputs = self._resolve_inputs(run_dir, state, run_node)
        executor = resolve_node_executor(
            run_node,
            skill,
            self.executor_name,
            self.agent_ref,
            self.store.project_root,
            self.skill_dirs,
            injected=self.injected_executor,
            store=self.store,
        )
        content = executor.run(run_node, skill, inputs)
        filename = primary_output_name(run_node, skill)
        had_artifact = bool(existing and existing.artifact)
        action = "modify" if had_artifact or session_context else "create"
        artifact_ref = self.store.write_artifact(run_dir, node.id, filename, content)
        structured_ref = self._write_structured_artifact(run_dir, node, skill, filename, content)
        execution_result = build_execution_result(
            node,
            content,
            artifact_ref,
            structured_ref=structured_ref,
            action=action,
            run_dir=run_dir,
        )
        self.store.write_node_result(run_dir, node.id, execution_result)
        self.sessions.record_turn(
            run_dir,
            node,
            execution_result,
            feedback=feedback,
            session_context=session_context,
        )
        started_at = existing.started_at if existing and existing.started_at else utc_now_iso()
        if self._node_needs_review(node):
            return NodeRunState(
                id=node.id,
                status="paused",
                phase="review",
                artifact=execution_result.primary_ref,
                result=execution_result,
                message="Execution finished. Waiting for review decision.",
                started_at=started_at,
                finished_at=utc_now_iso(),
            )
        return NodeRunState(
            id=node.id,
            status="completed",
            phase="execute",
            artifact=execution_result.primary_ref,
            result=execution_result,
            message="Node completed.",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    def _resolve_review_decision(
        self,
        run_dir: Path,
        node: NodeSpec,
        review: dict[str, object],
        existing: NodeRunState | None = None,
    ) -> NodeRunState:
        decision = review.get("decision")
        artifact = existing.artifact if existing else None
        result = existing.result if existing else None
        if result is None and artifact:
            result = self._load_or_synthesize_result(run_dir, node.id, artifact)
        started_at = existing.started_at if existing else ""
        finished_at = existing.finished_at if existing else utc_now_iso()
        if decision == "approve":
            status = "approved" if node.type == "review" else "completed"
            return NodeRunState(
                id=node.id,
                status=status,
                phase="review",
                artifact=artifact,
                result=result,
                message="Review approved.",
                started_at=started_at,
                finished_at=finished_at,
            )
        return NodeRunState(
            id=node.id,
            status="rejected",
            phase="review",
            artifact=artifact,
            result=result,
            message=f"Review rejected: {review.get('feedback', '')}",
            started_at=started_at,
            finished_at=finished_at,
        )

    def _run_review_node(self, run_dir: Path, node: NodeSpec) -> NodeRunState:
        review = self.store.load_review(run_dir, node.id)
        if not review:
            return NodeRunState(
                id=node.id,
                status="paused",
                phase="review",
                message="Waiting for review decision.",
            )
        state = self.store.load_state(run_dir)
        existing = state.nodes.get(node.id)
        return self._resolve_review_decision(run_dir, node, review, existing)

    def _load_or_synthesize_result(
        self,
        run_dir: Path,
        node_id: str,
        artifact: str | None,
    ) -> ExecutionResult | None:
        stored = self.store.read_node_result(run_dir, node_id)
        if stored:
            return stored
        return synthesize_from_artifact(node_id, artifact, run_dir=run_dir)

    def _load_skill(self, node: NodeSpec) -> SkillSpec | None:
        if not node.skill:
            return None
        from .skills import ensure_skill_ref

        skill = self.store.load_skill(node.skill, self.skill_dirs)
        return ensure_skill_ref(skill, self.store, self.skill_dirs)

    def _write_structured_artifact(
        self,
        run_dir: Path,
        node: NodeSpec,
        skill: SkillSpec | None,
        primary_filename: str,
        content: str,
    ) -> str | None:
        structured_name = structured_output_name(node, skill)
        if not structured_name:
            return None
        primary_ref = primary_filename
        if "/" not in primary_ref:
            primary_ref = f"artifacts/{primary_ref}"
        payload: dict[str, object] = {
            "node_id": node.id,
            "skill_id": skill.id if skill else None,
            "primary_artifact": primary_ref,
            "status": "draft",
            "summary": f"Structured sidecar for {node.name}",
            "content_preview": content.strip().replace("\r\n", "\n")[:240],
        }
        if node.id == "module_mapping":
            payload["modules"] = [
                {
                    "id": "login_reward",
                    "standard_lib_supported": False,
                    "risk": "needs review",
                },
                {
                    "id": "milestone_reward",
                    "standard_lib_supported": True,
                    "risk": "low",
                },
                {
                    "id": "ranking_reward",
                    "standard_lib_supported": False,
                    "risk": "needs review",
                },
            ]
        structured_content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        return self.store.write_artifact(run_dir, node.id, structured_name, structured_content)

    def _resolve_input_source(
        self,
        run_dir: Path,
        state: RunState,
        source: object,
    ) -> str:
        if isinstance(source, dict):
            src_type = str(source.get("source", "literal"))
            if src_type == "artifact":
                node_id = str(source.get("ref", ""))
                if not node_id:
                    raise ValueError("Artifact input binding requires ref.")
                upstream = state.nodes.get(node_id)
                if not upstream or not upstream.artifact:
                    raise ValueError(f"Input references missing artifact: {node_id}")
                return self.store.read_artifact_ref(run_dir, upstream.artifact)
            return str(source.get("value", ""))
        if isinstance(source, str):
            if source.startswith("artifact."):
                node_id = source.removeprefix("artifact.")
                upstream = state.nodes.get(node_id)
                if not upstream or not upstream.artifact:
                    raise ValueError(f"Input references missing artifact: {source}")
                return self.store.read_artifact_ref(run_dir, upstream.artifact)
            return source
        return str(source)

    def _resolve_inputs(self, run_dir: Path, state: RunState, node: NodeSpec) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for input_name, source in node.inputs.items():
            resolved[input_name] = self._resolve_input_source(run_dir, state, source)
        return resolved
