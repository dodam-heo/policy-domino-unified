import unittest
from unified.catalog import official_link


class OfficialVersionLinkTests(unittest.TestCase):
    def test_administrative_rule_opens_exact_official_revision(self):
        url=official_link({"source":"admrul","serial":"2100000284670",
                           "title":"2027년도 주거급여 선정기준",
                           "url":"https://www.law.go.kr/행정규칙/제목"})
        self.assertEqual(url,
            "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000284670")

    def test_law_opens_exact_official_revision(self):
        url=official_link({"source":"law","serial":"12345","title":"기준법"})
        self.assertIn("lsiSeq=12345",url)

    def test_unknown_version_does_not_invent_id(self):
        url=official_link({"source":"ordin","serial":"A12",
                           "title":"어떤 조례"})
        self.assertIn("www.law.go.kr",url)
