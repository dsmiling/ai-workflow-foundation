import json
import shutil
import subprocess
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
import unittest
from uuid import uuid4

from aiwf.server import create_server


class ServerTests(unittest.TestCase):
    def test_http_api_run_review_change_and_artifact(self) -> None:
        project = Path(__file__).resolve().parents[1]
        workspace = project / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        server = create_server(workspace, port=0, skill_dirs=[project / "examples" / "skills"], project_root=project)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"

            self.assertEqual(api_get(base, "/health")["status"], "ok")
            self.assertGreaterEqual(api_get(base, "/health").get("skill_api", 0), 2)
            api_get(base, "/skills/sources/wayland")
            api_get(base, "/skills/market/catalog")
            created = api_post(
                base,
                "/skills",
                {
                    "skill": {
                        "id": "server_skill_smoke",
                        "name": "Server Skill Smoke",
                        "description": "demo",
                        "goal": "Smoke test skill create.",
                        "output": {"primary": "server_skill_smoke.md"},
                        "quality": [],
                        "executor": "skill",
                    },
                    "markdown": "# Smoke\n",
                },
            )
            self.assertEqual(created["skill"]["id"], "server_skill_smoke")
            api_delete(base, "/skills/server_skill_smoke")
            html = http_get_text(base, "/")
            self.assertIn("AI Workflow Foundation", html)
            self.assertIn("Skill 助手", html)
            self.assertIn("Agent 配置", html)
            executors = api_get(base, "/executors")
            self.assertTrue(any(item["id"] == "openai-api" for item in executors["agent_providers"]))
            self.assertIn("status", executors["agent_providers"][0])
            self.assertIn("providers", executors)
            self.assertIn("role_agents", executors)
            templates = api_get(base, "/agents/templates")
            self.assertTrue(any(item["template_id"] == "requirement_analyst" for item in templates["templates"]))
            agents = api_get(base, "/agents")
            self.assertTrue(any(item["id"] == "openai-api" for item in agents["agents"]))
            created_agent = api_post(
                base,
                "/agents",
                {
                    "agent": {
                        "id": "server_agent_smoke",
                        "label": "Server Agent Smoke",
                        "provider": "openai-api",
                        "ident": {"name": "Smoke", "role": "test", "vibe": "direct"},
                        "soul": "demo",
                    }
                },
            )
            self.assertEqual(created_agent["agent"]["id"], "server_agent_smoke")
            updated_agent = api_put(
                base,
                "/agents/server_agent_smoke",
                {
                    "agent": {
                        "id": "server_agent_smoke",
                        "label": "Server Agent Updated",
                        "provider": "openai-api",
                        "ident": {"name": "Smoke", "role": "test", "vibe": "direct"},
                        "soul": "updated soul",
                    }
                },
            )
            self.assertEqual(updated_agent["agent"]["label"], "Server Agent Updated")
            self.assertEqual(updated_agent["agent"]["soul"], "updated soul")
            api_delete(base, "/agents/server_agent_smoke")
            self.assertIn('/web/js/main.js', html)
            self.assertIn("import", http_get_text(base, "/web/js/main.js"))
            self.assertIn(".page.active.settings-layout", http_get_text(base, "/web/styles/layout.css"))
            workflow_index = http_get_text(base, "/web/js/workflow/index.js")
            inspector_imports = [
                line
                for line in workflow_index.splitlines()
                if "renderWorkflowInspector" in line and line.strip().startswith("import")
            ]
            self.assertEqual(len(inspector_imports), 1)
            self.assertIn("./inspector.js", inspector_imports[0])
            self._assert_web_js_syntax(project)
            api_post(base, "/init", {})
            catalog = api_get(base, "/workflows")
            self.assertTrue(any(item["id"] == "unity_activity_create" for item in catalog["workflows"]))
            workflow = api_get(base, "/workflows/unity_activity_create")
            self.assertEqual(workflow["workflow"]["id"], "unity_activity_create")
            skills = api_get(base, "/skills")
            self.assertTrue(any(item["id"] == "module_mapping" for item in skills["skills"]))
            validation = api_post(
                base,
                "/validate",
                {"workflow": str(project / "examples" / "workflows" / "simple_foundation.json")},
            )
            self.assertTrue(validation["report"]["ok"])
            package_path = workspace / "server_export.aiwf.zip"
            package = api_post(
                base,
                "/packages/export",
                {
                    "workflow": str(project / "examples" / "workflows" / "simple_foundation.json"),
                    "package": str(package_path),
                },
            )
            self.assertEqual(package["manifest"]["workflow_id"], "simple_foundation")
            run = api_post(
                base,
                "/runs",
                {"workflow": str(project / "examples" / "workflows" / "simple_foundation.json")},
            )
            run_id = run["state"]["run_id"]
            self.assertEqual(run["state"]["status"], "paused")

            single_node = api_post(
                base,
                "/runs",
                {
                    "workflow": str(project / "examples" / "workflows" / "simple_foundation.json"),
                    "until_node": "requirement_analysis",
                },
            )
            self.assertEqual(single_node["state"]["status"], "pending")
            self.assertEqual(
                single_node["state"]["nodes"]["requirement_analysis"]["status"],
                "completed",
            )
            self.assertNotIn("module_breakdown", single_node["state"]["nodes"])

            node_run = api_post(
                base,
                f"/runs/{single_node['state']['run_id']}/nodes/module_breakdown/run",
                {"ensure_upstream": True},
            )
            self.assertEqual(node_run["state"]["nodes"]["module_breakdown"]["status"], "completed")
            self.assertNotIn("review_plan", node_run["state"]["nodes"])

            review = api_post(
                base,
                f"/runs/{run_id}/reviews",
                {
                    "node_id": "review_plan",
                    "decision": "reject",
                    "target_node": "module_breakdown",
                    "feedback": "Split rewards into login, milestone, and ranking modules.",
                },
            )
            change_id = review["change_id"]
            changes = api_get(base, f"/runs/{run_id}/changes")
            self.assertEqual(changes["changes"][0]["node_id"], "module_breakdown")

            applied = api_post(base, f"/runs/{run_id}/changes/{change_id}/apply", {"rerun": True})
            self.assertEqual(applied["state"]["status"], "paused")
            artifact_ref = applied["state"]["nodes"]["module_breakdown"]["artifact"]
            artifact = api_get(base, f"/runs/{run_id}/artifact?ref={artifact_ref}")
            self.assertIn("Split rewards", artifact["content"])

            edited = api_put(
                base,
                f"/runs/{run_id}/artifact",
                {
                    "ref": artifact_ref,
                    "content": artifact["content"] + "\nServer edit marker.\n",
                },
            )
            self.assertIn("Server edit marker.", edited["content"])
            self.assertEqual(
                edited["state"]["nodes"]["module_breakdown"]["message"],
                "Artifact manually edited.",
            )

            unity = api_post(
                base,
                "/runs",
                {"workflow": str(project / "examples" / "workflows" / "unity_activity_create.json")},
            )
            unity_run_id = unity["state"]["run_id"]
            self.assertEqual(unity["state"]["current_node"], "review_mapping")
            artifacts = api_get(base, f"/runs/{unity_run_id}/artifacts")
            self.assertIn("artifacts/module_mapping.json", artifacts["artifacts"])
        finally:
            server.shutdown()
            server.server_close()

    def _assert_web_js_syntax(self, project: Path) -> None:
        node = shutil.which("node")
        if not node:
            return
        web_js = project / "web" / "js"
        for path in web_js.rglob("*.js"):
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"{path.relative_to(project)}: {result.stderr.strip()}",
            )


def api_get(base: str, path: str):
    with urlopen(base + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_text(base: str, path: str) -> str:
    with urlopen(base + path, timeout=5) as response:
        return response.read().decode("utf-8")


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
