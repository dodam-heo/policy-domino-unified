from pathlib import Path
import tempfile
import unittest
from unified.engine import _pending_index_records, store


class LegacyQueueTest(unittest.TestCase):
    def test_historic_metadata_is_resumable_and_live_wins(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = {"source": "admrul", "stable_id": "42", "serial": "93",
                    "title": "옛 이름", "published_at": "2025-01-01"}
            store(root/"indexes"/"legacy"/"admrul"/"a.json.gz",
                  {"records": [base]})
            self.assertEqual(_pending_index_records(root)[0]["title"], "옛 이름")
            store(root/"indexes"/"admrul"/"new.json.gz",
                  {"records": [{**base, "title": "공식 최신 이름"}]})
            found = _pending_index_records(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["title"], "공식 최신 이름")
