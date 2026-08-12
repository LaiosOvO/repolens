from __future__ import annotations

import unittest

from repo_teacher.agents import load_agent_spec


class AgentCatalogTest(unittest.TestCase):
    def test_business_capability_agent_binds_one_prompt_and_schema(self) -> None:
        agent = load_agent_spec("business-capability-analyst")

        self.assertEqual(agent.stage, "capability-inventory")
        self.assertEqual(agent.display_name, "业务能力目录分析员")
        self.assertEqual(agent.contract_version, "repolens-agent/v1")
        self.assertEqual(agent.prompt, "inventory-global-v1.md")
        self.assertEqual(agent.schema, "inventory")
        self.assertIn("业务能力目录", agent.instructions)
        self.assertIn("capability-inventory.json", agent.instructions)
        self.assertIn("Good Case", agent.instructions)
        self.assertIn("Bad Cases", agent.instructions)
        self.assertIn("模型输出与最终文件的区别", agent.instructions)

    def test_every_production_agent_is_a_self_contained_chinese_contract(self) -> None:
        for name in (
            "project-context-analyzer",
            "business-capability-analyst",
            "capability-reviewer",
            "capability-partition-repairer",
            "chapter-writer",
            "human-report-reviewer",
        ):
            with self.subTest(name=name):
                agent = load_agent_spec(name)
                self.assertRegex(agent.display_name, "[\\u4e00-\\u9fff]")
                self.assertIn("输入合同", agent.instructions)
                self.assertIn("Good", agent.instructions)
                self.assertIn("Bad", agent.instructions)

    def test_agent_name_cannot_escape_packaged_catalog(self) -> None:
        with self.assertRaises(ValueError):
            load_agent_spec("../secrets")


if __name__ == "__main__":
    unittest.main()
