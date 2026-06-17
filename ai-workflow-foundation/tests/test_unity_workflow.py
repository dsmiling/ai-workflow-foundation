from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.runner import WorkflowRunner
from aiwf.storage import WorkflowStore
from aiwf.validation import validate_workflow_file


class UnityWorkflowTests(unittest.TestCase):
    def test_unity_workflow_validates_and_pauses_at_review(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "unity_activity_create.json"
        skills = [project / "examples" / "skills"]
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace, project_root=project)
        store.init()

        report = validate_workflow_file(store, workflow, skill_dirs=skills)
        self.assertTrue(report.ok, report.errors)

        runner = WorkflowRunner(store, skill_dirs=skills)
        state = runner.start(workflow)

        self.assertEqual(state.status, "paused")
        self.assertEqual(state.current_node, "review_mapping")
        self.assertEqual(state.nodes["requirement_analysis"].status, "completed")
        self.assertEqual(state.nodes["module_mapping"].status, "completed")

        run_dir = store.get_run_dir(state.run_id)
        self.assertTrue((run_dir / "artifacts" / "module_mapping.md").exists())
        self.assertTrue((run_dir / "artifacts" / "module_mapping.json").exists())
        analysis = store.read_artifact_ref(run_dir, state.nodes["requirement_analysis"].artifact)
        self.assertIn("Skill Orchestration", analysis)

    def test_artifact_edit_updates_node_message(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "unity_activity_create.json"
        skills = [project / "examples" / "skills"]
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace, project_root=project)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=skills)
        state = runner.start(workflow)
        run_dir = store.get_run_dir(state.run_id)
        artifact_ref = state.nodes["module_mapping"].artifact
        assert artifact_ref is not None

        store.write_artifact_ref(run_dir, artifact_ref, "# edited mapping\n")
        updated = store.load_state(run_dir)

        self.assertEqual(updated.nodes["module_mapping"].message, "Artifact manually edited.")


if __name__ == "__main__":
    unittest.main()
