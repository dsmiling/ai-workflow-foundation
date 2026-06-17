from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .execution_result import build_execution_result, synthesize_from_artifact
from .models import ChangeItem, ExecutionResult, JsonDict, NodeRunState, NodeSpec, RunState, SkillSpec


@dataclass(slots=True)
class SessionContext:
    prev_primary_ref: str
    prev_summary: str
    prev_content: str = ""
    feedback: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "prev_primary_ref": self.prev_primary_ref,
            "prev_summary": self.prev_summary,
        }
        if self.prev_content:
            payload["prev_content_excerpt"] = self.prev_content[:1200]
        return payload


@dataclass(slots=True)
class NodeSession:
    node_id: str
    status: str = "iterating"
    turn: int = 0
    skill_ref: str | None = None
    skill_override: JsonDict | None = None
    inputs_overlay: JsonDict = field(default_factory=dict)
    committed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "node_id": self.node_id,
            "status": self.status,
            "turn": self.turn,
            "inputs_overlay": self.inputs_overlay,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.skill_ref:
            payload["skill_ref"] = self.skill_ref
        if self.skill_override:
            payload["skill_override"] = self.skill_override
        if self.committed_at:
            payload["committed_at"] = self.committed_at
        return payload

    @classmethod
    def from_dict(cls, data: JsonDict) -> "NodeSession":
        return cls(
            node_id=str(data["node_id"]),
            status=str(data.get("status", "iterating")),
            turn=int(data.get("turn", 0)),
            skill_ref=data.get("skill_ref"),
            skill_override=data.get("skill_override") if isinstance(data.get("skill_override"), dict) else None,
            inputs_overlay=dict(data.get("inputs_overlay", {})),
            committed_at=data.get("committed_at"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass(slots=True)
class SessionTurn:
    turn: int
    result: ExecutionResult
    feedback: str = ""
    session_context: SessionContext | None = None
    change_refs: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "turn": self.turn,
            "result": self.result.to_dict(),
            "feedback": self.feedback,
            "change_refs": self.change_refs,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.session_context:
            payload["session_context"] = self.session_context.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: JsonDict) -> "SessionTurn":
        ctx_raw = data.get("session_context")
        context = None
        if isinstance(ctx_raw, dict):
            context = SessionContext(
                prev_primary_ref=str(ctx_raw.get("prev_primary_ref", "")),
                prev_summary=str(ctx_raw.get("prev_summary", "")),
                prev_content=str(ctx_raw.get("prev_content_excerpt", "")),
            )
        return cls(
            turn=int(data.get("turn", 0)),
            feedback=str(data.get("feedback", "")),
            change_refs=[str(item) for item in data.get("change_refs", [])],
            session_context=context,
            result=ExecutionResult.from_dict(data.get("result", {})),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
        )


class NodeSessionStore:
    def __init__(self, store: Any) -> None:
        self.store = store

    def session_dir(self, run_dir: Path, node_id: str) -> Path:
        return run_dir / "node_sessions" / node_id

    def session_path(self, run_dir: Path, node_id: str) -> Path:
        return self.session_dir(run_dir, node_id) / "session.json"

    def turns_dir(self, run_dir: Path, node_id: str) -> Path:
        return self.session_dir(run_dir, node_id) / "turns"

    def load_session(self, run_dir: Path, node_id: str) -> NodeSession | None:
        path = self.session_path(run_dir, node_id)
        if not path.exists():
            return None
        return NodeSession.from_dict(self.store.read_json(path))

    def save_session(self, run_dir: Path, session: NodeSession) -> None:
        session.updated_at = self.store.now()
        if not session.created_at:
            session.created_at = session.updated_at
        self.session_dir(run_dir, session.node_id).mkdir(parents=True, exist_ok=True)
        self.turns_dir(run_dir, session.node_id).mkdir(parents=True, exist_ok=True)
        self.store.write_json(self.session_path(run_dir, session.node_id), session.to_dict())

    def load_turn(self, run_dir: Path, node_id: str, turn: int) -> SessionTurn | None:
        path = self.turns_dir(run_dir, node_id) / f"turn_{turn:03d}.json"
        if not path.exists():
            return None
        return SessionTurn.from_dict(self.store.read_json(path))

    def save_turn(self, run_dir: Path, node_id: str, turn: SessionTurn) -> None:
        self.turns_dir(run_dir, node_id).mkdir(parents=True, exist_ok=True)
        self.store.write_json(self.turns_dir(run_dir, node_id) / f"turn_{turn.turn:03d}.json", turn.to_dict())

    def list_turns(self, run_dir: Path, node_id: str) -> list[SessionTurn]:
        turns_dir = self.turns_dir(run_dir, node_id)
        if not turns_dir.exists():
            return []
        turns: list[SessionTurn] = []
        for path in sorted(turns_dir.glob("turn_*.json")):
            turns.append(SessionTurn.from_dict(self.store.read_json(path)))
        return turns

    def max_turns_for(self, node: NodeSpec) -> int:
        iteration = node.params.get("iteration", {}) if node.params else {}
        if isinstance(iteration, dict):
            try:
                return max(1, int(iteration.get("max_turns", 10)))
            except (TypeError, ValueError):
                pass
        return 10

    def migrate_legacy_session(
        self,
        run_dir: Path,
        node: NodeSpec,
        node_state: NodeRunState,
    ) -> NodeSession:
        session = NodeSession(
            node_id=node.id,
            status="iterating",
            turn=1,
            skill_ref=node.skill,
            created_at=self.store.now(),
            updated_at=self.store.now(),
        )
        result = node_state.result
        if result is None and node_state.artifact:
            result = synthesize_from_artifact(node.id, node_state.artifact, run_dir=run_dir)
        if result is None:
            result = ExecutionResult(summary="", assets=[], changes=[], primary_ref="")
        self.save_session(run_dir, session)
        self.save_turn(
            run_dir,
            node.id,
            SessionTurn(
                turn=1,
                feedback="",
                result=result,
                started_at=node_state.started_at,
                finished_at=node_state.finished_at,
            ),
        )
        return session

    def open_or_get_session(
        self,
        run_dir: Path,
        node: NodeSpec,
        node_state: NodeRunState | None = None,
    ) -> NodeSession:
        existing = self.load_session(run_dir, node.id)
        if existing:
            return existing
        if node_state and (node_state.artifact or node_state.result):
            return self.migrate_legacy_session(run_dir, node, node_state)
        session = NodeSession(
            node_id=node.id,
            status="iterating",
            turn=0,
            skill_ref=node.skill,
            created_at=self.store.now(),
            updated_at=self.store.now(),
        )
        self.save_session(run_dir, session)
        return session

    def record_turn(
        self,
        run_dir: Path,
        node: NodeSpec,
        result: ExecutionResult,
        *,
        feedback: str = "",
        session_context: SessionContext | None = None,
    ) -> tuple[NodeSession, SessionTurn]:
        state = self.store.load_state(run_dir)
        node_state = state.nodes.get(node.id)
        session = self.open_or_get_session(run_dir, node, node_state)
        if session.status == "committed":
            session.status = "iterating"
        next_turn = session.turn + 1
        if next_turn > self.max_turns_for(node):
            raise ValueError(f"Session max turns exceeded for node {node.id}")
        turn = SessionTurn(
            turn=next_turn,
            feedback=feedback,
            session_context=session_context,
            result=result,
            started_at=self.store.now(),
            finished_at=self.store.now(),
        )
        self.save_turn(run_dir, node.id, turn)
        session.turn = next_turn
        session.updated_at = self.store.now()
        self.save_session(run_dir, session)
        return session, turn

    def aggregate_changelist(self, run_dir: Path, node_id: str) -> list[ChangeItem]:
        merged: dict[str, ChangeItem] = {}
        for turn in self.list_turns(run_dir, node_id):
            for change in turn.result.changes:
                merged[change.target] = change
        return list(merged.values())

    def commit_session(self, run_dir: Path, node_id: str) -> ExecutionResult:
        session = self.load_session(run_dir, node_id)
        if not session:
            raise FileNotFoundError(f"No session for node: {node_id}")
        turns = self.list_turns(run_dir, node_id)
        if not turns:
            raise ValueError(f"Session has no turns: {node_id}")
        last = turns[-1]
        changes = self.aggregate_changelist(run_dir, node_id)
        committed = ExecutionResult(
            summary=last.result.summary,
            assets=last.result.assets,
            changes=changes,
            primary_ref=last.result.primary_ref,
        )
        session.status = "committed"
        session.committed_at = self.store.now()
        session.updated_at = session.committed_at
        self.save_session(run_dir, session)
        self.store.write_node_result(run_dir, node_id, committed)
        return committed

    def build_session_context(
        self,
        run_dir: Path,
        node_id: str,
        feedback: str,
    ) -> SessionContext | None:
        session = self.load_session(run_dir, node_id)
        if not session or session.turn < 1:
            return None
        prev = self.load_turn(run_dir, node_id, session.turn)
        if not prev:
            return None
        content = ""
        if prev.result.primary_ref:
            try:
                content = self.store.read_artifact_ref(run_dir, prev.result.primary_ref)
            except FileNotFoundError:
                content = ""
        return SessionContext(
            prev_primary_ref=prev.result.primary_ref,
            prev_summary=prev.result.summary,
            prev_content=content,
            feedback=feedback,
        )
