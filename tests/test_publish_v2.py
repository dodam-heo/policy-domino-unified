import json
import tempfile
import unittest
from pathlib import Path
from unified.engine import store, ident, relative_path
from unified.publish import assemble, write_site


class PublicationContractTest(unittest.TestCase):
    def test_archived_original_not_counted_as_verified_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = {"source": "admrul", "stable_id": "1", "serial": "01",
                   "title": "시험 고시", "published_at": "2025-01-01"}
            new = {**old, "serial": "02", "published_at": "2026-01-01",
                   "revision": "일부개정"}
            store(root/relative_path(old), {"record": old, "body": {
                "status": "legacy_extracted", "clauses": {"본문": "100원"}},
                "source_snapshot_provenance": {"has_raw_official_xml": False}})
            store(root/relative_path(new), {"record": new, "body": {
                "status": "complete", "raw_xml_sha256": "valid",
                "clauses": {"본문": "120원"}}, "official_xml_base64": "ZGF0YQ=="})
            store(root/"comparisons"/"c.json.gz", {
                "changed_record": new, "prior_record": old, "status": "changed",
                "changes": [{"clause": "본문", "before": "100원",
                             "after": "120원"}]})
            report = assemble(root)
            self.assertEqual(report["summary"]["with_source_changes"], 1)
            self.assertEqual(report["summary"]["with_verified_changes"], 0)
            self.assertEqual(report["events"][0]["change_type"], "amended")
            output = root/"site"/"data.json"
            listing = write_site(report, output)
            self.assertEqual(listing["summary"]["with_verified_changes"], 0)
            self.assertNotIn("changes", listing["events"][0])
            detail = json.loads((root/"site"/listing["events"][0]["details_path"]).read_text())
            self.assertEqual(detail["changes"][0]["before"], "100원")
            self.assertEqual(detail["verification"],
                             "historical_comparison_needs_revalidation")
