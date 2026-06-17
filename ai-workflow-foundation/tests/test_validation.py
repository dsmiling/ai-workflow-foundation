import json
from pathlib import Path
import unittest
from uuid import uuid4

from aiwf.storage import WorkflowStore
from aiwf.validation import validate_workflow_file


class ValidationTests(unittest.TestCase):
    def test_demo_workflow_validates(self) -> None:
        project = Path(__file__).resolve().parents[1]
        store = WorkflowStore(project)
        report = validate_workflow_file(
            store,
            project / "examples" / "workflows" / "simple_foundation.json",
            skill_dirs=[project / "examples" / "skills"],
        )

        self.assertTrue(report.ok, report.errors)

    def test_missing_skill_fails_validation(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        workflow_path = workspace / "broken.json"
        workflow_path.write_text(
            json.dumps(
                {
                    "id": "broken",
                    "nodes": [
                        {
                            "id": "bad_node",
                            "type": "ai",
                            "skill": "missing_skill",
                            "outputs": {"primary": "bad.md"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        store = WorkflowStore(workspace)

        report = validate_workflow_file(store, workflow_path, skill_dirs=[workspace / "skills"])

        self.assertFalse(report.ok)
        self.assertTrue(any("missing_skill" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()

