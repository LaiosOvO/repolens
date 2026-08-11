from __future__ import annotations

import unittest

from repo_teacher.snapshot import _sanitize_remote


class SnapshotSanitizationTest(unittest.TestCase):
    def test_url_remote_discards_credentials_query_and_fragment(self) -> None:
        value = "https://alice:secret-token@example.com/org/repo.git?token=bad#fragment"

        self.assertEqual(
            _sanitize_remote(value), "https://example.com/org/repo.git"
        )

    def test_scp_remote_removes_token_userinfo_but_keeps_transport_user(self) -> None:
        self.assertEqual(
            _sanitize_remote(
                ("github_pat_" + "AAAAAAAAAAAAAAAAAAAAAAAA")
                + "@example.com:org/repo.git?x=1"
            ),
            "example.com:org/repo.git",
        )
        self.assertEqual(
            _sanitize_remote("git@github.com:org/repo.git"),
            "git@github.com:org/repo.git",
        )


if __name__ == "__main__":
    unittest.main()
