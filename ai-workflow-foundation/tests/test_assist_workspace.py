from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from aiwf.agent_assist_workspace import resolve_role_session
from aiwf.assist_workspace import (
    append_workflow_assist_messages,
    build_workflow_acp_user_text,
    clear_workflow_chat_id,
    clear_workflow_assist_session,
    load_workflow_assist_session,
    resolve_workflow_session,
    stream_workflow_assist_acp,
)
from aiwf.cli_acp import SessionRegistry
from aiwf.storage import WorkflowStore


class AssistWorkspaceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        SessionRegistry.reset()

    def tearDown(self) -> None:
        SessionRegistry.reset()

    def test_resolve_workflow_session_clears_chat_on_provider_switch(self) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "workflow_test_001"
        sid, folder, _ = resolve_workflow_session(
            store,
            workflow_id=wf_id,
            provider_id="cursor-agent-acp",
        )
        session_file = folder / "session.json"
        store.write_json(
            session_file,
            {
                "session_id": sid,
                "workflow_id": wf_id,
                "provider_id": "cursor-agent-acp",
                "chat_id": "chat-cursor-abc",
                "workspace": str(folder),
            },
        )
        index = store.read_json(store.aiwf / "assist" / "index.json")
        by_workflow = index["by_workflow_id"]
        assert isinstance(by_workflow, dict)
        by_workflow[wf_id] = {
            "session_id": sid,
            "chat_id": "chat-cursor-abc",
            "provider_id": "cursor-agent-acp",
        }
        store.write_json(store.aiwf / "assist" / "index.json", index)

        with patch.object(SessionRegistry, "release_scope") as release_scope:
            _, _, chat_id = resolve_workflow_session(
                store,
                workflow_id=wf_id,
                provider_id="codex-agent-acp",
            )
        self.assertIsNone(chat_id)
        release_scope.assert_called_once_with(f"workflow:{wf_id}")
        session_data = store.read_json(session_file)
        self.assertIsNone(session_data.get("chat_id"))
        self.assertEqual(session_data.get("provider_id"), "codex-agent-acp")

    def test_resolve_role_session_clears_chat_on_provider_switch(self) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        agent_id = "requirement_analyst"
        sid, folder, _ = resolve_role_session(
            store,
            agent_id=agent_id,
            provider_id="cursor-agent-acp",
        )
        session_file = folder / "session.json"
        store.write_json(
            session_file,
            {
                "session_id": sid,
                "agent_id": agent_id,
                "provider_id": "cursor-agent-acp",
                "chat_id": "chat-cursor-role",
                "workspace": str(folder),
            },
        )
        index = store.read_json(store.aiwf / "agents" / "assist" / "index.json")
        by_agent = index["by_agent_id"]
        assert isinstance(by_agent, dict)
        by_agent[agent_id] = {
            "session_id": sid,
            "chat_id": "chat-cursor-role",
            "provider_id": "cursor-agent-acp",
        }
        store.write_json(store.aiwf / "agents" / "assist" / "index.json", index)

        with patch.object(SessionRegistry, "release_scope") as release_scope:
            _, _, chat_id = resolve_role_session(
                store,
                agent_id=agent_id,
                provider_id="codex-agent-acp",
            )
        self.assertIsNone(chat_id)
        release_scope.assert_called_once_with(f"role:{agent_id}")
        session_data = store.read_json(session_file)
        self.assertIsNone(session_data.get("chat_id"))
        self.assertEqual(session_data.get("provider_id"), "codex-agent-acp")

    def test_load_and_append_workflow_assist_messages(self) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "unity_activity_create"
        sid, folder, _ = resolve_workflow_session(
            store,
            workflow_id=wf_id,
            provider_id="cursor-agent-acp",
        )
        store.write_json(
            folder / "session.json",
            {
                "session_id": sid,
                "workflow_id": wf_id,
                "provider_id": "cursor-agent-acp",
                "chat_id": "chat-001",
                "workspace": str(folder),
            },
        )
        append_workflow_assist_messages(
            store,
            workflow_id=wf_id,
            session_id=sid,
            user_text="add a node",
            assistant_text="已添加节点。",
        )
        loaded = load_workflow_assist_session(store, wf_id)
        self.assertEqual(loaded["session_id"], sid)
        self.assertEqual(loaded["chat_id"], "chat-001")
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][0]["role"], "user")
        self.assertEqual(loaded["messages"][1]["content"], "已添加节点。")

    @patch("aiwf.assist_workspace.create_cli_session_provider")
    @patch("aiwf.assist_workspace.stream_acp_message")
    def test_stream_workflow_assist_recovers_stale_chat_id(self, mock_stream, mock_provider) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "unity_activity_create"
        sid, folder, _ = resolve_workflow_session(
            store,
            workflow_id=wf_id,
            provider_id="cursor-agent-acp",
        )
        stale_chat = "71c24f30-stale-chat-id"
        persist = {
            "session_id": sid,
            "workflow_id": wf_id,
            "provider_id": "cursor-agent-acp",
            "chat_id": stale_chat,
            "workspace": str(folder),
        }
        store.write_json(folder / "session.json", persist)
        index = store.read_json(store.aiwf / "assist" / "index.json")
        by_workflow = index["by_workflow_id"]
        assert isinstance(by_workflow, dict)
        by_workflow[wf_id] = {
            "session_id": sid,
            "chat_id": stale_chat,
            "provider_id": "cursor-agent-acp",
        }
        store.write_json(store.aiwf / "assist" / "index.json", index)
        folder.joinpath("draft.json").write_text(
            '{"id":"unity_activity_create","name":"Test","nodes":[],"transitions":[]}\n',
            encoding="utf-8",
        )
        folder.joinpath("summary.md").write_text("已恢复会话。", encoding="utf-8")

        mock_client = mock_provider.return_value.acquire_session.return_value
        mock_client.create_chat.return_value = "new-chat-id-recovered"

        calls = {"count": 0}

        def side_effect(scope, text):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Internal error")
            yield {"type": "progress", "stage": "acp", "message": "ok", "percent": 50}
            yield {"type": "done", "message": "完成", "percent": 100}

        mock_stream.side_effect = side_effect
        events = list(
            stream_workflow_assist_acp(
                store,
                workflow_id=wf_id,
                provider_id="cursor-agent-acp",
                description="测试",
            )
        )
        self.assertEqual(calls["count"], 2)
        mock_client.create_chat.assert_called_once()
        done = [event for event in events if event.get("type") == "workspace_done"]
        self.assertEqual(len(done), 1)
        loaded = load_workflow_assist_session(store, wf_id)
        self.assertEqual(loaded.get("chat_id"), "new-chat-id-recovered")

    @patch("aiwf.assist_workspace.create_cli_session_provider")
    @patch("aiwf.assist_workspace.stream_acp_message")
    def test_stream_workflow_assist_recovers_new_chat_internal_error(
        self, mock_stream, mock_provider
    ) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "unity_activity_create"
        mock_client = mock_provider.return_value.acquire_session.return_value
        mock_client.create_chat.side_effect = ["chat-first-failed", "chat-second-ok"]

        calls = {"count": 0}

        def side_effect(scope, text):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Internal error (code=-32603)")
            yield {"type": "progress", "stage": "acp", "message": "ok", "percent": 50}
            yield {"type": "done", "message": "完成", "percent": 100}

        mock_stream.side_effect = side_effect
        events = list(
            stream_workflow_assist_acp(
                store,
                workflow_id=wf_id,
                provider_id="cursor-agent-acp",
                description="测试",
                draft={"id": wf_id, "name": "Test", "nodes": [], "transitions": []},
            )
        )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(mock_client.create_chat.call_count, 2)
        done = [event for event in events if event.get("type") == "workspace_done"]
        self.assertEqual(len(done), 1)
        loaded = load_workflow_assist_session(store, wf_id)
        self.assertEqual(loaded.get("chat_id"), "chat-second-ok")

    def test_build_workflow_acp_user_text_includes_focus_constraints(self) -> None:
        folder = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        focus_nodes = [{"id": "requirement_analysis", "name": "Requirement Analysis"}]
        text = build_workflow_acp_user_text(
            "@requirement_analysis 把节点显示名改成需求分析",
            folder,
            focus_nodes=focus_nodes,
            focus_detail="full",
        )
        self.assertIn("Do NOT translate or rewrite inputs", text)
        self.assertIn("requirement_analysis", text)

    def test_build_workflow_acp_user_text_compact_mode(self) -> None:
        folder = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        text = build_workflow_acp_user_text(
            "把节点显示名改成需求分析",
            folder,
            focus_hint="Focus nodes: requirement_analysis",
            focus_detail="compact",
        )
        self.assertIn("Focus nodes: requirement_analysis", text)
        self.assertNotIn("Focus nodes (edit only what", text)

    def test_build_workflow_acp_user_text_noop_mode(self) -> None:
        folder = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        text = build_workflow_acp_user_text(
            "这个工作流还缺什么？",
            folder,
            focus_hint="User is viewing node: requirement_analysis",
            focus_detail="none",
        )
        self.assertIn("Mode: conversation", text)
        self.assertIn("Reply naturally", text)
        self.assertNotIn("Focus nodes (edit only what", text)
        self.assertNotIn("Update draft.json", text)

    def test_clear_workflow_chat_id(self) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "wf_clear_chat"
        sid, folder, _ = resolve_workflow_session(
            store,
            workflow_id=wf_id,
            provider_id="cursor-agent-acp",
        )
        clear_workflow_chat_id(store, wf_id, sid)
        loaded = load_workflow_assist_session(store, wf_id)
        self.assertEqual(loaded.get("chat_id"), "")
        session_data = store.read_json(folder / "session.json")
        self.assertIsNone(session_data.get("chat_id"))

    def test_clear_workflow_assist_session(self) -> None:
        workspace = Path(__file__).resolve().parents[1] / ".test-workspace" / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=True)
        store = WorkflowStore(workspace)
        store.init()
        wf_id = "wf_clear_history"
        sid, folder, _ = resolve_workflow_session(
            store,
            workflow_id=wf_id,
            provider_id="cursor-agent-acp",
        )
        store.write_json(
            folder / "session.json",
            {
                "session_id": sid,
                "workflow_id": wf_id,
                "provider_id": "cursor-agent-acp",
                "chat_id": "chat-history-1",
                "workspace": str(folder),
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ],
                "pending_summary": "summary",
            },
        )
        (folder / "summary.md").write_text("summary", encoding="utf-8")

        cleared = clear_workflow_assist_session(store, wf_id)

        self.assertEqual(cleared["session_id"], sid)
        self.assertEqual(cleared["chat_id"], "")
        self.assertEqual(cleared["messages"], [])
        self.assertEqual(cleared["pending_summary"], "")
        loaded = load_workflow_assist_session(store, wf_id)
        self.assertEqual(loaded["messages"], [])
        self.assertEqual(loaded["pending_summary"], "")
        self.assertEqual(loaded["chat_id"], "")
        session_data = store.read_json(folder / "session.json")
        self.assertEqual(session_data.get("messages"), [])
        self.assertEqual(session_data.get("pending_summary"), "")
        self.assertIsNone(session_data.get("chat_id"))
        self.assertEqual((folder / "summary.md").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
