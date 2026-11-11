import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unified.engine import run, _pending_index_records, relative_path, load


class OfficialStub:
    def __init__(self):
        self.queries = []
    def search(self, source, start, end, edition, kind, query=""):
        self.queries.append((source, edition, kind, query))
        # A notice discovered outside the small detail budget cannot disappear.
        doc = {"source": "admrul", "stable_id": "402", "serial": "999",
               "title": "2027년도 시험 정책기준", "published_at": "2026-09-01",
               "effective_date": "2027-01-01"}
        return [doc], {"reported": 1, "collected": 1, "pages": 1, "complete": True}
    def detail(self, rec):
        return ("<법령><조문단위><조문번호>1</조문번호>"
                "<조문내용>공식 변경 본문</조문내용></조문단위></법령>").encode()
    def predecessor(self, rec):
        return None, False


class IncrementalLedgerTest(unittest.TestCase):
    def test_discovered_versions_survive_zero_detail_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api = OfficialStub()
            run(root, api, limit_streams=1, detail_budget=0,
                today=dt.date(2026, 11, 11))
            pending = _pending_index_records(root)
            self.assertEqual(len(pending), 1)
            self.assertTrue(any(item[-1] == "2027" for item in api.queries))
            self.assertFalse((root / relative_path(pending[0])).exists())
            run(root, api, limit_streams=1, detail_budget=1,
                today=dt.date(2026, 11, 11))
            self.assertEqual(load(root / relative_path(pending[0]))["body"]["status"],
                             "complete")
            self.assertEqual(len(_pending_index_records(root)), 1)


if __name__ == "__main__":
    unittest.main()
