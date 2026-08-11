from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from repo_teacher.indexer import build_index
from repo_teacher.module_locator import locate_modules
from repo_teacher.module_report import render_module_report


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


class ModuleReportTest(unittest.TestCase):
    def test_report_separates_name_match_trace_reading_and_test_association(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "src" / "acp"
            target.mkdir(parents=True)
            (target / "router.py").write_text(
                "def handle_request(payload):\n    return payload\n", encoding="utf-8"
            )
            (target / "tests").mkdir()
            (target / "tests" / "test_router.py").write_text(
                "from src.acp.router import handle_request\n", encoding="utf-8"
            )
            index = build_index(root)
            result = locate_modules(index, "ACP")

            page = render_module_report(index, result)

            self.assertIn("<!doctype html>", page)
            self.assertIn("唯一产品目录名称精确命中（功能未验证）", page)
            self.assertNotIn("已定位到唯一模块", page)
            self.assertNotIn("已定位到唯一模块", page)
            self.assertIn("不表示功能已确定", page)
            self.assertIn('href="#module-001"', page)
            self.assertIn('id="module-001"', page)
            self.assertIn('id="module-search"', page)
            self.assertIn("Implementation slices", page)
            self.assertIn("基于已解析边的组件边界", page)
            self.assertIn("已解析实现链", page)
            self.assertIn("启发式阅读顺序", page)
            self.assertIn("未解析引用（诊断）", page)
            self.assertIn("测试关联，不等于测试覆盖", page)
            self.assertIn("resolved-relationship", page)
            self.assertIn("resolved-static-link", page)
            self.assertIn("src/acp/router.py:1-2", page)
            self.assertIn("片段 SHA-256", page)
            self.assertIn((target / "router.py").resolve().as_uri(), page)
            self.assertIn("链接只打开源文件", page)
            self.assertIn("@media(max-width:580px)", page)

    def test_report_rejects_non_local_or_out_of_root_file_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = {
                "query": '<script>alert("x")</script>',
                "project": {"name": "repo", "path": str(root)},
                "resolution": {"status": "candidate", "summary": "<b>guess</b>"},
                "modules": [
                    {
                        "name": '<svg onload="alert(1)">',
                        "path": "src/acp.py",
                        "surface_kind": "composite",
                        "certainty": "candidate",
                        "confidence": 0.5,
                        "confidence_label": "medium",
                        "reasons": ["<script>bad()</script>"],
                        "slices": [
                            {"path": "src/acp.py", "kind": "file", "source_uri": "file://remote-host/etc/passwd"},
                            {"path": "outside", "kind": "file", "source_uri": Path("/etc/passwd").as_uri()},
                        ],
                        "files": [],
                        "core_symbols": [],
                        "relationships": {},
                        "tests": [],
                        "possible_tests": [],
                        "implementation_trace": [],
                        "reading_order": [],
                    }
                ],
            }

            page = render_module_report({"stats": {"files": 1, "symbols": 1}}, result)

            self.assertNotIn('<script>alert("x")</script>', page)
            self.assertNotIn("<svg onload=", page)
            self.assertNotIn('href="file://remote-host', page)
            self.assertNotIn('href="file:///etc/passwd', page)
            self.assertIn("&lt;script&gt;alert", page)
            self.assertIn("&lt;svg onload=", page)


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE and CHROME.is_file(),
    "Playwright and a local Chromium browser are required for viewport assertions",
)
class ModuleReportBrowserTest(unittest.TestCase):
    def test_long_trace_and_source_excerpt_stay_inside_mobile_and_desktop_viewports(self) -> None:
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = (
                "src/very-long-component-name/very-long-orchestration-boundary/"
                "implementation_with_a_deliberately_long_name.py"
            )
            source = root / relative
            source.parent.mkdir(parents=True)
            snippet = "result = " + "very_long_unbroken_call_chain." * 24 + "execute()"
            source.write_text(snippet + "\n", encoding="utf-8")
            location = {
                "path": relative,
                "line_start": 17,
                "line_end": 17,
                "source_uri": source.resolve().as_uri(),
                "snippet": snippet,
                "snippet_sha256": "a" * 64,
                "file_sha256": "b" * 64,
                "fresh": True,
            }
            file_record = {
                "path": relative,
                "source_uri": source.resolve().as_uri(),
                "source_location": location,
                "role": "orchestration",
                "surface_role": "orchestration",
                "role_reason": "long-path mobile layout oracle",
                "role_confidence": "heuristic",
                "language": "Python",
                "lines": 17,
                "symbol_count": 1,
            }
            endpoint = {
                "path": relative,
                "line_start": 17,
                "line_end": 17,
                "source_uri": source.resolve().as_uri(),
                "snippet": snippet,
                "snippet_sha256": "a" * 64,
                "file_sha256": "b" * 64,
                "fresh": True,
            }
            result = {
                "query": "long-mobile-capability",
                "project": {"name": "mobile-layout-oracle", "path": str(root)},
                "resolution": {
                    "status": "candidate",
                    "summary": "A source-supported candidate with deliberately long trace content.",
                },
                "modules": [
                    {
                        "name": "long-mobile-capability",
                        "path": relative,
                        "surface_kind": "composite",
                        "certainty": "source-slice-candidate",
                        "confidence": 0.75,
                        "confidence_label": "medium",
                        "reasons": ["long trace and excerpt viewport regression oracle"],
                        "slices": [
                            {
                                "path": relative,
                                "kind": "file",
                                "role": "orchestration",
                                "evidence": "test-oracle",
                                "source_uri": source.resolve().as_uri(),
                            }
                        ],
                        "file_count": 1,
                        "symbol_count": 1,
                        "languages": {"Python": 1},
                        "entrypoints": [file_record],
                        "files": [file_record],
                        "core_symbols": [
                            {
                                "name": (
                                    "VeryLongOrchestrationBoundaryWithAnUnbrokenGeneratedName"
                                    "ThatMustWrapInsideTheSymbolRow.execute"
                                ),
                                "kind": "function",
                                "source_uri": source.resolve().as_uri(),
                                "source_location": location,
                                "relationship_count": 1,
                                "signature": snippet,
                            }
                        ],
                        "implementation_trace": [
                            {
                                "order": 1,
                                "ordering": "resolved-graph-topology",
                                "topology_layer": 0,
                                "confidence": "heuristic",
                                "relationship_kind": "calls",
                                "source": endpoint,
                                "target": endpoint,
                            }
                        ],
                        "component_boundaries": [
                            {
                                "confidence": "resolved-edge-component",
                                "file_count": 1,
                                "edge_count": 1,
                                "files": [file_record],
                            }
                        ],
                        "reading_order": [
                            {
                                "role": "orchestration",
                                "title": "Orchestration candidate",
                                "explanation": "Heuristic reading order only.",
                                "files": [file_record],
                            }
                        ],
                        "relationship_quality": {
                            "resolved": 1,
                            "unresolved": 0,
                            "resolved_ratio": 1.0,
                        },
                        "relationship_counts": {
                            "resolved_internal": 1,
                            "resolved_inbound": 0,
                            "resolved_outbound": 0,
                            "unresolved": 0,
                        },
                        "relationships": {
                            "resolved_internal": [
                                {
                                    "resolved": True,
                                    "kind": "calls",
                                    "confidence": "heuristic",
                                    "source": endpoint,
                                    "target": endpoint,
                                }
                            ]
                        },
                        "tests": [],
                        "possible_tests": [],
                    }
                ],
            }
            report = root / "module-report.html"
            report.write_text(
                render_module_report({"stats": {"files": 1, "symbols": 1}}, result),
                encoding="utf-8",
            )

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(CHROME),
                    headless=True,
                )
                for viewport in (
                    {"width": 390, "height": 844},
                    {"width": 1440, "height": 900},
                ):
                    with self.subTest(viewport=viewport["width"]):
                        page = browser.new_page(viewport=viewport)
                        page.goto(report.as_uri(), wait_until="load")
                        dimensions = page.evaluate(
                            """() => ({
                              viewport: document.documentElement.clientWidth,
                              page: document.documentElement.scrollWidth,
                              body: document.body.scrollWidth,
                              details: document.querySelectorAll('.module-detail').length,
                              links: document.querySelectorAll('a.step-file[href^="file:"]').length,
                              lineLabels: [...document.querySelectorAll('a.step-file')]
                                .filter((node) => node.textContent.includes(':17')).length,
                              scrollableCode: [...document.querySelectorAll('.source-excerpt pre')]
                                .some((node) => {
                                  const style = getComputedStyle(node);
                                  return ['auto', 'scroll'].includes(style.overflowX)
                                    && node.scrollWidth > node.clientWidth;
                                })
                            })"""
                        )
                        self.assertEqual(dimensions["viewport"], viewport["width"])
                        self.assertEqual(dimensions["page"], viewport["width"])
                        self.assertEqual(dimensions["body"], viewport["width"])
                        self.assertEqual(dimensions["details"], 1)
                        self.assertGreater(dimensions["links"], 0)
                        self.assertGreater(dimensions["lineLabels"], 0)
                        self.assertTrue(dimensions["scrollableCode"])
                        page.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
