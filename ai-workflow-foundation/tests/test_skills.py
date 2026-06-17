import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest
from uuid import uuid4

from aiwf.server import create_server


class SkillApiTests(unittest.TestCase):
    def setUp(self) -> None:
        project = Path(__file__).resolve().parents[1]
        self.project = project
        self.workspace = project / ".test-workspace" / uuid4().hex
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.server = create_server(
            self.workspace,
            port=0,
            skill_dirs=[project / "examples" / "skills"],
            project_root=project,
        )
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        api_post(self.base, "/init", {})

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_skill_crud_clone_market_and_wayland(self) -> None:
        created = api_post(
            self.base,
            "/skills",
            {
                "skill": {
                    "id": "test_skill",
                    "name": "Test Skill",
                    "description": "demo",
                    "goal": "Produce a test artifact.",
                    "output": {"primary": "test_skill.md"},
                    "quality": ["Must be readable."],
                    "executor": "skill",
                },
                "markdown": "# Test Skill\n\nRun this skill for testing.\n",
            },
        )
        self.assertEqual(created["skill"]["id"], "test_skill")
        self.assertIn("Run this skill", created["markdown"])

        updated = api_put(
            self.base,
            "/skills/test_skill",
            {
                "skill": {
                    "id": "test_skill",
                    "name": "Test Skill Updated",
                    "description": "demo",
                    "goal": "Produce an updated artifact.",
                    "output": {"primary": "test_skill.md"},
                    "quality": ["Must be readable.", "Must mention update."],
                    "executor": "skill",
                },
                "markdown": "# Test Skill\n\nUpdated body.\n",
            },
        )
        self.assertEqual(updated["skill"]["name"], "Test Skill Updated")

        catalog = api_get(self.base, "/skills")
        self.assertTrue(any(item["id"] == "test_skill" and item["source"] == "workspace" for item in catalog["skills"]))

        cloned = api_post(self.base, "/skills/module_mapping/clone", {"new_id": "module_mapping_copy"})
        self.assertEqual(cloned["skill"]["id"], "module_mapping_copy")

        example = next(item for item in catalog["skills"] if item["id"] == "module_mapping" and item["source"] == "example")
        detail = api_get(self.base, f"/skills/{example['id']}?source=example")
        self.assertEqual(detail["source"], "example")
        self.assertEqual(detail["skill"]["id"], "module_mapping")

        market = api_get(self.base, "/skills/market/catalog")
        self.assertTrue(any(item["id"] == "module_mapping" for item in market["skills"]))
        installed = api_post(self.base, "/skills/market/install", {"skill_id": "unity_build_plan"})
        self.assertEqual(installed["skill"]["id"], "unity_build_plan")

        wayland = api_get(self.base, "/skills/sources/wayland")
        if wayland["skills"]:
            entry = wayland["skills"][0]
            imported = api_post(
                self.base,
                "/skills/import/wayland",
                {"skill_id": entry["id"], "wayland_path": entry["path"]},
            )
            self.assertEqual(imported["skill"]["id"], entry["id"])
            self.assertIn("#", imported["markdown"])

        api_delete(self.base, "/skills/test_skill")
        with self.assertRaises(HTTPError):
            api_get(self.base, "/skills/test_skill")

    def test_import_skill_markdown_preview_and_save(self) -> None:
        sample = (
            "---\n"
            "name: cursor-demo\n"
            "description: Demo skill imported from markdown.\n"
            "---\n"
            "# Cursor Demo\n\n"
            "Follow these imported instructions.\n"
        )
        preview = api_post(
            self.base,
            "/skills/import/markdown/preview",
            {"markdown": sample},
        )
        self.assertEqual(preview["skill"]["id"], "cursor-demo")
        self.assertEqual(preview["skill"]["description"], "Demo skill imported from markdown.")
        self.assertIn("Cursor Demo", preview["markdown"])
        self.assertFalse(preview["conflict"])

        imported = api_post(
            self.base,
            "/skills/import/markdown",
            {"markdown": sample},
        )
        self.assertEqual(imported["skill"]["id"], "cursor-demo")
        self.assertIn("Follow these imported instructions", imported["markdown"])

        example_md = self.project / "examples" / "skills" / "module_mapping.SKILL.md"
        from_path = api_post(
            self.base,
            "/skills/import/markdown",
            {"markdown_path": str(example_md), "new_id": "module_mapping_imported"},
        )
        self.assertEqual(from_path["skill"]["id"], "module_mapping_imported")
        self.assertIn("Module Mapping", from_path["markdown"])

        api_delete(self.base, "/skills/cursor-demo")
        api_delete(self.base, "/skills/module_mapping_imported")


def api_get(base: str, path: str):
    with urlopen(base + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(base: str, path: str, payload: dict):
    return api_request(base, path, "POST", payload)


def api_put(base: str, path: str, payload: dict):
    return api_request(base, path, "PUT", payload)


def api_delete(base: str, path: str):
    return api_request(base, path, "DELETE", {})


def api_request(base: str, path: str, method: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        base + path,
        data=data if method != "DELETE" else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        if response.length == 0:
            return {}
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
