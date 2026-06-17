from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(slots=True)
class SkillSpec:
    id: str
    name: str
    description: str
    goal: str
    output: JsonDict = field(default_factory=dict)
    quality: list[str] = field(default_factory=list)
    ref: str = ""
    executor: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "SkillSpec":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            goal=data.get("goal", ""),
            output=data.get("output", {}),
            quality=list(data.get("quality", [])),
            ref=str(data.get("ref", "")),
            executor=str(data.get("executor", "")),
        )


@dataclass(slots=True)
class ApprovalSpec:
    mode: str = "auto"
    level: str = "optional"

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "ApprovalSpec":
        if not data:
            return cls()
        return cls(mode=data.get("mode", "auto"), level=data.get("level", "optional"))


@dataclass(slots=True)
class ReviewSpec:
    mode: str = "auto"
    level: str = "optional"
    inputs: JsonDict = field(default_factory=dict)
    skill: str | None = None
    criteria: str = ""
    checklist: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "ReviewSpec":
        if not data:
            return cls()
        skill = data.get("skill")
        checklist = data.get("checklist", [])
        return cls(
            mode=str(data.get("mode", "auto")),
            level=str(data.get("level", "optional")),
            inputs=dict(data.get("inputs", {})),
            skill=str(skill) if skill else None,
            criteria=str(data.get("criteria", "")),
            checklist=[str(item) for item in checklist] if isinstance(checklist, list) else [],
        )


@dataclass(slots=True)
class NodeSpec:
    id: str
    name: str
    type: str
    skill: str | None = None
    executor: str | None = None
    agent_provider: str | None = None
    test_executor: str | None = None
    test_agent_provider: str | None = None
    inputs: JsonDict = field(default_factory=dict)
    outputs: JsonDict = field(default_factory=dict)
    params: JsonDict = field(default_factory=dict)
    approval: ApprovalSpec = field(default_factory=ApprovalSpec)
    review: ReviewSpec | None = None

    @classmethod
    def from_dict(cls, data: JsonDict) -> "NodeSpec":
        executor = data.get("executor")
        agent_provider = data.get("agent_provider")
        test_executor = data.get("test_executor")
        test_agent_provider = data.get("test_agent_provider")
        review_raw = data.get("review")
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            type=data.get("type", "ai"),
            skill=data.get("skill"),
            executor=str(executor) if executor else None,
            agent_provider=str(agent_provider) if agent_provider else None,
            test_executor=str(test_executor) if test_executor else None,
            test_agent_provider=str(test_agent_provider) if test_agent_provider else None,
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            params=data.get("params", {}),
            approval=ApprovalSpec.from_dict(data.get("approval")),
            review=ReviewSpec.from_dict(review_raw) if isinstance(review_raw, dict) else None,
        )


@dataclass(slots=True)
class TransitionSpec:
    from_node: str
    to: str
    when: str = "always"

    @classmethod
    def from_dict(cls, data: JsonDict) -> "TransitionSpec":
        from_value = data.get("from")
        if not isinstance(from_value, str) or not from_value.strip():
            raise ValueError("transition.from must be a non-empty string.")
        to_value = data.get("to")
        if not isinstance(to_value, str) or not to_value.strip():
            raise ValueError("transition.to must be a non-empty string.")
        return cls(
            from_node=from_value,
            to=to_value,
            when=str(data.get("when", "always")),
        )

    def to_dict(self) -> JsonDict:
        return {"from": self.from_node, "to": self.to, "when": self.when}


@dataclass(slots=True)
class WorkflowSpec:
    id: str
    name: str
    nodes: list[NodeSpec]
    initial: str = ""
    transitions: list[TransitionSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "WorkflowSpec":
        transitions_raw = data.get("transitions", [])
        transitions: list[TransitionSpec] = []
        if transitions_raw:
            if not isinstance(transitions_raw, list):
                raise ValueError("workflow.transitions must be a list.")
            transitions = [TransitionSpec.from_dict(item) for item in transitions_raw]
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            nodes=[NodeSpec.from_dict(item) for item in data.get("nodes", [])],
            initial=str(data.get("initial", "")),
            transitions=transitions,
        )


@dataclass(slots=True)
class ChangeItem:
    action: str
    target: str
    summary: str

    def to_dict(self) -> JsonDict:
        return {"action": self.action, "target": self.target, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ChangeItem":
        return cls(
            action=str(data.get("action", "create")),
            target=str(data.get("target", "")),
            summary=str(data.get("summary", "")),
        )


@dataclass(slots=True)
class AssetRecord:
    ref: str
    kind: str
    action: str
    size: int = 0
    sha256: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {"ref": self.ref, "kind": self.kind, "action": self.action}
        if self.size:
            payload["size"] = self.size
        if self.sha256:
            payload["sha256"] = self.sha256
        return payload

    @classmethod
    def from_dict(cls, data: JsonDict) -> "AssetRecord":
        return cls(
            ref=str(data.get("ref", "")),
            kind=str(data.get("kind", "other")),
            action=str(data.get("action", "create")),
            size=int(data.get("size", 0) or 0),
            sha256=str(data.get("sha256", "")),
        )


@dataclass(slots=True)
class ExecutionResult:
    summary: str
    assets: list[AssetRecord]
    changes: list[ChangeItem]
    primary_ref: str

    def to_dict(self) -> JsonDict:
        return {
            "summary": self.summary,
            "assets": [item.to_dict() for item in self.assets],
            "changes": [item.to_dict() for item in self.changes],
            "primary_ref": self.primary_ref,
        }

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ExecutionResult":
        return cls(
            summary=str(data.get("summary", "")),
            assets=[AssetRecord.from_dict(item) for item in data.get("assets", [])],
            changes=[ChangeItem.from_dict(item) for item in data.get("changes", [])],
            primary_ref=str(data.get("primary_ref", "")),
        )


@dataclass(slots=True)
class NodeRunState:
    id: str
    status: str = "pending"
    phase: str = ""
    artifact: str | None = None
    result: ExecutionResult | None = None
    message: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "id": self.id,
            "status": self.status,
            "artifact": self.artifact,
            "message": self.message,
        }
        if self.phase:
            payload["phase"] = self.phase
        if self.result is not None:
            payload["result"] = self.result.to_dict()
        if self.started_at:
            payload["started_at"] = self.started_at
        if self.finished_at:
            payload["finished_at"] = self.finished_at
        return payload

    @classmethod
    def from_dict(cls, data: JsonDict) -> "NodeRunState":
        result_raw = data.get("result")
        result = ExecutionResult.from_dict(result_raw) if isinstance(result_raw, dict) else None
        return cls(
            id=data["id"],
            status=data.get("status", "pending"),
            phase=str(data.get("phase", "")),
            artifact=data.get("artifact"),
            result=result,
            message=data.get("message", ""),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
        )


@dataclass(slots=True)
class RunState:
    run_id: str
    workflow_id: str
    status: str
    current_node: str | None
    nodes: dict[str, NodeRunState]
    started_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "current_node": self.current_node,
            "nodes": {key: value.to_dict() for key, value in self.nodes.items()},
        }
        if self.started_at:
            payload["started_at"] = self.started_at
        if self.updated_at:
            payload["updated_at"] = self.updated_at
        return payload

    @classmethod
    def from_dict(cls, data: JsonDict) -> "RunState":
        return cls(
            run_id=data["run_id"],
            workflow_id=data["workflow_id"],
            status=data.get("status", "pending"),
            current_node=data.get("current_node"),
            nodes={
                key: NodeRunState.from_dict(value)
                for key, value in data.get("nodes", {}).items()
            },
            started_at=str(data.get("started_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )

