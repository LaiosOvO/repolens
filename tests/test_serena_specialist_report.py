from __future__ import annotations

from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import unittest
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_serena_specialist_report.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("serena_specialist_report", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("Serena specialist builder could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")


class SerenaSpecialistReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.html = cls.builder.build_html()
        cls.parser = _Parser()
        cls.parser.feed(cls.html)

    def test_report_is_feature_first_and_uses_current_clone(self) -> None:
        self.assertIn("这个项目有哪些功能", self.html)
        self.assertIn("一句话技术选型结论", self.html)
        self.assertIn("FindReferencingSymbolsTool", Path(self.builder.SERENA_ROOT / "src/serena/tools/symbol_tools.py").read_text())
        self.assertIn(self.builder._git("rev-parse", "HEAD"), self.html)
        self.assertIn("trusted project 不是沙箱", self.html)
        self.assertIn("项目记忆管理（不是代码引用）", self.html)
        self.assertNotIn("query_project_tools.py", self.html)
        self.assertNotIn("jquery.min.js", self.html)

    def test_all_feature_cards_have_targets_and_all_local_sources_exist(self) -> None:
        fragments = [href[1:] for href in self.parser.hrefs if href.startswith("#")]
        self.assertEqual(len(fragments), 6)
        self.assertTrue(all(fragment in self.parser.ids for fragment in fragments))
        local = [href for href in self.parser.hrefs if href.startswith("file:")]
        self.assertGreaterEqual(len(local), 10)
        missing = [Path(unquote(urlparse(href).path)) for href in local if not Path(unquote(urlparse(href).path)).exists()]
        self.assertEqual(missing, [])

    def test_report_is_offline_and_mobile_rules_are_present(self) -> None:
        self.assertNotIn('<script src="http', self.html)
        self.assertNotIn('<link rel="stylesheet" href="http', self.html)
        self.assertIn("@media(max-width:720px)", self.html)
        self.assertIn(".hero,.features,.explain,.sources{grid-template-columns:1fr}", self.html)
        self.assertIn(".source>*{min-width:0;max-width:100%;overflow-wrap:anywhere", self.html)


if __name__ == "__main__":
    unittest.main()
