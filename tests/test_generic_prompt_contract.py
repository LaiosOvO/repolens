from __future__ import annotations

import unittest
from pathlib import Path


class GenericPromptContractTest(unittest.TestCase):
    def test_business_discovery_prompts_do_not_embed_repository_or_domain_examples(self) -> None:
        prompt_root = Path(__file__).parents[1] / "src" / "repo_teacher" / "prompts"
        prompt_names = (
            "inventory-global-v1.md",
            "inventory-shard-v1.md",
            "inventory-grouping-v1.md",
            "inventory-review-v1.md",
        )
        forbidden = (
            "coze",
            "waku",
            "pipecat",
            "dograh",
            "voxa",
            "数字员工平台应",
            "实时语音主链",
        )

        for name in prompt_names:
            source = (prompt_root / name).read_text(encoding="utf-8").casefold()
            for token in forbidden:
                with self.subTest(prompt=name, token=token):
                    self.assertNotIn(token.casefold(), source)


if __name__ == "__main__":
    unittest.main()
