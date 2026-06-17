from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.runner import WorkflowRunner
from aiwf.storage import WorkflowStore
from test_executor import FakeExecutor


class WorkflowRunnerTests(unittest.TestCase):
    def test_demo_workflow_pauses_and_resumes(self) -> None:
        store, state = self.completed_demo_run()

        self.assertEqual(state.status, "completed")
        self.assertEqual(state.nodes["review_plan"].status, "approved")
        self.assertEqual(state.nodes["build_plan"].status, "completed")

    def test_revision_diff_and_rollback(self) -> None:
        store, state = self.completed_demo_run()
        run_dir = store.get_run_dir(state.run_id)
        artifact = run_dir / state.nodes["build_plan"].artifact
        original = artifact.read_text(encoding="utf-8")

        first_revision = store.create_revision(run_dir, "accepted output")
        artifact.write_text(original + "\nManual edit for diff coverage.\n", encoding="utf-8")
        second_revision = store.create_revision(run_dir, "manual edit")

        diff = store.diff_revisions(run_dir, first_revision, second_revision)

        self.assertIn("Manual edit for diff coverage.", diff)
        self.assertIn("artifacts/build_plan.md", diff)

        store.rollback_revision(run_dir, first_revision)

        self.assertEqual(artifact.read_text(encoding="utf-8"), original)

    def test_rerun_from_node_resets_downstream_state(self) -> None:
        store, state = self.completed_demo_run()
        runner = WorkflowRunner(store, skill_dirs=[Path(__file__).resolve().parents[1] / "examples" / "skills"])

        rerun = runner.rerun_from(state.run_id, "module_breakdown")

        self.assertEqual(rerun.status, "paused")
        self.assertEqual(rerun.current_node, "review_plan")
        self.assertEqual(rerun.nodes["requirement_analysis"].status, "completed")
        self.assertEqual(rerun.nodes["module_breakdown"].status, "completed")
        self.assertEqual(rerun.nodes["review_plan"].status, "paused")
        self.assertNotIn("build_plan", rerun.nodes)

    def test_change_request_applies_feedback_and_reruns_node(self) -> None:
        store, state = self.completed_demo_run()
        run_dir = store.get_run_dir(state.run_id)
        runner = WorkflowRunner(store, skill_dirs=[Path(__file__).resolve().parents[1] / "examples" / "skills"])
        feedback = "Split reward planning into login, milestone, and ranking rewards."

        change_id = store.create_change_request(run_dir, "module_breakdown", feedback)
        change = store.apply_change_request(run_dir, change_id)
        rerun = runner.rerun_from(state.run_id, "module_breakdown")
        artifact = run_dir / rerun.nodes["module_breakdown"].artifact

        self.assertEqual(change["status"], "applied")
        self.assertEqual(rerun.status, "paused")
        self.assertIn(feedback, artifact.read_text(encoding="utf-8"))

    def test_runner_accepts_injected_executor(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        runner = WorkflowRunner(
            store,
            skill_dirs=[project / "examples" / "skills"],
            executor=FakeExecutor(),
        )

        state = runner.start(workflow)
        run_dir = store.get_run_dir(state.run_id)
        artifact = run_dir / state.nodes["requirement_analysis"].artifact

        self.assertIn("node=requirement_analysis", artifact.read_text(encoding="utf-8"))

    def test_start_until_node_runs_upstream_and_stops(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        state = runner.start(workflow, until_node="module_breakdown")

        self.assertEqual(state.status, "pending")
        self.assertIsNone(state.current_node)
        self.assertEqual(state.nodes["requirement_analysis"].status, "completed")
        self.assertEqual(state.nodes["module_breakdown"].status, "completed")
        self.assertNotIn("review_plan", state.nodes)

    def test_run_single_node_on_existing_run(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        started = runner.start(workflow, until_node="requirement_analysis")
        rerun = runner.run_single_node(started.run_id, "module_breakdown")

        self.assertEqual(rerun.status, "pending")
        self.assertEqual(rerun.nodes["module_breakdown"].status, "completed")
        self.assertNotIn("review_plan", rerun.nodes)

    def test_reject_transition_reruns_upstream_node(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        state = runner.start(workflow)
        self.assertEqual(state.status, "paused")
        self.assertEqual(state.current_node, "review_plan")

        run_dir = store.get_run_dir(state.run_id)
        store.write_review(run_dir, "review_plan", "reject", "Need more module detail.")
        rejected = runner.resume(state.run_id)

        self.assertEqual(rejected.status, "paused")
        self.assertEqual(rejected.current_node, "review_plan")
        self.assertEqual(rejected.nodes["requirement_analysis"].status, "completed")
        self.assertEqual(rejected.nodes["module_breakdown"].status, "completed")
        self.assertNotIn("build_plan", rejected.nodes)

    def test_unified_node_execute_and_review_pause(self) -> None:
        project = Path(__file__).resolve().parents[1]
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        workflow_path = test_workspace / ".aiwf" / "workflows" / "unified_review.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(
            """
{
  "id": "unified_review",
  "name": "Unified Review Demo",
  "initial": "analysis",
  "nodes": [
    {
      "id": "analysis",
      "name": "Analysis",
      "type": "ai",
      "skill": "requirement_analysis",
      "inputs": { "raw_requirement": "demo" },
      "outputs": { "primary": "analysis.md" },
      "approval": { "mode": "human", "level": "required" }
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        state = runner.start(workflow_path)
        self.assertEqual(state.status, "paused")
        self.assertEqual(state.current_node, "analysis")
        self.assertEqual(state.nodes["analysis"].status, "paused")
        self.assertEqual(state.nodes["analysis"].phase, "review")
        self.assertTrue(state.nodes["analysis"].artifact)

        run_dir = store.get_run_dir(state.run_id)
        store.write_review(run_dir, "analysis", "approve", "Looks good.")
        resumed = runner.resume(state.run_id)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.nodes["analysis"].status, "completed")

    def test_unified_node_reject_reruns_self_by_default(self) -> None:
        project = Path(__file__).resolve().parents[1]
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        workflow_path = test_workspace / ".aiwf" / "workflows" / "unified_reject.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(
            """
{
  "id": "unified_reject",
  "name": "Unified Reject Demo",
  "initial": "analysis",
  "nodes": [
    {
      "id": "analysis",
      "name": "Analysis",
      "type": "ai",
      "skill": "requirement_analysis",
      "inputs": { "raw_requirement": "demo" },
      "outputs": { "primary": "analysis.md" },
      "approval": { "mode": "human", "level": "required" }
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        state = runner.start(workflow_path)
        run_dir = store.get_run_dir(state.run_id)

        store.write_review(run_dir, "analysis", "reject", "Try again.")
        rejected = runner.resume(state.run_id)

        self.assertEqual(rejected.status, "paused")
        self.assertEqual(rejected.current_node, "analysis")
        self.assertEqual(rejected.nodes["analysis"].phase, "review")
        self.assertIsNone(store.load_review(run_dir, "analysis"))
        self.assertTrue((run_dir / rejected.nodes["analysis"].artifact).exists())

    def completed_demo_run(self):
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        test_workspace = project / ".test-workspace" / uuid4().hex
        test_workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(test_workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])

        state = runner.start(workflow)

        self.assertEqual(state.status, "paused")
        self.assertEqual(state.current_node, "review_plan")
        self.assertEqual(state.nodes["requirement_analysis"].status, "completed")
        self.assertTrue(state.nodes["requirement_analysis"].started_at)
        self.assertTrue(state.nodes["requirement_analysis"].finished_at)
        self.assertEqual(state.nodes["module_breakdown"].status, "completed")
        self.assertEqual(state.nodes["review_plan"].status, "paused")

        run_dir = store.get_run_dir(state.run_id)
        store.write_review(run_dir, "review_plan", "approve", "Looks good.")
        resumed = runner.resume(state.run_id)

        return store, resumed


if __name__ == "__main__":
    unittest.main()
