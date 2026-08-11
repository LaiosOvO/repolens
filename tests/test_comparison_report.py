from __future__ import annotations

import copy
import json
import re
import unittest

from repo_teacher.comparison_report import render_comparison_report

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # Browser verification is optional outside the development audit environment.
    sync_playwright = None  # type: ignore[assignment]


class ComparisonReportTest(unittest.TestCase):
    def fixture(self) -> dict:
        return {
            "schema_version": "2.0",
            "tool": {"catalog_revision": "2026-08-10.3"},
            "score_methodology": {
                "kind": "reviewer-rubric-signal",
                "objective_benchmark": False,
                "levels": {"0": "未实现", "25": "相邻机制", "50": "基础链路", "75": "主要链路", "100": "生产链路"},
                "scenario_profiles": {"teaching": {"title": "代码教学体验"}},
                "default_scenario": "teaching",
            },
            "projects": [
                {
                    "name": "GraphKit",
                    "path": "/tmp/graph",
                    "remote": "https://github.com/acme/graphkit.git",
                    "commit": "a" * 40,
                    "license": "MIT",
                    "report_href": "projects/graph/index.html",
                }
            ],
            "capabilities": [
                {
                    "id": "cap-1",
                    "slug": "code-graph",
                    "title": "代码图与调用关系",
                    "description": "比较静态调用图的底层实现。",
                    "option_ids": ["option-1", "option-2"],
                    "recommendation_option_ids": ["option-1"],
                    "default_scenario": "teaching",
                    "scenario_recommendations": {
                        "teaching": {
                            "preferred_class": "deterministic-code-fact-graph",
                            "primary_projects": "GraphKit",
                            "alternative_projects": "PromptGraph",
                            "confidence": "路线内首选，仍需 PoC",
                            "why": "先用确定性代码事实图，再叠加教学叙事。",
                            "tradeoff": "动态调用需补证据",
                            "module_plan": [
                                {
                                    "role": "首选路线",
                                    "project_name": "GraphKit",
                                    "source_paths": ["src/graph_builder.py"],
                                }
                            ],
                        }
                    },
                    "recommendation": "先选择同类路线，再做 PoC。",
                    "decision_factors": ["语义精度", "增量成本"],
                }
            ],
            "options": [
                {
                    "id": "option-1",
                    "project_name": "GraphKit",
                    "project_report_href": "projects/graph/index.html",
                    "remote": "https://github.com/acme/graphkit.git",
                    "commit": "a" * 40,
                    "license": "MIT",
                    "capability_slug": "code-graph",
                    "comparison_class": "deterministic-code-fact-graph",
                    "summary": "用 AST 与解析器生成符号图。",
                    "approach": "解析源码后归一化节点与边。",
                    "data_flow": ["扫描文件", "提取符号", "解析调用边", "写入图索引"],
                    "technology_tags": ["Tree-sitter", "LSP"],
                    "source_paths": ["src/graph_builder.py"],
                    "source_references": [
                        {
                            "path": "src/graph_builder.py",
                            "line_start": 12,
                            "line_end": 44,
                            "source_uri": "file:///tmp/graph/src/graph_builder.py",
                            "reference_scope": "claim-evidence",
                            "evidence_scope": "claim",
                            "supports_claim": True,
                            "claim": "该范围实现 AST 到调用图的转换。",
                            "snippet_sha256": "f" * 64,
                            "evidence_ids": ["evidence-1"],
                            "symbol_ids": ["symbol-1"],
                        }
                    ],
                    "evidence_ids": ["evidence-1"],
                    "symbol_ids": ["symbol-1"],
                    "strengths": ["跨语言", "行号精确"],
                    "limitations": ["动态调用需补证据"],
                    "architecture_reference": "复用图模型；解析适配器按语言渐进引入。",
                    "code_reuse_status": "requires-compatibility-review",
                    "dimension_scores": {
                        "semantic_precision": 100,
                        "evidence_traceability": 75,
                        "incremental_efficiency": 75,
                    },
                    "score": 88,
                    "score_uncertainty": 5,
                    "confidence": "source-audited",
                },
                {"id": "option-2", "project_name": "PromptGraph", "capability_slug": "code-graph", "score": 50},
            ],
        }

    def test_renders_summary_methodology_reuse_boundaries_and_drilldown_links(self) -> None:
        report = render_comparison_report(self.fixture())

        self.assertIn("30 SECOND BRIEF", report)
        self.assertIn('href="#capability-1"', report)
        self.assertIn("默认场景首选", report)
        self.assertIn("推荐路线", report)
        self.assertIn("建议借鉴的模块", report)
        self.assertIn("先用确定性代码事实图", report)
        self.assertIn("人工 rubric 判断（不是 benchmark）", report)
        self.assertIn("deterministic-code-fact-graph", report)
        self.assertIn('href="projects/graph/index.html"', report)
        self.assertIn('href="file:///tmp/graph/src/graph_builder.py"', report)
        self.assertIn("src/graph_builder.py:12-44", report)
        self.assertIn("EvidenceRef 1", report)
        self.assertIn("License: MIT", report)
        self.assertIn("直接代码复用：requires-compatibility-review", report)
        self.assertIn("最后怎么用这份报告", report)
        self.assertIn("证据可追溯", report)
        self.assertNotIn("自动评分", report)
        self.assertNotIn("当前推荐", report)
        self.assertNotIn('src="http', report)
        self.assertNotIn('<link rel="stylesheet"', report)

    def test_hidden_scenario_rule_overrides_grid_display_and_controls_expose_state(self) -> None:
        report = render_comparison_report(self.fixture())

        grid_rule = report.index(".scenario-recommendation{display:grid")
        hidden_rule = report.index("[data-scenario-pane][hidden]{display:none!important}")
        self.assertGreater(hidden_rule, grid_rule)
        self.assertIn('aria-pressed="true"', report)
        self.assertIn("peer.setAttribute('aria-pressed', String(active))", report)

    def test_escapes_html_and_rejects_non_file_source_links(self) -> None:
        comparison = self.fixture()
        attack = '</script><script>alert("x")</script><img src=x onerror=alert(1)>'
        comparison["capabilities"][0]["title"] = attack
        comparison["options"][0]["source_references"][0]["path"] = attack
        comparison["options"][0]["source_references"][0]["source_uri"] = "javascript:alert(1)"
        comparison["options_by_id"] = {"option-1": comparison["options"][0]}

        report = render_comparison_report(comparison)

        self.assertNotIn(attack, report)
        self.assertNotIn("<img src=x", report)
        self.assertNotIn('href="javascript:', report)
        self.assertIn("&lt;/script&gt;", report)
        match = re.search(r'<script id="comparison-data" type="application/json">(.*?)</script>', report, re.S)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))  # type: ignore[union-attr]
        self.assertEqual(payload["capabilities"][0]["title"], attack)

    def test_tolerates_missing_fields_and_orphan_option_ids(self) -> None:
        report = render_comparison_report(
            {
                "capabilities": [{"title": "空能力", "option_ids": ["missing"]}],
                "options": [{"id": "orphan", "capability_slug": "different"}],
            }
        )

        self.assertIn("空能力", report)
        self.assertIn("尚未找到与此功能绑定的实现方案", report)
        self.assertIn("暂无项目元数据", report)

    def test_legacy_single_recommendation_is_rendered_as_a_candidate_not_objective_winner(self) -> None:
        comparison = self.fixture()
        comparison["capabilities"][0].pop("recommendation_option_ids")
        comparison["capabilities"][0]["recommendation_option_id"] = "option-1"

        report = render_comparison_report(comparison)

        quick_card = re.search(r'<a class="decision-card".*?</a>', report, re.S)
        self.assertIsNotNone(quick_card)
        self.assertIn("GraphKit", quick_card.group(0))  # type: ignore[union-attr]
        self.assertIn("默认场景首选", report)

    def browser_fixture(self) -> dict:
        comparison = self.fixture()
        scenarios = {
            "precise-static-analysis": {"title": "精确静态分析"},
            "local-first-product": {"title": "本地优先产品"},
            "teaching-experience": {"title": "代码教学体验"},
            "dynamic-agent-runtime": {"title": "动态 Agent 运行时"},
        }
        comparison["score_methodology"]["scenario_profiles"] = scenarios
        comparison["score_methodology"]["default_scenario"] = "local-first-product"
        capability_template = comparison["capabilities"][0]
        option_template = comparison["options"][0]
        capabilities: list[dict] = []
        options: list[dict] = []
        for index in range(8):
            option = copy.deepcopy(option_template)
            option["id"] = f"option-{index}"
            option["project_name"] = f"Project {index}"
            options.append(option)
            capability = copy.deepcopy(capability_template)
            capability["id"] = f"capability-{index}"
            capability["slug"] = f"capability-{index}"
            capability["title"] = f"能力 {index + 1}"
            capability["option_ids"] = [option["id"]]
            capability["recommendation_option_ids"] = [option["id"]]
            capability["default_scenario"] = "local-first-product"
            capability["scenario_recommendations"] = {
                scenario: {
                    "preferred_class": f"{scenario}-route-{index}",
                    "primary_projects": option["project_name"],
                    "alternative_projects": "Alternative",
                    "confidence": "路线内首选，仍需 PoC",
                    "why": f"{scenario} 对能力 {index + 1} 的场景化理由。",
                    "tradeoff": "需验证生产边界",
                    "module_plan": [],
                }
                for scenario in scenarios
            }
            capabilities.append(capability)
        comparison["capabilities"] = capabilities
        comparison["options"] = options
        return comparison

    @unittest.skipUnless(sync_playwright is not None, "Playwright is not installed")
    def test_real_chromium_shows_exactly_one_scenario_group_at_desktop_and_mobile(self) -> None:
        report = render_comparison_report(self.browser_fixture())
        assert sync_playwright is not None
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover - only for hosts without a browser binary
                self.skipTest(f"Chromium is unavailable: {exc}")
            try:
                for width, height, max_page_height in ((1440, 900, 16000), (390, 844, 28000)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_content(report, wait_until="load")
                    self.assertEqual(page.locator("[data-scenario-pane]").count(), 36)
                    for scenario in self.browser_fixture()["score_methodology"]["scenario_profiles"]:
                        page.locator(f'[data-scenario-button="{scenario}"]').first.click()
                        visible_scenarios = page.locator("[data-scenario-pane]").evaluate_all(
                            """panes => panes
                                .filter(pane => getComputedStyle(pane).display !== 'none')
                                .map(pane => pane.dataset.scenarioPane)"""
                        )
                        self.assertEqual(visible_scenarios, [scenario] * 9)
                        active_scenarios = page.locator('[data-scenario-button][aria-pressed="true"]').evaluate_all(
                            "buttons => buttons.map(button => button.dataset.scenarioButton)"
                        )
                        self.assertEqual(active_scenarios, [scenario, scenario])
                    metrics = page.evaluate(
                        """() => ({
                            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                            height: document.documentElement.scrollHeight
                        })"""
                    )
                    self.assertLessEqual(metrics["overflow"], 1)
                    self.assertLess(metrics["height"], max_page_height)
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
