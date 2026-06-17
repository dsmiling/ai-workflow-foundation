from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.execution_result import (
    build_execution_result,
    primary_output_name,
    structured_output_name,
    synthesize_from_artifact,
)
from aiwf.models import NodeSpec
from aiwf.runner import WorkflowRunner
from aiwf.storage import WorkflowStore


class ExecutionResultTests(unittest.TestCase):
    def test_build_execution_result_create(self) -> None:
        node = NodeSpec(id="requirement_analysis", name="Requirement Analysis", type="ai")
        result = build_execution_result(
            node,
            "# Requirement Analysis\n\nDone.",
            "artifacts/requirement_analysis.md",
            action="create",
        )
        self.assertEqual(result.primary_ref, "artifacts/requirement_analysis.md")
        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.changes[0].action, "create")

    def test_synthesize_from_artifact(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])
        state = runner.start(workflow, until_node="requirement_analysis")
        run_dir = store.get_run_dir(state.run_id)
        node_state = state.nodes["requirement_analysis"]
        self.assertIsNotNone(node_state.result)
        self.assertTrue((run_dir / "node_results" / "requirement_analysis.json").exists())
        payload = store.read_node_result(run_dir, "requirement_analysis")
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload.summary)
        self.assertEqual(payload.primary_ref, node_state.artifact)

    def test_structured_output_name_from_node(self) -> None:
        node = NodeSpec(
            id="module_mapping",
            name="Module Mapping",
            type="ai",
            outputs={"structured": "module_mapping.json"},
        )
        self.assertEqual(structured_output_name(node, None), "module_mapping.json")

    def test_primary_output_name_default(self) -> None:
        node = NodeSpec(id="demo", name="Demo", type="ai")
        self.assertEqual(primary_output_name(node, None), "demo.md")

    def test_synthesize_legacy_only_artifact(self) -> None:
        result = synthesize_from_artifact("demo", "artifacts/demo.md")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_ref, "artifacts/demo.md")


if __name__ == "__main__":
    unittest.main()
