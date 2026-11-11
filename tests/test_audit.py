import tempfile
import unittest
from pathlib import Path
from unified.audit import audit, write_reports
import json
import hashlib


def h(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]


class AuditTest(unittest.TestCase):
    def test_conflict_reuse_and_relative_gap(self):
        first = {"source": "admrul", "stable_id": "11", "serial": "22",
                 "title": "2027년도 기준 중위소득", "published_at": "2026-08-01"}
        second = {"source": "admrul", "stable_id": "11", "serial": "23",
                  "title": "2027년도 주거급여"}
        with tempfile.TemporaryDirectory() as directory:
            paths = {name: Path(directory) / (name + ".json")
                     for name in ("v2", "v4", "next")}
            src = {"events": {"foo": {**first, "changes": []}}, "pending": [],
                   "snapshots": {h("admrul|11"): {
                       "serial": "22", "clauses": {"제1조": "기준 변경"}}}}
            # v2 snapshots are reused only if their serial matches.
            paths["v2"].write_text(json.dumps(src, ensure_ascii=False))
            paths["v4"].write_text(json.dumps({
                "catalog": {"abc": first, "def": second},
                "verified_snapshots": {"abc": {**first,
                    "complete_source": True, "clauses": {"제1조": "기준 변경"}}},
                "coverage": [{"source": "admrul", "complete": False}]
            }, ensure_ascii=False))
            paths["next"].write_text(json.dumps({
                "documents": {"abc": {**first, "id": "abc"}},
                "versions": {"abc": {"status": "extracted",
                    "clauses": {"제1조": {"complete": True, "text": "기준 변경"}}}},
                "collection_windows": {}
            }, ensure_ascii=False))
            report, reuse = audit(paths)
            self.assertEqual(report["totals"]["unique_versions_union"], 2)
            self.assertEqual(report["totals"]["reusable_complete_versions"], 1)
            self.assertEqual(report["totals"]["relative_missing_versions"]["v2"]["v4"], 1)
            self.assertEqual(report["coverage"]["v4"]["incomplete"], 1)
            self.assertTrue(report["required_examples"]["기준 중위소득"]["validated"])
            write_reports(paths, Path(directory) / "report")
            self.assertTrue((Path(directory) / "report" / "audit.md").exists())

    def test_same_id_different_original_is_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {x: Path(directory) / (x + ".json") for x in ("v2", "v4", "next")}
            doc = {"source": "law", "stable_id": "A", "serial": "B", "title": "법"}
            paths["v2"].write_text(json.dumps({"events": {}, "snapshots": {}}))
            paths["v4"].write_text(json.dumps({"catalog": {"x": doc},
                "verified_snapshots": {"x": {**doc, "complete_source": True,
                                            "clauses": {"제1조": "첫번째"}}}}}, ensure_ascii=False))
            paths["next"].write_text(json.dumps({"documents": {"x": doc},
                "versions": {"x": {"status": "extracted", "clauses": {
                    "제1조": {"text": "두번째", "complete": True}}}}}, ensure_ascii=False))
            report, reuse = audit(paths)
            self.assertEqual(report["totals"]["body_conflicts"], 1)
            self.assertEqual(len(reuse), 0)


if __name__ == "__main__":
    unittest.main()
