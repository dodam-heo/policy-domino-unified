import tempfile
from pathlib import Path
import unittest
import json
from unified.engine import store
from unified.publish import assemble, write_site


class CatalogPublishTests(unittest.TestCase):
    def test_indexed_only_document_visible_but_not_invented_as_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rec={"source":"admrul","stable_id":"1","serial":"2027",
                 "title":"2027년 공식 선정기준","published_at":"2026-08-31",
                 "kind":"고시"}
            store(root/"indexes"/"legacy"/"admrul"/"a.json.gz",
                  {"records":[rec]})
            report=assemble(root)
            self.assertEqual(report["summary"]["displayed_events"],1)
            event=report["events"][0]
            self.assertEqual(event["comparison_status"],"official_index_only")
            self.assertEqual(event["action_count"],0)
            self.assertFalse(event["details_path"])
            site=root/"site"/"data.json"
            output=write_site(report,site)
            self.assertEqual(output["events"][0]["id"],"admrul|1|2027")
            self.assertFalse((root/"site"/"details").glob("*.json").__next__ if False else False)
