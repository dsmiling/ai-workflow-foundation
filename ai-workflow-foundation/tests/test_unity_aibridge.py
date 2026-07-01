import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiwf.unity_aibridge import (
    UnityContextRequest,
    collect_unity_context,
    inspect_aibridge,
    maybe_collect_unity_context,
    parse_unity_context_request,
    resolve_aibridge_cli,
    resolve_unity_project_root,
    unity_context_task_section,
)


class UnityAibridgeTests(unittest.TestCase):
    def test_parse_unity_context_request_from_node_params(self) -> None:
        request = parse_unity_context_request(
            {
                "unity_context": {
                    "prefab_paths": ["Assets/Prefabs/Foo.prefab"],
                    "scene_hierarchy_depth": 5,
                }
            }
        )
        self.assertIsNotNone(request)
        assert request is not None
        self.assertTrue(request.active_scene)
        self.assertEqual(request.scene_hierarchy_depth, 5)
        self.assertEqual(request.prefab_paths, ["Assets/Prefabs/Foo.prefab"])

    def test_parse_disabled_unity_context(self) -> None:
        self.assertIsNone(parse_unity_context_request({"unity_context": {"enabled": False}}))

    def test_resolve_unity_project_root_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"AIWF_UNITY_PROJECT_ROOT": str(Path.cwd())}, clear=False):
            root = resolve_unity_project_root()
        self.assertEqual(root, Path.cwd().resolve())

    def test_inspect_aibridge_unconfigured(self) -> None:
        old = os.environ.pop("AIWF_UNITY_PROJECT_ROOT", None)
        try:
            result = inspect_aibridge()
            self.assertFalse(result["ready"])
        finally:
            if old is not None:
                os.environ["AIWF_UNITY_PROJECT_ROOT"] = old

    def test_collect_unity_context_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            project_root = run_dir / "unity_project"
            cli = project_root / ".aibridge" / "cli" / "AIBridgeCLI.exe"
            cli.parent.mkdir(parents=True, exist_ok=True)
            cli.write_text("", encoding="utf-8")

            def fake_run(args, **kwargs):  # noqa: ARG001
                command = args[0][1:3]
                payload = {"ok": True, "command": command}
                return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

            request = UnityContextRequest(prefab_paths=["Assets/Prefabs/Foo.prefab"])
            with mock.patch("aiwf.unity_aibridge.subprocess.run", side_effect=fake_run):
                out_dir, written, errors = collect_unity_context(
                    run_dir,
                    request,
                    project_root=project_root,
                    cli_path=cli,
                )
            self.assertEqual(errors, [])
            self.assertTrue((out_dir / "manifest.json").exists())
            self.assertTrue(any(path.endswith("manifest.json") for path in written))
            manifest = json.loads((run_dir / "unity_context" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest["project_root"]).resolve(), project_root.resolve())

    def test_maybe_collect_skips_when_not_configured(self) -> None:
        old = os.environ.pop("AIWF_UNITY_PROJECT_ROOT", None)
        try:
            written, errors = maybe_collect_unity_context(Path("run_missing"), None)
            self.assertEqual(written, [])
            self.assertEqual(errors, [])
        finally:
            if old is not None:
                os.environ["AIWF_UNITY_PROJECT_ROOT"] = old

    def test_unity_context_task_section_lists_files(self) -> None:
        lines = unity_context_task_section(["unity_context/scene_hierarchy.json"], [])
        text = "\n".join(lines)
        self.assertIn("scene_hierarchy.json", text)
        self.assertIn("Unity Context", text)


if __name__ == "__main__":
    unittest.main()
