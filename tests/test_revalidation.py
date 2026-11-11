import tempfile
from pathlib import Path
import unittest
from unified.engine import process, store, load, relative_path


class FakeApi:
    def detail(self, rec):
        return ('<AdmRulService><조문내용>제1조 새 본문 '
                '&lt;img id="1"&gt;&lt;/img&gt;</조문내용></AdmRulService>').encode()


class RevalidateTests(unittest.TestCase):
    def test_historic_text_preserved_when_fresh_official_has_image(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            doc={"source":"admrul","stable_id":"7","serial":"9",
                 "title":"시험고시"}
            store(root/relative_path(doc),{"record":doc,"body":{
                "status":"legacy_extracted","clauses":{"제1조":"종전 문장"}},
                "source_snapshot_provenance":{"has_raw_official_xml":False}})
            out=process(FakeApi(),root,{},doc)
            self.assertEqual(out["body"]["status"],"partial")
            self.assertIn("제1조",out["body"]["clauses"])
            archive=list((root/"historic_extracts").glob("*.json.gz"))
            self.assertEqual(len(archive),1)
            self.assertEqual(load(archive[0])["body"]["clauses"]["제1조"],"종전 문장")
