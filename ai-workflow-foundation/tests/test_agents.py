import json
import os
import shutil
import unittest
import unittest.mock
from pathlib import Path
from uuid import uuid4

from aiwf.agent_providers import (
    check_requirement,
    inspect_agent_provider,
    normalize_agent_provider,
    test_agent_provider,
)
from aiwf.agents import (
    build_agent_context,
    delete_agent,
    extract_json_object,
    generate_agent_draft,
    get_agent,
    list_agent_templates,
    list_agents,
    list_role_agents,
    normalize_generated_agent,
    rename_agent,
    resolve_agent_provider_id,
    save_agent,
)
from aiwf.storage import WorkflowStore


class AgentProviderTests(unittest.TestCase):
    def test_agent_provider_aliases(self) -> None:
        self.assertEqual(normalize_agent_provider("openai"), "openai-api")
        self.assertEqual(normalize_agent_provider("cursor"), "cursor-agent-acp")

    def test_check_requirement_env_or_fallback(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_aiwf_key = os.environ.pop("AIWF_OPENAI_API_KEY", None)
        try:
            ok, detail = check_requirement("OPENAI_API_KEY|AIWF_OPENAI_API_KEY")
            self.assertFalse(ok)
            self.assertEqual(detail, "OPENAI_API_KEY")
            os.environ["AIWF_OPENAI_API_KEY"] = "test-key"
            ok, detail = check_requirement("OPENAI_API_KEY|AIWF_OPENAI_API_KEY")
            self.assertTrue(ok)
            self.assertEqual(detail, "AIWF_OPENAI_API_KEY")
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if old_aiwf_key is not None:
                os.environ["AIWF_OPENAI_API_KEY"] = old_aiwf_key
            else:
                os.environ.pop("AIWF_OPENAI_API_KEY", None)

    def test_inspect_openai_provider_without_key(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_aiwf_key = os.environ.pop("AIWF_OPENAI_API_KEY", None)
        try:
            status = inspect_agent_provider("openai-api")
            self.assertEqual(status["status"], "missing")
            self.assertFalse(status["ready"])
            self.assertIn("OPENAI_API_KEY", status["missing"])
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_aiwf_key is not None:
                os.environ["AIWF_OPENAI_API_KEY"] = old_aiwf_key

    def test_build_cli_argv_resolves_executable(self) -> None:
        self.skipTest("CLI batch path removed; ACP session only.")

    @unittest.skipUnless(shutil.which("codex"), "codex CLI is not installed")
    def test_codex_provider_smoke(self) -> None:
        with unittest.mock.patch("aiwf.agent_providers.SessionRegistry") as registry_cls:
            mock_registry = registry_cls.get.return_value
            mock_client = unittest.mock.MagicMock()
            mock_client.create_chat.return_value = "chat-test"
            mock_registry.acquire.return_value = mock_client
            result = test_agent_provider("codex-agent-acp")
        self.assertEqual(result["status"], "ok", msg=result.get("message"))


class AgentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.store = WorkflowStore(self.workspace)
        self.store.init()

    def tearDown(self) -> None:
        import shutil

        if self.workspace.exists():
            shutil.rmtree(self.workspace, ignore_errors=True)

    def test_save_and_resolve_custom_agent(self) -> None:
        save_agent(
            self.store,
            {
                "id": "prod_openai",
                "label": "生产 OpenAI",
                "provider": "openai-api",
                "description": "demo soul",
            },
        )
        agents = list_agents(self.store)
        saved = next(item for item in agents if item["id"] == "prod_openai")
        self.assertEqual(saved["soul"], "demo soul")
        self.assertEqual(saved["tier"], "role")
        self.assertEqual(resolve_agent_provider_id(self.store, "prod_openai"), "openai-api")
        roles = list_role_agents(self.store)
        self.assertTrue(any(item["id"] == "prod_openai" for item in roles))
        delete_agent(self.store, "prod_openai")
        with self.assertRaises(ValueError):
            resolve_agent_provider_id(self.store, "prod_openai")

    def test_rename_custom_agent(self) -> None:
        save_agent(
            self.store,
            {
                "id": "role_old",
                "label": "旧助手",
                "provider": "openai-api",
                "soul": "demo",
            },
        )
        result = rename_agent(
            self.store,
            "role_old",
            {
                "id": "role_new",
                "label": "新助手",
                "provider": "openai-api",
                "soul": "demo updated",
            },
        )
        self.assertEqual(result["agent"]["id"], "role_new")
        self.assertEqual(result["agent"]["label"], "新助手")
        with self.assertRaises(FileNotFoundError):
            get_agent(self.store, "role_old")
        delete_agent(self.store, "role_new")

    def test_save_ident_soul_and_build_context(self) -> None:
        save_agent(
            self.store,
            {
                "id": "role_analyst",
                "label": "分析师",
                "provider": "cursor-agent-acp",
                "ident": {"name": "分析师", "role": "需求拆解", "vibe": "严谨"},
                "soul": "只做节点产物。",
            },
        )
        agent = next(item for item in list_agents(self.store) if item["id"] == "role_analyst")
        context = build_agent_context(agent)
        self.assertIn("分析师", context)
        self.assertIn("需求拆解", context)
        self.assertIn("只做节点产物。", context)
        delete_agent(self.store, "role_analyst")

    def test_list_agent_templates_from_examples(self) -> None:
        project = Path(__file__).resolve().parents[1]
        templates = list_agent_templates(project)
        self.assertTrue(any(item["template_id"] == "requirement_analyst" for item in templates))
        self.assertFalse(any(item["template_id"] == "role_template" for item in templates))

    def test_extract_json_object(self) -> None:
        payload = extract_json_object('```json\n{"id": "role_x", "label": "测试"}\n```')
        self.assertEqual(payload["id"], "role_x")

    def test_extract_json_object_nested(self) -> None:
        payload = extract_json_object(
            '说明如下\n```json\n{"summary": "ok", "workflow": {"id": "demo", "name": "Demo", "nodes": []}}\n```\n'
        )
        self.assertEqual(payload["workflow"]["id"], "demo")
        self.assertEqual(payload["summary"], "ok")

    def test_normalize_generated_agent(self) -> None:
        agent = normalize_generated_agent(
            self.store,
            {
                "label": "代码审查员",
                "ident": {"name": "审查员", "role": "审查 PR", "vibe": "直接"},
                "soul": "只做审查。",
            },
            "openai-api",
        )
        self.assertTrue(agent["id"].startswith("role_"))
        self.assertEqual(agent["label"], "代码审查员")
        self.assertEqual(agent["provider"], "openai-api")

    def test_generate_agent_draft_mocked(self) -> None:
        from unittest.mock import patch

        fake_agent = {
            "id": "role_mock",
            "label": "Mock 助手",
            "provider": "cursor-agent-acp",
            "ident": {"name": "Mock", "role": "测试", "vibe": "冷静"},
            "soul": "只做测试输出。",
        }

        def fake_stream(*args, **kwargs):
            yield {"type": "session", "session_id": "s1", "chat_id": "c1", "agent_id": "role_mock"}
            yield {"type": "done", "summary": "ok", "agent": fake_agent, "session_id": "s1", "chat_id": "c1"}

        with patch("aiwf.agents.stream_role_assist_message", side_effect=fake_stream), patch(
            "aiwf.agents.inspect_agent_provider",
            return_value={"ready": True, "detail": "ok"},
        ):
            result = generate_agent_draft(
                self.store,
                description="创建一个测试助手",
                provider_id="cursor-agent-acp",
                agent_id="role_mock",
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["agent"]["label"], "Mock 助手")


if __name__ == "__main__":
    unittest.main()
