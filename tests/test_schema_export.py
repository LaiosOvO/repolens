from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.export_inventory_schema import main


class SchemaExportTest(unittest.TestCase):
    def test_check_detects_stale_schema_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.schema.json"
            path.write_text("{}\n", encoding="utf-8")

            self.assertEqual(main([str(path), "--check"]), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), "{}\n")
            self.assertEqual(main([str(path)]), 0)
            self.assertEqual(main([str(path), "--check"]), 0)


if __name__ == "__main__":
    unittest.main()
