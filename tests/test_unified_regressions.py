import base64
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from unified.acceptance import evaluate
from unified.engine import ident, parse_body, process, relative_path, store
from unified.impact import run as impact_run
from unified.publish import write_site


class UnifiedRegressionTests(unittest.TestCase):
    def test_recover_saved_official_xml_without_network(self):
        xml = ('<root><조문내용>제1조 &lt;img id="1"&gt;'
               '</조문내용></root>').encode()
        record = dict(source="admrul", stable_id="1", serial="2",
                      title="시험 고시", published_at="2026-11-11")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store(root / relative_path(record),
                  {"record": record, "body": parse_body(xml),
                   "official_xml_base64": base64.b64encode(xml).decode("ascii")})
            class Offline:
                def detail(self, record):
                    raise AssertionError("Already saved original must not be re-fetched")
            recovered = process(Offline(), root, {}, record)
            self.assertEqual(recovered["body"]["raw_xml_sha256"],
                             hashlib.sha256(xml).hexdigest())

    def test_archive_entry_is_seen_by_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            site = Path(directory) / "site"
            serial = "2100000283464"
            record = dict(source="admrul", stable_id="1", serial=serial,
                          title="시험 기준", published_at="2026-11-11")
            store(root / relative_path(record),
                  {"record": record, "body": {"status": "legacy_extracted",
                   "clauses": {"본문": "시험"}}})
            store(root / "indexes" / "admrul" / "seed.json.gz",
                  {"records": [record]})
            (site / "catalog").mkdir(parents=True)
            (site / "data.json").write_text(json.dumps(
                {"events": [], "archive_shards": ["catalog/00000.json"]}), "utf8")
            (site / "catalog" / "00000.json").write_text(json.dumps(
                {"events": [{"id": ident(record), "details_path": ""}]}), "utf8")
            cases = evaluate(root, site)["required_examples"]
            self.assertTrue(cases[0]["stages"]["published"])
            self.assertFalse(cases[0]["stages"]["official_original_verified"])

    def test_full_impact_corpus_not_capped_at_300(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(301):
                record = {"source": "law", "stable_id": str(number),
                          "serial": str(number), "title": "시험 법률"}
                store(root / "comparisons" / (str(number) + ".json.gz"),
                      {"status": "no_text_change", "changed_record": record,
                       "changes": []})
            result = impact_run(root)
            self.assertEqual(result["comparisons_considered"], 301)

    def test_initial_catalog_includes_prior_important_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site" / "data.json"
            events = []
            for i in range(760):
                events.append({"id": "record-"+str(i), "details_path": "",
                               "published_at": "2026-11-11",
                               "verification": "comparison_incomplete",
                               "support_standard": False,
                               "change_count": int(i == 759),
                               "action_count": 0})
            index = write_site({"events": events, "summary": {},
                                "quality": {}}, output)
            self.assertEqual(len(index["events"]), 700)
            self.assertIn("record-759", {e["id"] for e in index["events"]})
            self.assertEqual(sum(len(json.loads((output.parent / shard)
                                .read_text("utf8"))["events"])
                                for shard in index["archive_shards"]), 60)


if __name__ == "__main__":
    unittest.main()
