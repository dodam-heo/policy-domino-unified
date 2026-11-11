import tempfile
from pathlib import Path
import unittest
from unified.engine import store
from unified.catalog import indexed_documents, official_link


class CatalogTests(unittest.TestCase):
    def test_archived_and_live_versions_are_merged_without_dropping_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a={"source":"admrul","stable_id":"1","serial":"2027",
               "title":"2027년 기준 고시","published_at":"2026-07-01"}
            b={**a,"serial":"2026","title":"2026년 기준 고시"}
            store(root/"indexes"/"legacy"/"admrul"/"a.json.gz",
                  {"records":[a,b]})
            store(root/"indexes"/"admrul"/"recent.json.gz",
                  {"records":[{**a,"ministry":"중앙부처"}]})
            result=indexed_documents(root)
            self.assertEqual(len(result),2)
            self.assertEqual(result["admrul|1|2027"]["ministry"],"중앙부처")
            self.assertEqual(result["admrul|1|2027"]["index_grade"],
                             "official_api_indexed")
            self.assertIn("www.law.go.kr",official_link(a))
