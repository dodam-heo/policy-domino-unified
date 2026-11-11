import unittest
from unified.engine import parse_body
from unified.attachments import normalized_url


class FlatOfficialTests(unittest.TestCase):
    def test_flat_administrative_rules_keep_articles_and_addenda(self):
        raw = ('<AdmRulService><조문내용>제1조(목적) 실제 기준</조문내용>'
               '<조문내용>제2조(선정기준) 100원</조문내용>'
               '<부칙내용>2027년 1월 1일부터 시행</부칙내용></AdmRulService>').encode()
        body=parse_body(raw)
        self.assertEqual(body["clauses"]["제1조"],"제1조(목적) 실제 기준")
        self.assertIn("100원",body["clauses"]["제2조"])
        self.assertIn("2027년",body["clauses"]["부칙"])
        self.assertEqual(body["status"],"complete")

    def test_embedded_image_tables_are_explicitly_unresolved(self):
        raw=('<AdmRulService><조문내용>제2조 기준&lt;img id="8"&gt;'
             '&lt;/img&gt;</조문내용></AdmRulService>').encode()
        body=parse_body(raw)
        self.assertIn("제2조",body["clauses"])
        self.assertEqual(body["status"],"partial")
        self.assertIn("제2조",body["incomplete_keys"])

    def test_official_http_annex_is_securely_upgraded(self):
        self.assertEqual(
            normalized_url("http://law.go.kr/flDownload.do?flSeq=168087179"),
            "https://law.go.kr/flDownload.do?flSeq=168087179")
        self.assertEqual(normalized_url("http://evil.invalid/x"),"")
