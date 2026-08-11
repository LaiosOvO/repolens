from __future__ import annotations

from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_single_report.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("repo_teacher_single_report", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("single report builder could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")


class SingleReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.html = cls.builder.build_html()
        cls.parser = _ReportParser()
        cls.parser.feed(cls.html)

    def test_one_page_contains_six_references_and_waku_boundary(self) -> None:
        self.assertEqual(self.html.count('data-project="'), 6)
        self.assertEqual(self.html.count('data-capability="'), 48)
        self.assertEqual(self.html.count('id="capability-'), 48)
        self.assertIn("30 SECOND MAP", self.html)
        self.assertIn("Waku 不参加六仓技术排名", self.html)
        self.assertIn("只看重点", self.html)
        self.assertIn("Waku 唯一验收仓", self.html)

    def test_decisions_link_to_primary_secondary_modules_and_boundaries(self) -> None:
        self.assertIn("主参考", self.html)
        self.assertIn("辅助参考", self.html)
        self.assertIn("复用模块", self.html)
        self.assertIn("不采用", self.html)
        self.assertIn('href="#capability-', self.html)
        for capability in self.builder.CAPABILITY_LABELS:
            self.assertIn(f'--{capability}"', self.html)

    def test_claim_proof_is_separate_from_reading_context(self) -> None:
        self.assertIn("行级审计证据", self.html)
        self.assertIn("相关模块 / 继续阅读", self.html)
        self.assertIn("range sha256", self.html)
        self.assertIn("audited HEAD", self.html)
        self.assertEqual(self.html.count('class="claim-proof"'), 15)
        self.assertEqual(self.html.count('class="identity verified"'), 6)
        self.assertNotIn("每个判断回到文件、行号、符号和关系", self.html)

    def test_waku_reports_closed_findings_and_final_review(self) -> None:
        self.assertIn("独立复验 PASS", self.html)
        self.assertIn("原始发现", self.html)
        self.assertIn("core-index-reaudit-round3.md", self.html)
        self.assertIn("examples/compatibility/waku-agent/index/index.html", self.html)
        for query in ("memory", "graph", "loop", "gateway"):
            self.assertIn(f"examples/compatibility/waku-agent/{query}/modules/{query}.html", self.html)
        self.assertNotIn("已进入核心修复门", self.html)

    def test_release_status_links_current_independent_audits(self) -> None:
        self.assertIn("生产验收 PASS · 单页为唯一阅读入口", self.html)
        self.assertNotIn("生产验收收口中", self.html)
        self.assertIn("core-index-reaudit-round3.md", self.html)
        self.assertIn("teaching-reaudit-round13.md", self.html)

    def test_serena_uses_the_current_specialist_report_not_the_stale_generic_page(self) -> None:
        self.assertIn("serena-specialist.html", self.html)
        self.assertIn("打开 Serena 当前源码专项分析", self.html)
        self.assertNotIn("project-code-serena.html", self.html)

    def test_long_decision_module_links_can_wrap_on_mobile(self) -> None:
        self.assertIn(
            ".decision-wrap a{overflow-wrap:anywhere;word-break:break-word;",
            self.html,
        )

    def test_all_embedded_file_links_exist(self) -> None:
        file_links = [link for link in self.parser.links if link.startswith("file:")]
        self.assertGreaterEqual(len(file_links), 150)
        missing = [
            Path(unquote(urlparse(link).path))
            for link in file_links
            if not Path(unquote(urlparse(link).path)).exists()
        ]
        self.assertEqual(missing, [])

    def test_html_has_unique_ids_and_no_external_runtime(self) -> None:
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))
        self.assertNotIn('<script src="http', self.html)
        self.assertNotIn('<link rel="stylesheet" href="http', self.html)

    def test_cli_writes_a_single_standalone_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "repo-teacher.html"
            original = __import__("sys").argv
            try:
                __import__("sys").argv = [str(SCRIPT), "--output", str(target)]
                self.assertEqual(self.builder.main(), 0)
            finally:
                __import__("sys").argv = original
            self.assertTrue(target.is_file())
            self.assertIn("<!doctype html>", target.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
