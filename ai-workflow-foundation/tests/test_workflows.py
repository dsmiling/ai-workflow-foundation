from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.storage import WorkflowStore
from aiwf.workflows import delete_workflow, get_workflow, list_workflows, save_workflow


class WorkflowCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        project = Path(__file__).resolve().parents[1]
        self.project = project
        self.workspace = project / ".test-workspace" / uuid4().hex
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.store = WorkflowStore(self.workspace, project_root=self.project)
        self.store.init()
        self.skills = [project / "examples" / "skills"]

    def test_list_and_get_workflows(self) -> None:
        workflows = list_workflows(self.store)
        ids = {item["id"] for item in workflows}
        self.assertIn("unity_activity_create", ids)

        payload = get_workflow(self.store, "unity_activity_create")
        self.assertEqual(payload["workflow"]["id"], "unity_activity_create")
        self.assertIn("examples/workflows/unity_activity_create.json", payload["path"])

    def test_save_and_delete_workspace_workflow(self) -> None:
        source = get_workflow(self.store, "simple_foundation")
        workflow = source["workflow"]
        workflow["id"] = "saved_demo"
        workflow["name"] = "Saved Demo"

        saved = save_workflow(self.store, workflow, self.skills)
        self.assertTrue(saved["editable"])
        self.assertTrue(saved["path"].endswith(".aiwf/workflows/saved_demo.json"))

        payload = get_workflow(self.store, "saved_demo")
        self.assertEqual(payload["source"], "workspace")

        delete_workflow(self.store, "saved_demo")
        with self.assertRaises(FileNotFoundError):
            delete_workflow(self.store, "saved_demo")

    def test_save_single_node_workflow(self) -> None:
        workflow = {
            "id": "single_node_demo",
            "name": "Single Node Demo",
            "initial": "only",
            "transitions": [],
            "nodes": [
                {
                    "id": "only",
                    "name": "Only Node",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {"raw_requirement": "Create a one-node workflow."},
                    "outputs": {"primary": "requirement_analysis.md"},
                    "approval": {"mode": "auto", "level": "optional"},
                }
            ],
        }
        saved = save_workflow(self.store, workflow, self.skills)
        self.assertTrue(saved["editable"])
        payload = get_workflow(self.store, "single_node_demo")
        self.assertEqual(len(payload["workflow"]["nodes"]), 1)
        self.assertEqual(payload["workflow"]["initial"], "only")

        delete_workflow(self.store, "single_node_demo")

if __name__ == "__main__":
    unittest.main()
