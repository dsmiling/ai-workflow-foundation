import os
from pathlib import Path
import unittest

from aiwf.executor import OpenAICompatibleExecutor, SkillExecutor, build_executor_prompt, enrich_skill_spec, normalize_executor_name
from aiwf.agent_providers import normalize_agent_provider
from aiwf.models import NodeSpec, SkillSpec


class ExecutorTests(unittest.TestCase):
    def test_openai_executor_requires_api_key(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_aiwf_key = os.environ.pop("AIWF_OPENAI_API_KEY", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                OpenAICompatibleExecutor.from_env()
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_aiwf_key is not None:
                os.environ["AIWF_OPENAI_API_KEY"] = old_aiwf_key

    def test_normalize_executor_name_maps_openai_to_agent(self) -> None:
        self.assertEqual(normalize_executor_name("openai"), "agent")
        self.assertEqual(normalize_executor_name("mock"), "mock")

    def test_agent_provider_aliases(self) -> None:
        self.assertEqual(normalize_agent_provider("openai"), "openai-api")
        self.assertEqual(normalize_agent_provider("cursor"), "cursor-agent-acp")

    def test_prompt_contains_skill_inputs_and_feedback(self) -> None:
        node = NodeSpec.from_dict(
            {
                "id": "module_breakdown",
                "name": "Module Breakdown",
                "type": "ai",
                "params": {"last_feedback": "Split rewards."},
            }
        )
        skill = SkillSpec.from_dict(
            {
                "id": "module_breakdown",
                "goal": "Break down modules.",
                "quality": ["Every module has inputs and outputs."],
                "output": {"primary": "module_breakdown.md"},
            }
        )

        prompt = build_executor_prompt(node, skill, {"requirement": "Create an event."})

        self.assertIn("Split rewards.", prompt)
        self.assertIn("Break down modules.", prompt)
        self.assertIn("Create an event.", prompt)

    def test_prompt_includes_agent_context_before_node(self) -> None:
        node = NodeSpec.from_dict({"id": "n1", "name": "Node", "type": "ai"})
        prompt = build_executor_prompt(
            node,
            None,
            {},
            agent_context="## Agent Identity\n\n- name: 分析师",
        )
        identity_index = prompt.index("## Agent Identity")
        node_index = prompt.index("## Node")
        self.assertLess(identity_index, node_index)

    def test_skill_executor_enriches_ref_and_marks_output(self) -> None:
        project = Path(__file__).resolve().parents[1]
        skill = SkillSpec.from_dict(
            {
                "id": "module_mapping",
                "goal": "Map modules.",
                "ref": "examples/skills/module_mapping.SKILL.md",
                "executor": "skill",
            }
        )
        enriched = enrich_skill_spec(skill, project)
        self.assertIn("Skill Reference Document", enriched.description)
        node = NodeSpec.from_dict(
            {
                "id": "module_mapping",
                "name": "Module Mapping",
                "type": "ai",
                "skill": "module_mapping",
            }
        )
        executor = SkillExecutor(FakeExecutor(), project, [project / "examples" / "skills"])
        content = executor.run(node, skill, {})
        self.assertIn("Skill Orchestration", content)
        self.assertIn("module_mapping", content)


class FakeExecutor:
    def run(self, node, skill, inputs):
        return f"# fake\n\nnode={node.id}\n"


if __name__ == "__main__":
    unittest.main()

