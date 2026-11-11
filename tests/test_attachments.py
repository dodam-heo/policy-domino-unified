import tempfile
import unittest
from pathlib import Path
from unified.attachments import normalized_url, resolve_attachments


class AnnexTest(unittest.TestCase):
    def test_block_non_law_portal_hosts(self):
        self.assertEqual(normalized_url("https://attacker.invalid/file.pdf"), "")
        self.assertTrue(normalized_url("/LSW/test.pdf").startswith("https://www.law.go.kr/"))
    def test_never_certify_unreadable_annex(self):
        with tempfile.TemporaryDirectory() as temp:
            doc={"status":"partial","clauses":{"제1조":"본문"},
                 "attachment_links":["https://www.law.go.kr/LSW/annex.pdf"]}
            row=resolve_attachments(Path(temp),doc,transport=lambda url:b"not a valid pdf")
            self.assertEqual(row["status"],"partial")
            self.assertEqual(len(row["unresolved_attachments"]),1)
            self.assertFalse(row["attachments"][0]["verified_text"])


if __name__=="__main__":
    unittest.main()
