from pathlib import Path
import unittest
from uuid import uuid4
import zipfile

from aiwf.packages import export_workflow_package, import_workflow_package
from aiwf.storage import WorkflowStore
from aiwf.validation import validate_workflow_file


class PackageTests(unittest.TestCase):
    def test_export_and_import_workflow_package(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workspace = project / ".test-workspace" / uuid4().hex
        package_path = workspace / "simple_foundation.aiwf.zip"
        workspace.mkdir(parents=True, exist_ok=True)
        source_store = WorkflowStore(project)

        manifest = export_workflow_package(
            source_store,
            project / "examples" / "workflows" / "simple_foundation.json",
            package_path,
            skill_dirs=[project / "examples" / "skills"],
        )

        self.assertEqual(manifest["workflow_id"], "simple_foundation")
        with zipfile.ZipFile(package_path, "r") as archive:
            names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("workflows/simple_foundation.json", names)
        self.assertIn("skills/module_breakdown.json", names)

        target = workspace / "target"
        target_store = WorkflowStore(target)
        result = import_workflow_package(target_store, package_path)
        workflow_path = target / result["workflow"]
        report = validate_workflow_file(
            target_store,
            workflow_path,
            skill_dirs=[target_store.aiwf / "skills"],
        )

        self.assertTrue(report.ok, report.errors)


if __name__ == "__main__":
    unittest.main()

