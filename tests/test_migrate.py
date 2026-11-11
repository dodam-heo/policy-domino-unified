import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from unified.migrate import migrate
from unified.engine import load, relative_path


class MigrationTests(unittest.TestCase):
    def test_seed_from_one_verified_original(self):
        doc = {"source": "law", "stable_id": "a", "serial": "101",
               "title": "공식 규정", "published_at": "2026-01-01"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {x: root/(x+".json") for x in ("v2", "v4", "next")}
            paths["v2"].write_text('{"events":{},"snapshots":{}}')
            paths["v4"].write_text(json.dumps({
                "catalog": {"abc": doc}, "verified_snapshots": {
                    "abc": dict(doc, complete_source=True,
                                clauses={"제1조": "신규 기준 100원"})}},
                ensure_ascii=False))
            paths["next"].write_text('{"documents":{},"versions":{}}')
            summary = migrate(paths, root/"out")
            self.assertEqual(summary["imported_originals"], 1)
            saved = load(root/"out"/relative_path(doc))
            self.assertEqual(saved["body"]["status"], "complete")
            self.assertFalse(saved["source_snapshot_provenance"]["has_raw_official_xml"])


if __name__ == "__main__":
    unittest.main()
