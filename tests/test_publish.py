import json
import tempfile
import unittest
from pathlib import Path
from unified.engine import relative_path, store
from unified.publish import assemble


class PublishTest(unittest.TestCase):
    def test_unverified_agency_not_invented(self):
        doc = {"source": "admrul", "stable_id": "X", "serial": "123",
               "title": "행정규칙", "published_at": "2026-11-01"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store(path / relative_path(doc), {"record": doc, "body": {
                "status": "complete", "clauses": {"제1조": "본문"}}})
            result = assemble(path)
            self.assertEqual(result["total_source_versions_saved"], 1)
            self.assertEqual(result["summary"]["agency_action_count"], 0)
            self.assertEqual(len(result["events"]), 1)


if __name__ == "__main__":
    unittest.main()
