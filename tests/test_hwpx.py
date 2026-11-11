import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from unified.attachments import _format, hwpx_text, resolve_attachments


def sample_hwpx():
    output=io.BytesIO()
    section=('<?xml version="1.0" encoding="utf-8"?>'
      '<root xmlns:h="urn:hwp">'
      '<h:p><h:t>2027년 소득 및 선정기준</h:t></h:p>'
      '<h:tbl><h:tr><h:tc><h:p><h:t>가구원</h:t></h:p></h:tc>'
      '<h:tc><h:p><h:t>기준금액</h:t></h:p></h:tc></h:tr>'
      '<h:tr><h:tc><h:p><h:t>4인 가구</h:t></h:p></h:tc>'
      '<h:tc><h:p><h:t>6,929,885원</h:t></h:p></h:tc></h:tr>'
      '</h:tbl></root>')
    with zipfile.ZipFile(output,"w") as archive:
        archive.writestr("mimetype","application/hwp+zip")
        archive.writestr("Contents/section0.xml",section)
    return output.getvalue()


class HWPXTests(unittest.TestCase):
    def test_extract_household_amount_with_table_cells(self):
        raw=sample_hwpx()
        self.assertEqual(_format(raw),"hwpx")
        result=hwpx_text(raw)
        self.assertIn("4인 가구 | 6,929,885원",result)
        self.assertIn("2027년",result)

    def test_official_hwpx_annex_becomes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            original={"status":"partial","clauses":{"본문":"선정기준"},
                      "attachment_links":["http://law.go.kr/flDownload.do?flSeq=2"],
                      "incomplete_keys":[]}
            result=resolve_attachments(Path(directory),original,
                         transport=lambda url:sample_hwpx())
            self.assertEqual(result["attachments"][0]["format"],"hwpx")
            self.assertTrue(result["attachments"][0]["verified_text"])
            self.assertIn("6,929,885원",result["clauses"]["첨부 1"])
            self.assertEqual(result["status"],"complete")
