from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

from repo_teacher.report import render_report


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE and CHROME.is_file(),
    "Playwright and a local Chromium browser are required for viewport assertions",
)
class ReportMobileBrowserTest(unittest.TestCase):
    def test_desktop_and_mobile_viewports_are_usable_without_overflow(self) -> None:
        from playwright.sync_api import sync_playwright

        long_path = "src/" + "/".join(["very-long-component-name"] * 12) + "/implementation.py"
        index = {
            "schema_version": "2.0",
            "project": {"name": "Mobile overflow oracle", "path": "/tmp/mobile-oracle"},
            "stats": {"files": 1, "languages": {"Python": 1}, "skipped": {}},
            "features": [
                {
                    "id": "mobile-feature",
                    "title": "A very long feature title " * 8,
                    "kind": "capability-cluster",
                    "summary": "A long summary " * 30,
                    "entrypoint": long_path,
                    "confidence": "source-audited",
                    "source": "mobile-browser-oracle",
                    "technology_tags": [
                        "parser:python-ast", "framework:unknown", "store:unknown",
                        "retrieval:unknown", "llm:unknown", "incremental:unknown",
                        "evidence:source-lines", "ui:unknown",
                    ],
                    "technology_claims": [
                        {
                            "dimension": "parser",
                            "value": "python-ast",
                            "claim_scope": "bounded parser claim " * 20,
                            "confidence": "source-audited",
                            "evidence_ids": ["mobile-evidence"],
                            "source_path": long_path,
                        }
                    ],
                    "steps": [
                        {
                            "order": 1,
                            "title": "Long source responsibility",
                            "explanation": "static teaching explanation " * 20,
                            "path": long_path,
                            "line_start": 1,
                            "line_end": 4,
                            "source_symbol": "VeryLongQualifiedSymbol." * 14,
                            "source_role": "state ownership",
                            "claim_scope": "local source responsibility only " * 15,
                            "relationship_kind": "constructs:VeryLongTargetName",
                            "snippet_sha256": "a" * 64,
                            "evidence_ids": ["mobile-evidence"],
                        }
                    ],
                    "evidence_ids": ["mobile-evidence"],
                    "test_evidence_ids": [],
                }
            ],
            "evidence": [
                {
                    "id": "mobile-evidence",
                    "path": long_path,
                    "line_start": 1,
                    "line_end": 4,
                    "snippet": "VeryLongUnbrokenToken" * 40,
                    "kind": "technology-claim:parser",
                    "confidence": "source-audited",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            index["project"]["path"] = directory
            source_path = Path(directory) / long_path
            source_path.parent.mkdir(parents=True)
            source_path.write_text("pass\n" * 4, encoding="utf-8")
            report_path = Path(directory) / "report.html"
            report_path.write_text(render_report(index), encoding="utf-8")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(CHROME),
                    headless=True,
                )
                observations = []
                for width, height in ((1440, 900), (390, 844)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto(report_path.as_uri(), wait_until="load")
                    first_screen_usable = page.evaluate(
                        """(height) => {
                          const title = document.querySelector('h1').getBoundingClientRect();
                          return title.top >= 0 && title.top < height && title.width > 0;
                        }""",
                        height,
                    )
                    page.locator(".deep-dive > summary").click()
                    self.assertTrue(page.locator(".deep-dive").evaluate("node => node.open"))
                    source_link = page.locator("a.source-link").first
                    href = source_link.get_attribute("href")
                    self.assertIsNotNone(href)
                    parsed_href = urlparse(str(href))
                    self.assertEqual(parsed_href.scheme, "file")
                    self.assertTrue(
                        Path(unquote(parsed_href.path))
                        .resolve()
                        .is_relative_to(Path(directory).resolve())
                    )
                    page.evaluate(
                        """() => {
                          window.__sourceLinkClicked = false;
                          document.querySelector('a.source-link').addEventListener('click', (event) => {
                            event.preventDefault();
                            window.__sourceLinkClicked = true;
                          }, {once: true});
                        }"""
                    )
                    source_link.click()
                    self.assertTrue(page.evaluate("window.__sourceLinkClicked"))
                    observations.append(
                        page.evaluate(
                            """([width, firstScreenUsable]) => {
                              return {
                                width,
                                viewport: document.documentElement.clientWidth,
                                page: document.documentElement.scrollWidth,
                                body: document.body.scrollWidth,
                                firstScreenUsable,
                                offenders: [...document.querySelectorAll('body *')]
                                  .filter((node) => {
                                    const box = node.getBoundingClientRect();
                                    return box.width > 0 && (box.left < -0.5 || box.right > width + 0.5);
                                  })
                                  .slice(0, 10)
                                  .map((node) => `${node.tagName}.${node.className}`)
                              };
                            }""",
                            [width, first_screen_usable],
                        )
                    )
                    page.close()
                browser.close()

        for observation in observations:
            self.assertEqual(observation["viewport"], observation["width"])
            self.assertEqual(observation["page"], observation["width"])
            self.assertEqual(observation["body"], observation["width"])
            self.assertTrue(observation["firstScreenUsable"])
            self.assertEqual(observation["offenders"], [])


if __name__ == "__main__":
    unittest.main()
