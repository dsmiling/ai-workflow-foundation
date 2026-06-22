from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.runner import WorkflowRunner
from aiwf.session import NodeSessionStore
from aiwf.storage import WorkflowStore


class SessionTests(unittest.TestCase):
    def test_iterate_and_commit(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])
        state = runner.start(workflow, until_node="requirement_analysis")
        run_dir = store.get_run_dir(state.run_id)

        sessions = NodeSessionStore(store)
        session = sessions.load_session(run_dir, "requirement_analysis")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.turn, 1)

        feedback = "Add protocol and configuration sections."
        state = runner.iterate_node(state.run_id, "requirement_analysis", feedback)
        node_state = state.nodes["requirement_analysis"]
        self.assertIn(feedback, store.read_artifact_ref(run_dir, node_state.artifact or ""))

        session = sessions.load_session(run_dir, "requirement_analysis")
        assert session is not None
        self.assertEqual(session.turn, 2)
        turns = sessions.list_turns(run_dir, "requirement_analysis")
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].result.changes[0].action, "create")
        self.assertEqual(turns[1].result.changes[0].action, "modify")

        aggregated = sessions.aggregate_changelist(run_dir, "requirement_analysis")
        self.assertTrue(any(item.action == "modify" for item in aggregated))

        committed = runner.commit_session(state.run_id, "requirement_analysis")
        committed_session = sessions.load_session(run_dir, "requirement_analysis")
        assert committed_session is not None
        self.assertEqual(committed_session.status, "committed")
        self.assertEqual(committed.nodes["requirement_analysis"].result.summary, committed_session and committed.nodes["requirement_analysis"].result.summary)

    def test_revert_to_turn(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workflow = project / "examples" / "workflows" / "simple_foundation.json"
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        runner = WorkflowRunner(store, skill_dirs=[project / "examples" / "skills"])
        state = runner.start(workflow, until_node="requirement_analysis")
        run_dir = store.get_run_dir(state.run_id)

        turn1_content = store.read_artifact_ref(run_dir, state.nodes["requirement_analysis"].artifact or "")
        state = runner.iterate_node(state.run_id, "requirement_analysis", "Add protocol section.")
        turn2_content = store.read_artifact_ref(run_dir, state.nodes["requirement_analysis"].artifact or "")
        self.assertNotEqual(turn1_content, turn2_content)

        state = runner.revert_session_turn(state.run_id, "requirement_analysis", 1)
        reverted = store.read_artifact_ref(run_dir, state.nodes["requirement_analysis"].artifact or "")
        self.assertEqual(reverted, turn1_content)

        sessions = NodeSessionStore(store)
        session = sessions.load_session(run_dir, "requirement_analysis")
        assert session is not None
        self.assertEqual(session.turn, 1)
        self.assertEqual(session.status, "iterating")
        self.assertEqual(len(sessions.list_turns(run_dir, "requirement_analysis")), 1)


if __name__ == "__main__":
    unittest.main()
