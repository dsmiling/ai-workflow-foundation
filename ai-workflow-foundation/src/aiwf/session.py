from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .execution_result import build_execution_result, normalize_artifact_ref, synthesize_from_artifact
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

    def snapshot_dir(self, run_dir: Path, node_id: str, turn: int) -> Path:
        return self.session_dir(run_dir, node_id) / "snapshots" / f"turn_{turn:03d}"

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

    def save_turn_snapshot(self, run_dir: Path, node_id: str, turn: int, result: ExecutionResult) -> None:
        snap_dir = self.snapshot_dir(run_dir, node_id, turn)
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
        snap_dir.mkdir(parents=True, exist_ok=True)
        for asset in result.assets:
            ref = normalize_artifact_ref(asset.ref)
            src = run_dir / ref
            if not src.is_file():
                continue
            rel = Path(ref).relative_to("artifacts")
            dest = snap_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def restore_turn_snapshot(self, run_dir: Path, node_id: str, turn: int) -> None:
        snap_dir = self.snapshot_dir(run_dir, node_id, turn)
        if not snap_dir.is_dir():
            raise FileNotFoundError(f"No snapshot for turn {turn} on node {node_id}")
        for path in snap_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(snap_dir)
            dest = run_dir / "artifacts" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    def _refresh_result_assets(self, run_dir: Path, result: ExecutionResult) -> ExecutionResult:
        from .models import AssetRecord

        assets: list[AssetRecord] = []
        for asset in result.assets:
            ref = normalize_artifact_ref(asset.ref)
            path = run_dir / ref
            size = 0
            sha = ""
            if path.is_file():
                data = path.read_bytes()
                size = len(data)
                sha = hashlib.sha256(data).hexdigest()
            assets.append(
                AssetRecord(
                    ref=ref,
                    kind=asset.kind,
                    action=asset.action,
                    size=size,
                    sha256=sha,
                )
            )
        return ExecutionResult(
            summary=result.summary,
            assets=assets,
            changes=result.changes,
            primary_ref=result.primary_ref,
        )

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
        self.save_turn_snapshot(run_dir, node.id, 1, result)
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
        self.save_turn_snapshot(run_dir, node.id, next_turn, result)
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

    def revert_to_turn(self, run_dir: Path, node_id: str, target_turn: int) -> ExecutionResult:
        session = self.load_session(run_dir, node_id)
        if session is None:
            raise FileNotFoundError(f"No session for node: {node_id}")
        if target_turn < 1 or target_turn > session.turn:
            raise ValueError(f"Invalid revert target turn: {target_turn}")
        target = self.load_turn(run_dir, node_id, target_turn)
        if target is None:
            raise ValueError(f"Turn not found: {target_turn}")

        self.restore_turn_snapshot(run_dir, node_id, target_turn)

        for turn in self.list_turns(run_dir, node_id):
            if turn.turn <= target_turn:
                continue
            turn_path = self.turns_dir(run_dir, node_id) / f"turn_{turn.turn:03d}.json"
            turn_path.unlink(missing_ok=True)
            snap_path = self.snapshot_dir(run_dir, node_id, turn.turn)
            if snap_path.exists():
                shutil.rmtree(snap_path)

        session.turn = target_turn
        session.status = "iterating"
        session.committed_at = None
        session.updated_at = self.store.now()
        self.save_session(run_dir, session)

        changes = self.aggregate_changelist(run_dir, node_id)
        result = self._refresh_result_assets(
            run_dir,
            ExecutionResult(
                summary=target.result.summary,
                assets=target.result.assets,
                changes=changes,
                primary_ref=target.result.primary_ref,
            ),
        )
        self.store.write_node_result(run_dir, node_id, result)
        return result

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
