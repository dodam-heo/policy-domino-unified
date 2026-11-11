import datetime as dt
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unified.engine import parse_body, parse_index, compare_bodies, relative_path, store, load, streams


class EngineTest(unittest.TestCase):
    def test_persist_per_version(self):
        rec = {"source": "admrul", "stable_id": "abc", "serial": "123"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / relative_path(rec)
            self.assertTrue(store(path, {"record": rec, "body": {"status": "complete"}}))
            self.assertFalse(store(path, {"record": rec, "body": {"status": "complete"}}))
            self.assertEqual(load(path)["record"]["stable_id"], "abc")

    def test_no_unverified_annex(self):
        body = parse_body("""<root><조문단위><조문번호>1</조문번호>
           <조문내용>제1조 신청 기준을 변경한다.</조문내용></조문단위>
           <별표서식파일링크>https://www.law.go.kr/example.pdf</별표서식파일링크></root>""".encode())
        self.assertEqual(body["status"], "partial")
        self.assertEqual(len(body["attachment_links"]), 1)

    def test_actual_before_after(self):
        left = {"status": "complete", "clauses": {"제1조": "기준 100원"}}
        right = {"status": "complete", "clauses": {"제1조": "기준 120원"}}
        change = compare_bodies(left, right)
        self.assertEqual(change["status"], "changed")
        self.assertEqual(change["changes"][0]["before"], "기준 100원")
        self.assertEqual(change["changes"][0]["after"], "기준 120원")

    def test_kinds_all_and_not_hardcoded_to_three_notices(self):
        catalog = streams()
        self.assertIn(("admrul", "1", "3"), catalog)
        self.assertIn(("admrul", "2", "3"), catalog)
        self.assertIn(("admrul", "1", "4"), catalog)
        self.assertIn(("ordin", "2", ""), catalog)
        self.assertEqual(len(catalog), 15)


if __name__ == "__main__":
    unittest.main()
