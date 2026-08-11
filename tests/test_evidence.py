from __future__ import annotations

import unittest

from repo_teacher.evidence import EvidenceStore, redact_secrets


class EvidenceStoreTest(unittest.TestCase):
    def test_adds_deduplicated_grounded_snippet_with_hash(self) -> None:
        store = EvidenceStore({"src/app.py": "first\nsecond\nthird\n"})

        first = store.add("src/app.py", 2, 3, kind="definition", confidence="exact")
        duplicate = store.add("src/app.py", 2, 3, kind="definition", confidence="exact")

        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(first.snippet, "second\nthird")
        self.assertEqual(len(first.snippet_sha256), 64)
        self.assertTrue(store.validate(first))
        self.assertEqual(len(store.records), 1)

    def test_rejects_unknown_paths_and_invalid_line_ranges(self) -> None:
        store = EvidenceStore({"src/app.py": "one\ntwo\n"})

        with self.assertRaises(ValueError):
            store.add("../secret.py", 1, 1)
        with self.assertRaises(ValueError):
            store.add("missing.py", 1, 1)
        with self.assertRaises(ValueError):
            store.add("src/app.py", 0, 1)
        with self.assertRaises(ValueError):
            store.add("src/app.py", 2, 3)

    def test_redacts_credentials_but_validates_against_original_source(self) -> None:
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        store = EvidenceStore(
            {"src/settings.py": f'api_key = "super-secret-value"\naws = "{secret}"\n'}
        )

        evidence = store.add("src/settings.py", 1, 2)

        self.assertNotIn("super-secret-value", evidence.snippet)
        self.assertNotIn(secret, evidence.snippet)
        self.assertEqual(evidence.snippet.count("[REDACTED]"), 2)
        self.assertTrue(store.validate(evidence))

    def test_fail_closed_secret_corpus_never_reaches_display_snippet(self) -> None:
        secrets = {
            "github": "github_pat_" + "AAAAAAAAAAAAAAAAAAAAAAAA",
            "bearer": "Bearer opaque-token-that-must-not-leak",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.AAAAAAAAAAAAAAAA",
            "database": "postgresql://alice:database-password@db.local/prod",
            "quoted": 'client_secret = "quoted-secret-value"',
            "unquoted": "password=unquoted-secret-value",
        }
        source = "\n".join(secrets.values()) + "\n"
        store = EvidenceStore({"settings.env": source})

        evidence = store.add("settings.env", 1, len(secrets))

        for value in (
            secrets["github"],
            "opaque-token-that-must-not-leak",
            secrets["jwt"],
            "alice:database-password",
            "quoted-secret-value",
            "unquoted-secret-value",
        ):
            self.assertNotIn(value, evidence.snippet)
        self.assertTrue(store.validate(evidence))

    def test_ordinary_code_is_not_modified_by_secret_scanner(self) -> None:
        source = 'url = "https://example.com/docs"\ntoken_count = 3\n'

        self.assertEqual(redact_secrets(source), source)


if __name__ == "__main__":
    unittest.main()
