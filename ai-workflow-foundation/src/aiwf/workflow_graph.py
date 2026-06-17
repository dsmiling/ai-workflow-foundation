from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import NodeSpec, TransitionSpec, WorkflowSpec


SUCCESS_STATUSES = {"completed", "approved", "skipped"}
ALLOWED_WHEN = {"always", "approved", "rejected", "completed", "failed", "skipped"}


def transition_matches(when: str, status: str) -> bool:
    if when == "always":
        return status in SUCCESS_STATUSES
    return when == status


def linear_transitions(nodes: list[NodeSpec]) -> list[TransitionSpec]:
    transitions: list[TransitionSpec] = []
    for index in range(len(nodes) - 1):
        transitions.append(
            TransitionSpec(
                from_node=nodes[index].id,
                to=nodes[index + 1].id,
                when="always",
            )
        )
    return transitions


@dataclass(slots=True)
class WorkflowGraph:
    workflow: WorkflowSpec
    nodes_by_id: dict[str, NodeSpec]
    transitions: list[TransitionSpec]
    initial: str

    @classmethod
    def from_workflow(cls, workflow: WorkflowSpec) -> "WorkflowGraph":
        nodes_by_id = {node.id: node for node in workflow.nodes}
        transitions = list(workflow.transitions) if workflow.transitions else linear_transitions(workflow.nodes)
        initial = workflow.initial or (workflow.nodes[0].id if workflow.nodes else "")
        return cls(
            workflow=workflow,
            nodes_by_id=nodes_by_id,
            transitions=transitions,
            initial=initial,
        )

    def get_node(self, node_id: str) -> NodeSpec:
        node = self.nodes_by_id.get(node_id)
        if node is None:
            raise ValueError(f"Node not found in workflow: {node_id}")
        return node

    def transitions_from(self, node_id: str) -> list[TransitionSpec]:
        return [transition for transition in self.transitions if transition.from_node == node_id]

    def resolve_next(self, from_id: str, status: str) -> str | None:
        matches = [
            transition.to
            for transition in self.transitions_from(from_id)
            if transition_matches(transition.when, status)
        ]
        if not matches:
            return None
        return matches[0]

    def collect_reachable_from(self, start: str) -> set[str]:
        reachable: set[str] = set()
        queue = deque([start])
        while queue:
            node_id = queue.popleft()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            for transition in self.transitions_from(node_id):
                if transition.to not in reachable:
                    queue.append(transition.to)
        return reachable

    def ancestors(self, node_id: str) -> set[str]:
        reverse: dict[str, list[str]] = {node.id: [] for node in self.workflow.nodes}
        for transition in self.transitions:
            reverse.setdefault(transition.to, []).append(transition.from_node)
        found: set[str] = set()
        queue = deque(reverse.get(node_id, []))
        while queue:
            current = queue.popleft()
            if current in found:
                continue
            found.add(current)
            queue.extend(reverse.get(current, []))
        return found

    def execution_entry(self, node_states: dict[str, object], current_node: str | None) -> str | None:
        if current_node and current_node in self.nodes_by_id:
            node_state = node_states.get(current_node)
            status = getattr(node_state, "status", None) if node_state is not None else None
            if status in {None, "pending", "paused"}:
                return current_node

        current = self.initial
        visited: set[str] = set()
        while current:
            if current in visited:
                return current
            visited.add(current)
            node_state = node_states.get(current)
            status = getattr(node_state, "status", "pending") if node_state is not None else "pending"
            if status not in SUCCESS_STATUSES:
                return current
            next_id = self.resolve_next(current, status)
            if not next_id:
                return None
            current = next_id
        return None
