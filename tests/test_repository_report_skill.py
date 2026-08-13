from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "repository-report"


def read(relative: str) -> str:
    return (SKILL_DIR / relative).read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


class RepositoryReportSkillContractTests(unittest.TestCase):
    def test_business_entries_are_mechanical_and_exact_once(self) -> None:
        coverage = read("references/coverage.md")
        discovery = between(
            coverage,
            "### 1. 按平台机械枚举入口",
            "### 2. `business_entry` 必填字段",
        )

        for required_family in (
            "Web / Desktop / Mobile 导航",
            "页面交互",
            "本地与桌面能力",
            "CLI 与开发者入口",
            "HTTP / RPC / WebSocket",
            "自动与外部入口",
        ):
            self.assertIn(required_family, discovery)

        for registration_fact in (
            "route table",
            "menu config",
            "tab registry",
            "command palette",
            "IPC/Tauri command",
            "queue consumer",
        ):
            self.assertIn(registration_fact, discovery)

        gates = between(coverage, "## 双向闭包与发布门", "## 配置、协作与外部集成")
        self.assertIn("每个 entry_id 恰好一个处置", gates)
        self.assertIn("unresolved = 0", gates)
        self.assertIn(
            "entry_id → surface_id → capability_id/处置",
            gates,
        )

    def test_system_ledger_has_all_eighteen_cross_repository_axes(self) -> None:
        coverage = read("references/coverage.md")
        axes = between(
            coverage,
            "### 1. 固定审计轴，不固定项目功能",
            "### 2. 机械发现系统入口",
        )
        numbers = [
            int(match.group(1))
            for match in re.finditer(r"(?m)^(\d+)\. ", axes)
        ]
        self.assertEqual(numbers, list(range(1, 19)))

        for responsibility in (
            "身份、登录、会话",
            "数据库、Schema、迁移、事务",
            "并发、锁、租约、幂等",
            "AI、模型、Agent、工具、Skill、插件与沙箱",
            "安全隔离、网络出口、隐私",
            "日志、指标、Trace、健康",
            "构建、打包、升级、发布、部署",
        ):
            self.assertIn(responsibility, axes)

        self.assertIn("`not-applicable`", axes)
        self.assertIn("固定轴只强制提问", axes)

    def test_catalog_cannot_replace_coverage_and_outputs_share_one_source(self) -> None:
        skill = read("SKILL.md")
        pipeline = read("references/pipeline.md")
        knowledge = read("references/knowledge.md")

        for artifact in (
            "02-business-entries.md",
            "02-system-capabilities.md",
            "02-report-catalog.md",
            "report.md",
            "index.html",
            "knowledge/index.md",
        ):
            self.assertIn(artifact, skill)

        self.assertIn("不能重新决定功能", pipeline)
        self.assertIn("所有未重点展开项仍必须进入覆盖附录", pipeline)
        self.assertIn("report.md 正文 = stages/05-report.md 正文", knowledge)
        self.assertIn("知识目录由业务入口台账、系统能力台账和证据闭包决定", knowledge)

        self.assertIn("源码快照或引用 ID 不匹配时拒绝复用", skill)
        self.assertIn("用户可调整标题、顺序、分组和要重点展开的项", pipeline)
        self.assertIn("所有未重点展开项仍必须进入覆盖附录", pipeline)

    def test_knowledge_pack_preserves_safe_starting_documents_and_qa_links(self) -> None:
        knowledge = read("references/knowledge.md")

        for source_role in (
            "README*",
            "architecture",
            "getting-started",
            "菜单、路由、命令和协议的声明性注册文件",
        ):
            self.assertIn(source_role, knowledge)

        for unsafe_kind in (
            ".env",
            "token",
            "credential",
            "私钥",
            "数据库",
        ):
            self.assertIn(unsafe_kind, knowledge)

        for knowledge_type in (
            "business-entry",
            "product-surface",
            "business-capability",
            "system-capability",
            "evidence-pack",
        ):
            self.assertIn(f"`{knowledge_type}`", knowledge)

        self.assertIn("当前章节 knowledge ID", knowledge)
        self.assertIn("引用 knowledge IDs", knowledge)


if __name__ == "__main__":
    unittest.main()
