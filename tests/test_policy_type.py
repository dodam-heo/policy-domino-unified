import unittest
import xml.etree.ElementTree as ET
from unified.engine import parse_index


class KindTests(unittest.TestCase):
    def test_official_law_kind_is_not_administrative_rule(self):
        raw='<LawSearch><law><법령명한글>시험법</법령명한글><법령ID>10</법령ID><법령일련번호>100</법령일련번호><공포일자>20260101</공포일자><법령구분명>법률</법령구분명></law></LawSearch>'
        result=parse_index(ET.fromstring(raw),"law")
        self.assertEqual(result[0]["kind"],"법률")

    def test_admin_kind_uses_verified_query_filter(self):
        raw='<AdmRulSearch><admrul><행정규칙명>시험기준</행정규칙명><행정규칙ID>10</행정규칙ID><행정규칙일련번호>100</행정규칙일련번호><발령일자>20260101</발령일자></admrul></AdmRulSearch>'
        result=parse_index(ET.fromstring(raw),"admrul","3")
        self.assertEqual(result[0]["kind"],"고시")
