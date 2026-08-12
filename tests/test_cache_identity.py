from __future__ import annotations

import unittest

from unittest.mock import patch

from repo_teacher.pipeline.cache_identity import (
    build_run_identity,
    build_stage_cache_identity,
    build_workspace_root_identity,
    contract_digest_subset,
    packaged_contract_digests,
    provider_model_identity,
    provider_stage_identity,
)


class CacheIdentityTest(unittest.TestCase):
    def _identity(
        self,
        *,
        contract: str = "a",
        model: str = "m",
        source_manifest: str = "manifest",
        indexed_content: str = "content",
    ) -> str:
        result = build_run_identity(
            source="/repo",
            commit="abc",
            analysis_fingerprint="fp",
            source_manifest_sha256=source_manifest,
            indexed_content_sha256=indexed_content,
            provider="codex",
            inventory_sha256=None,
            synthesis_contract="v1",
            contract_digests={"prompt": contract, "schema": "s"},
            provider_config={"provider": "codex", "model": model, "reasoning": "low"},
        )
        return str(result["identity_sha256"])

    def test_prompt_or_schema_change_invalidates_cache(self) -> None:
        self.assertNotEqual(self._identity(contract="a"), self._identity(contract="b"))

    def test_model_change_invalidates_cache(self) -> None:
        self.assertNotEqual(self._identity(model="m1"), self._identity(model="m2"))

    def test_metadata_only_manifest_change_reuses_semantic_cache(self) -> None:
        self.assertEqual(
            self._identity(source_manifest="metadata-a"),
            self._identity(source_manifest="metadata-b"),
        )

    def test_indexed_content_change_invalidates_semantic_cache(self) -> None:
        self.assertNotEqual(
            self._identity(indexed_content="content-a"),
            self._identity(indexed_content="content-b"),
        )

    def test_packaged_contracts_include_semantic_and_human_report_schemas(self) -> None:
        digests = packaged_contract_digests()

        self.assertIn("schema:inventory-semantic-review", digests)
        self.assertIn("schema:human-report", digests)
        self.assertIn("repo_teacher.pipeline:semantic_review.py", digests)
        self.assertIn("repo_teacher.providers:runtime.py", digests)
        self.assertIn("repo_teacher:human_report.py", digests)

    def test_codex_cache_identity_includes_fast_inventory_model_route(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "REPO_TEACHER_CODEX_MODEL": "review-model",
                "REPO_TEACHER_CODEX_INVENTORY_MODEL": "inventory-model",
            },
            clear=False,
        ):
            identity = provider_model_identity("codex")

        self.assertEqual(identity["model"], "review-model")
        self.assertEqual(identity["inventory_model"], "inventory-model")

    def test_stage_identity_ignores_unrelated_contract_digests(self) -> None:
        available_a = {
            "repo_teacher.prompts:inventory-shard-v1.md": "prompt",
            "schema:inventory-model": "schema",
            "repo_teacher.renderers:html.py": "renderer-a",
        }
        available_b = {
            **available_a,
            "repo_teacher.renderers:html.py": "renderer-b",
        }
        selected = [
            "repo_teacher.prompts:inventory-shard-v1.md",
            "schema:inventory-model",
        ]

        identity_a = build_stage_cache_identity(
            stage="inventory-shard",
            source="/repo",
            indexed_content_sha256="content",
            packet_sha256="packet",
            provider_config=provider_stage_identity("codex", inventory=True),
            contract_digests=contract_digest_subset(available_a, selected),
        )
        identity_b = build_stage_cache_identity(
            stage="inventory-shard",
            source="/repo",
            indexed_content_sha256="content",
            packet_sha256="packet",
            provider_config=provider_stage_identity("codex", inventory=True),
            contract_digests=contract_digest_subset(available_b, selected),
        )

        self.assertEqual(identity_a["identity_sha256"], identity_b["identity_sha256"])

    def test_stage_identity_changes_with_inventory_route(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "REPO_TEACHER_CODEX_MODEL": "review-model",
                "REPO_TEACHER_CODEX_INVENTORY_MODEL": "inventory-model",
            },
            clear=False,
        ):
            default_provider = provider_stage_identity("codex")
            inventory_provider = provider_stage_identity("codex", inventory=True)

        self.assertNotEqual(default_provider, inventory_provider)

        identity_default = build_stage_cache_identity(
            stage="inventory-shard",
            source="/repo",
            indexed_content_sha256="content",
            packet_sha256="packet",
            provider_config=default_provider,
            contract_digests={"schema:inventory-model": "schema"},
        )
        identity_inventory = build_stage_cache_identity(
            stage="inventory-shard",
            source="/repo",
            indexed_content_sha256="content",
            packet_sha256="packet",
            provider_config=inventory_provider,
            contract_digests={"schema:inventory-model": "schema"},
        )

        self.assertNotEqual(
            identity_default["identity_sha256"],
            identity_inventory["identity_sha256"],
        )

    def test_stage_identity_changes_with_materialized_graph_context(self) -> None:
        common = {
            "stage": "inventory-shard",
            "source": "/repo",
            "indexed_content_sha256": "content",
            "provider_config": {"provider": "codex", "model": "inventory"},
            "contract_digests": {"schema:inventory-model": "schema"},
        }
        first = build_stage_cache_identity(packet_sha256="graph-a", **common)
        second = build_stage_cache_identity(packet_sha256="graph-b", **common)

        self.assertNotEqual(first["identity_sha256"], second["identity_sha256"])

    def test_schema_subset_does_not_include_unrelated_schema_module_digest(self) -> None:
        available_a = {
            "repo_teacher.schemas:__init__.py": "all-schemas-a",
            "schema:inventory-model": "inventory-schema",
        }
        available_b = {
            **available_a,
            "repo_teacher.schemas:__init__.py": "all-schemas-b",
        }

        self.assertEqual(
            contract_digest_subset(available_a, ["schema:inventory-model"]),
            contract_digest_subset(available_b, ["schema:inventory-model"]),
        )

    def test_workspace_root_identity_is_stable_for_same_repo_inputs(self) -> None:
        first = build_workspace_root_identity(
            source="/repo",
            indexed_content_sha256="content",
            provider="codex",
        )
        second = build_workspace_root_identity(
            source="/repo",
            indexed_content_sha256="content",
            provider="codex",
        )

        self.assertEqual(first["identity_sha256"], second["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
