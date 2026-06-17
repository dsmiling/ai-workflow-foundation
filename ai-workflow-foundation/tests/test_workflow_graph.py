from pathlib import Path
import unittest

from aiwf.models import WorkflowSpec
from aiwf.storage import WorkflowStore
from aiwf.workflow_graph import WorkflowGraph, linear_transitions, transition_matches


class WorkflowGraphTests(unittest.TestCase):
    def test_linear_fallback_matches_nodes_order(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = WorkflowSpec.from_dict(
            WorkflowStore(project).read_json(project / "examples" / "workflows" / "simple_foundation.json")
        )
        graph = WorkflowGraph.from_workflow(
            WorkflowSpec(
                id=workflow.id,
                name=workflow.name,
                nodes=workflow.nodes,
                initial="",
                transitions=[],
            )
        )
        transitions = linear_transitions(workflow.nodes)
        self.assertEqual(len(transitions), len(workflow.nodes) - 1)
        self.assertEqual(graph.resolve_next("requirement_analysis", "completed"), "module_breakdown")

    def test_transition_matching(self) -> None:
        self.assertTrue(transition_matches("always", "completed"))
        self.assertTrue(transition_matches("approved", "approved"))
        self.assertFalse(transition_matches("approved", "completed"))
        self.assertTrue(transition_matches("rejected", "rejected"))

    def test_reject_transition_targets_upstream(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = WorkflowSpec.from_dict(
            WorkflowStore(project).read_json(project / "examples" / "workflows" / "simple_foundation.json")
        )
        graph = WorkflowGraph.from_workflow(workflow)
        self.assertEqual(graph.resolve_next("review_plan", "rejected"), "module_breakdown")
        reachable = graph.collect_reachable_from("module_breakdown")
        self.assertIn("review_plan", reachable)
        self.assertIn("build_plan", reachable)


if __name__ == "__main__":
    unittest.main()
