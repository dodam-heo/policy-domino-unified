import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from unified.audit import audit, write_reports


def hash20(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class AuditTest(unittest.TestCase):
    def fixture(self, root, v2, v4, next_state):
        paths = {key: Path(root) / (key + ".json") for key in ("v2", "v4", "next")}
        for key, value in (("v2", v2), ("v4", v4), ("next", next_state)):
            paths[key].write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")
        return paths

    def test_reuse_and_relative_gap(self):
        first = dict(source="admrul", stable_id="11", serial="22",
                     title="2027년도 기준 중위소득", published_at="2026-08-01")
        second = dict(source="admrul", stable_id="11", serial="23",
                      title="2027년도 주거급여")
        v2 = {"events": {"foo": first}, "pending": [],
              "snapshots": {hash20("admrul|11"):
                            {"serial": "22", "clauses": {"제1조": "기준 변경"}}}}
        v4 = {"catalog": {"abc": first, "def": second},
              "verified_snapshots": {"abc": dict(first, complete_source=True,
                                                  clauses={"제1조": "기준 변경"})},
              "coverage": [{"source": "admrul", "complete": False}]}
        next_state = {"documents": {"abc": dict(first, id="abc")},
                      "versions": {"abc": {"status": "extracted", "clauses": {
                          "제1조": {"complete": True, "text": "기준 변경"}}}},
                      "collection_windows": {}}
        with tempfile.TemporaryDirectory() as root:
            paths = self.fixture(root, v2, v4, next_state)
            report, reuse = audit(paths)
            self.assertEqual(report["totals"]["unique_versions_union"], 2)
            self.assertEqual(report["totals"]["reusable_complete_versions"], 1)
            self.assertEqual(len(reuse), 1)
            self.assertEqual(report["totals"]["relative_missing_versions"]["v2"]["v4"], 1)
            self.assertEqual(report["coverage"]["v4"]["incomplete"], 1)
            self.assertTrue(report["required_examples"]["기준 중위소득"]["validated"])
            write_reports(paths, Path(root) / "report")
            self.assertTrue((Path(root) / "report" / "audit.md").exists())

    def test_conflicting_originals(self):
        doc = dict(source="law", stable_id="A", serial="B", title="법")
        v2 = {"events": {}, "snapshots": {}}
        v4 = {"catalog": {"x": doc},
              "verified_snapshots": {"x": dict(doc, complete_source=True,
                                                  clauses={"제1조": "첫번째"})}}
        next_state = {"documents": {"x": doc},
                      "versions": {"x": {"status": "extracted", "clauses": {
                          "제1조": {"text": "두번째", "complete": True}}}}}
        with tempfile.TemporaryDirectory() as root:
            paths = self.fixture(root, v2, v4, next_state)
            report, reuse = audit(paths)
            self.assertEqual(report["totals"]["body_conflicts"], 1)
            self.assertEqual(len(reuse), 0)


if __name__ == "__main__":
    unittest.main()
