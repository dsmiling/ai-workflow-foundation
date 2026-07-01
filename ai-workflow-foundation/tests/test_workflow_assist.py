from pathlib import Path
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from aiwf.storage import WorkflowStore
from aiwf.assist_workspace import (
    _is_recoverable_acp_error,
    persist_chat_id,
    resolve_workflow_session,
    stream_workflow_assist_acp,
)
from aiwf.workflow_assist import (
    _extract_assist_payload,
    _try_simple_workflow_edit,
    build_workflow_assist_prompt,
    compute_workflow_changes,
    extract_node_rename_intent,
    format_workflow_changes,
    has_workflow_edit_intent,
    normalize_focus_node_ids,
    normalize_generated_workflow,
    normalize_workflow_draft,
    reconcile_assist_workflow,
    resolve_assist_focus_detail,
    stream_workflow_assist,
    workflow_draft_changed,
)


class WorkflowAssistTests(unittest.TestCase):
    def setUp(self) -> None:
        project = Path(__file__).resolve().parents[1]
        self.project = project
        self.workspace = project / ".test-workspace" / uuid4().hex
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.store = WorkflowStore(self.workspace, project_root=self.project)
        self.store.init()
        self.skills = [project / "examples" / "skills"]

    def test_normalize_workflow_draft_empty(self) -> None:
        self.assertEqual(normalize_workflow_draft(None), {})
        self.assertEqual(normalize_workflow_draft("bad"), {})

    def test_normalize_focus_node_ids(self) -> None:
        self.assertEqual(normalize_focus_node_ids(["a", "a", "", "b"]), ["a", "b"])
        self.assertEqual(normalize_focus_node_ids(None), [])

    def test_build_prompt_includes_focus_nodes(self) -> None:
        draft = {
            "id": "demo",
            "nodes": [
                {
                    "id": "node_a",
                    "name": "A",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "a.md"},
                }
            ],
        }
        prompt = build_workflow_assist_prompt(
            "update inputs",
            draft=draft,
            focus_node_ids=["node_a"],
        )
        self.assertIn("node_a", prompt)
        self.assertIn("Explicitly mentioned focus nodes", prompt)

    def test_normalize_generated_workflow_single_node(self) -> None:
        raw = {
            "summary": "ok",
            "workflow": {
                "id": "assist_demo",
                "name": "Assist Demo",
                "nodes": [
                    {
                        "id": "only",
                        "name": "Only",
                        "type": "ai",
                        "skill": "requirement_analysis",
                        "inputs": {"raw_requirement": "hello"},
                        "outputs": {"primary": "only.md"},
                        "approval": {"mode": "auto", "level": "optional"},
                    }
                ],
            },
        }
        result = normalize_generated_workflow(self.store, raw, self.skills)
        workflow = result["workflow"]
        self.assertEqual(workflow["id"], "assist_demo")
        self.assertEqual(len(workflow["nodes"]), 1)
        self.assertEqual(workflow["nodes"][0]["skill"], "requirement_analysis")
        self.assertEqual(workflow["initial"], "only")

    def test_normalize_generated_workflow_refine_keeps_id(self) -> None:
        draft = {"id": "keep_me", "name": "Keep", "nodes": [{"id": "n1", "type": "ai", "skill": "requirement_analysis"}]}
        raw = {
            "workflow": {
                "id": "other",
                "name": "Other",
                "nodes": [
                    {
                        "id": "n1",
                        "name": "N1",
                        "type": "ai",
                        "skill": "requirement_analysis",
                        "inputs": {},
                        "outputs": {"primary": "n1.md"},
                    },
                    {
                        "id": "n2",
                        "name": "N2",
                        "type": "ai",
                        "skill": "module_breakdown",
                        "inputs": {"requirement": "artifact.n1"},
                        "outputs": {"primary": "n2.md"},
                    },
                ],
            }
        }
        result = normalize_generated_workflow(self.store, raw, self.skills, draft=draft, refine=True)
        self.assertEqual(result["workflow"]["id"], "keep_me")
        self.assertEqual(len(result["workflow"]["nodes"]), 2)

    def test_normalize_generated_workflow_invalid_skill_fallback(self) -> None:
        raw = {
            "workflow": {
                "id": "fallback",
                "name": "Fallback",
                "nodes": [
                    {
                        "id": "n1",
                        "type": "ai",
                        "skill": "not_a_real_skill",
                        "inputs": {},
                    }
                ],
            }
        }
        result = normalize_generated_workflow(self.store, raw, self.skills)
        skill = result["workflow"]["nodes"][0].get("skill")
        self.assertTrue(skill)
        self.assertNotEqual(skill, "not_a_real_skill")

    def test_try_simple_workflow_edit_rename(self) -> None:
        draft = {
            "id": "demo",
            "name": "Old Name",
            "nodes": [
                {
                    "id": "n1",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "n1.md"},
                }
            ],
        }
        result = _try_simple_workflow_edit("能否直接修改当前工作流名字 改成 Test001", draft)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["workflow"]["name"], "Test001")
        self.assertEqual(result["workflow"]["id"], "demo")

    def test_try_simple_workflow_edit_rename_with_spaces(self) -> None:
        draft = {
            "id": "demo",
            "name": "Old Name",
            "nodes": [
                {
                    "id": "n1",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "n1.md"},
                }
            ],
        }
        result = _try_simple_workflow_edit("把当前工作流名字改成test 001", draft)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["workflow"]["name"], "test 001")

    def test_try_simple_workflow_edit_rename_compact(self) -> None:
        draft = {
            "id": "demo",
            "name": "Old Name",
            "nodes": [
                {
                    "id": "n1",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "n1.md"},
                }
            ],
        }
        result = _try_simple_workflow_edit("把工作流名字改成Test001", draft)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["workflow"]["name"], "Test001")

    def test_extract_assist_payload_rejects_schema_example(self) -> None:
        output = """说明
```json
{
  "summary": "示例",
  "workflow": {
    "id": "workflow_id",
    "name": "显示名称",
    "nodes": [
      {
        "id": "node_id",
        "inputs": {"key": "xxx 或固定值"}
      }
    ]
  }
}
```"""
        self.assertIsNone(_extract_assist_payload(output))

    def test_workflow_draft_changed_detects_rename(self) -> None:
        draft = {
            "id": "demo",
            "name": "Old Name",
            "nodes": [
                {
                    "id": "n1",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "n1.md"},
                }
            ],
        }
        renamed = {**draft, "name": "New Name"}
        self.assertTrue(
            workflow_draft_changed(
                self.store,
                self.skills,
                baseline=draft,
                candidate=renamed,
                refine=True,
            )
        )

    def test_workflow_draft_changed_ignores_identical_snapshot(self) -> None:
        draft = {
            "id": "demo",
            "name": "Same Name",
            "nodes": [
                {
                    "id": "n1",
                    "name": "N1",
                    "type": "ai",
                    "skill": "requirement_analysis",
                    "inputs": {},
                    "outputs": {"primary": "n1.md"},
                    "approval": {"mode": "auto", "level": "optional"},
                }
            ],
        }
        self.assertFalse(
            workflow_draft_changed(
                self.store,
                self.skills,
                baseline=draft,
                candidate=json.loads(json.dumps(draft)),
                refine=True,
            )
        )

    def test_compute_workflow_changes_node_rename(self) -> None:
        baseline = {
            "id": "demo",
            "name": "Demo",
            "nodes": [
                {
                    "id": "requirement_analysis",
                    "name": "Requirement Analysis",
                    "type": "ai",
                    "skill": "unity_requirement_analysis",
                    "inputs": {"raw_requirement": "hello"},
                    "outputs": {"primary": "requirement_analysis.md"},
                }
            ],
        }
        candidate = json.loads(json.dumps(baseline))
        candidate["nodes"][0]["name"] = "需求分析"
        changes = compute_workflow_changes(baseline, candidate)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["kind"], "node_field")
        self.assertEqual(changes[0]["node_id"], "requirement_analysis")
        self.assertEqual(changes[0]["path"], "name")
        text = format_workflow_changes(changes)
        self.assertIn("requirement_analysis/name", text)
        self.assertIn("Requirement Analysis", text)
        self.assertIn("需求分析", text)

    def _unity_activity_draft(self) -> dict:
        path = self.project / "examples" / "workflows" / "unity_activity_create.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_extract_node_rename_intent_from_mention(self) -> None:
        intent = extract_node_rename_intent(
            "@requirement_analysis 把节点显示名改成需求分析",
            ["requirement_analysis"],
        )
        self.assertEqual(intent, ("requirement_analysis", "需求分析"))

    def test_try_simple_node_rename_skips_acp(self) -> None:
        draft = self._unity_activity_draft()
        result = _try_simple_workflow_edit(
            "@requirement_analysis 把节点显示名改成需求分析",
            draft,
            focus_ids=["requirement_analysis"],
        )
        self.assertIsNotNone(result)
        assert result is not None
        node = next(item for item in result["workflow"]["nodes"] if item["id"] == "requirement_analysis")
        self.assertEqual(node["name"], "需求分析")
        self.assertEqual(
            node["inputs"]["raw_requirement"],
            draft["nodes"][0]["inputs"]["raw_requirement"],
        )

    def test_reconcile_assist_workflow_drops_unrequested_input_change(self) -> None:
        baseline = self._unity_activity_draft()
        candidate = json.loads(json.dumps(baseline, ensure_ascii=False))
        req = next(node for node in candidate["nodes"] if node["id"] == "requirement_analysis")
        req["name"] = "需求分析"
        req["inputs"]["raw_requirement"] = "创建一个季节性 Unity 大型活动"
        merged = reconcile_assist_workflow(
            baseline,
            candidate,
            focus_node_ids=["requirement_analysis"],
            rename_only_node_id="requirement_analysis",
        )
        node = next(item for item in merged["nodes"] if item["id"] == "requirement_analysis")
        self.assertEqual(node["name"], "需求分析")
        self.assertEqual(
            node["inputs"]["raw_requirement"],
            baseline["nodes"][0]["inputs"]["raw_requirement"],
        )
        changes = compute_workflow_changes(baseline, merged)
        paths = [f"{item.get('node_id')}/{item.get('path')}" for item in changes if item.get("kind") == "node_field"]
        self.assertEqual(paths, ["requirement_analysis/name"])

    @patch("aiwf.workflow_assist.inspect_agent_provider", return_value={"ready": True, "detail": ""})
    @patch("aiwf.workflow_assist.stream_workflow_assist_acp")
    def test_assist_conversation_acp_overedit_is_reconciled(self, mock_acp, _mock_inspect) -> None:
        baseline = self._unity_activity_draft()
        mutated = json.loads(json.dumps(baseline, ensure_ascii=False))
        req = next(node for node in mutated["nodes"] if node["id"] == "requirement_analysis")
        req["name"] = "需求分析"
        req["inputs"]["raw_requirement"] = "创建一个季节性 Unity 大型活动"

        def fake_acp(*_args, **_kwargs):
            yield {"type": "session", "session_id": "assist_test", "chat_id": "chat_test", "workflow_id": "unity_activity_create"}
            yield {"type": "workspace_done", "summary": "", "workflow": mutated, "session_id": "assist_test", "chat_id": "chat_test"}

        mock_acp.side_effect = fake_acp
        user_message = "将节点显示名由「Requirement Analysis」改为「需求分析」"
        events = list(
            stream_workflow_assist(
                self.store,
                self.skills,
                description=user_message,
                draft=baseline,
                workflow_id="unity_activity_create",
                focus_node_ids=["requirement_analysis"],
                selected_node_id="requirement_analysis",
            )
        )
        done = next(event for event in events if event.get("type") == "done")
        self.assertTrue(done.get("changed"))
        changes = done.get("changes")
        assert isinstance(changes, list)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].get("path"), "name")
        workflow = done.get("workflow")
        assert isinstance(workflow, dict)
        node = next(item for item in workflow["nodes"] if item["id"] == "requirement_analysis")
        self.assertEqual(node["name"], "需求分析")
        self.assertEqual(
            node["inputs"]["raw_requirement"],
            baseline["nodes"][0]["inputs"]["raw_requirement"],
        )
        self.assertEqual(done.get("message"), "△ nodes/requirement_analysis/name: Requirement Analysis → 需求分析")

    def test_assist_conversation_local_rename_end_to_end(self) -> None:
        baseline = self._unity_activity_draft()
        user_message = "@requirement_analysis 把节点显示名改成需求分析"
        events = list(
            stream_workflow_assist(
                self.store,
                self.skills,
                description=user_message,
                draft=baseline,
                workflow_id="unity_activity_create",
                focus_node_ids=["requirement_analysis"],
            )
        )
        stages = [event.get("stage") for event in events if event.get("type") == "progress"]
        self.assertIn("local", stages)
        done = next(event for event in events if event.get("type") == "done")
        self.assertEqual(done.get("message"), "△ nodes/requirement_analysis/name: Requirement Analysis → 需求分析")
        workflow = done.get("workflow")
        assert isinstance(workflow, dict)
        node = next(item for item in workflow["nodes"] if item["id"] == "requirement_analysis")
        self.assertEqual(node["name"], "需求分析")

    def test_has_workflow_edit_intent(self) -> None:
        self.assertTrue(has_workflow_edit_intent("把工作流名字改成 Demo"))
        self.assertFalse(has_workflow_edit_intent("123"))
        self.assertFalse(has_workflow_edit_intent("这个活动的核心玩法是什么？"))

    def test_resolve_assist_focus_detail(self) -> None:
        self.assertEqual(resolve_assist_focus_detail("123", focus_ids=["n1"]), "none")
        self.assertEqual(
            resolve_assist_focus_detail(
                "@requirement_analysis 改显示名",
                focus_ids=["requirement_analysis"],
            ),
            "full",
        )
        self.assertEqual(
            resolve_assist_focus_detail(
                "把节点显示名改成需求分析",
                focus_ids=["requirement_analysis"],
            ),
            "compact",
        )
        self.assertEqual(
            resolve_assist_focus_detail(
                "帮我分析一下这个工作流还缺什么节点",
                focus_ids=["requirement_analysis"],
            ),
            "none",
        )

    def test_build_assist_done_event_uses_reply_when_unchanged(self) -> None:
        from aiwf.workflow_assist import _build_assist_done_event

        baseline = {"id": "demo", "name": "Demo", "nodes": [], "transitions": []}
        done = _build_assist_done_event(
            self.store,
            self.skills,
            summary="内部 summary",
            baseline=baseline,
            workflow=baseline,
            refine=True,
            reply="可以先从登录奖励和里程碑奖励两条线梳理需求。",
        )
        self.assertFalse(done.get("changed"))
        self.assertEqual(done.get("message"), "可以先从登录奖励和里程碑奖励两条线梳理需求。")

    def test_build_assist_done_event_fallback_when_no_reply(self) -> None:
        from aiwf.workflow_assist import NO_WORKFLOW_CHANGE_FALLBACK, _build_assist_done_event

        baseline = {"id": "demo", "name": "Demo", "nodes": [], "transitions": []}
        done = _build_assist_done_event(
            self.store,
            self.skills,
            summary="",
            baseline=baseline,
            workflow=baseline,
            refine=True,
            reply="",
        )
        self.assertEqual(done.get("message"), NO_WORKFLOW_CHANGE_FALLBACK)

    def test_build_assist_done_event_shows_diff_when_changed(self) -> None:
        from aiwf.workflow_assist import _build_assist_done_event

        baseline = {
            "id": "demo",
            "name": "Demo",
            "nodes": [{"id": "n1", "name": "A", "type": "ai", "skill": "build_plan", "inputs": {}, "outputs": {"primary": "n1.md"}, "approval": {"mode": "auto", "level": "optional"}}],
            "transitions": [],
        }
        candidate = json.loads(json.dumps(baseline))
        candidate["nodes"][0]["name"] = "B"
        done = _build_assist_done_event(
            self.store,
            self.skills,
            summary="",
            baseline=baseline,
            workflow=candidate,
            refine=True,
            reply="已改好名称",
        )
        self.assertTrue(done.get("changed"))
        self.assertIn("△ nodes/n1/name", str(done.get("message")))

    def test_recoverable_acp_error_accepts_formatted_internal_error(self) -> None:
        self.assertTrue(_is_recoverable_acp_error(RuntimeError("Internal error (code=-32000)")))

    @patch("aiwf.assist_workspace.create_cli_session_provider")
    @patch("aiwf.assist_workspace.stream_acp_message")
    def test_workflow_assist_acp_retries_formatted_internal_error(self, mock_stream, mock_provider) -> None:
        draft = self._unity_activity_draft()
        sid, _folder, _chat_id = resolve_workflow_session(
            self.store,
            workflow_id="unity_activity_create",
            provider_id="cursor-agent-acp",
        )
        persist_chat_id(self.store, "unity_activity_create", sid, "chat_old")
        client = mock_provider.return_value.acquire_session.return_value
        client.create_chat.return_value = "chat_new"

        def fake_stream(scope, _user_text):
            if scope.chat_id == "chat_old":
                raise RuntimeError("Internal error (code=-32000)")
            yield {"type": "done"}

        mock_stream.side_effect = fake_stream
        events = list(
            stream_workflow_assist_acp(
                self.store,
                workflow_id="unity_activity_create",
                provider_id="cursor-agent-acp",
                description="测试",
                draft=draft,
                session_id=sid,
                focus_detail="none",
            )
        )
        self.assertTrue(any(event.get("type") == "workspace_done" for event in events))
        sessions = [event for event in events if event.get("type") == "session"]
        self.assertEqual(sessions[-1].get("chat_id"), "chat_new")


if __name__ == "__main__":
    unittest.main()
