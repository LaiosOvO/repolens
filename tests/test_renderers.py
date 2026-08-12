from __future__ import annotations

import unittest
from unittest.mock import patch

from repo_teacher.renderers import CanonicalIndexHtmlRenderer, HumanHtmlRenderer


class RendererBoundaryTest(unittest.TestCase):
    def test_renderers_select_an_explicit_schema_variant(self) -> None:
        payload: dict[str, object] = {"project": {"name": "fixture"}}
        with patch(
            "repo_teacher.renderers.human_html._render_report",
            return_value="<html></html>",
        ) as render:
            HumanHtmlRenderer().render(payload)
            CanonicalIndexHtmlRenderer().render(payload)

        self.assertEqual(render.call_args_list[0].kwargs, {"variant": "human"})
        self.assertEqual(render.call_args_list[1].kwargs, {"variant": "canonical"})


if __name__ == "__main__":
    unittest.main()
