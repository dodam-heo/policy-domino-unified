import unittest
from unified.engine import _local_predecessor


class YearlessStandardTests(unittest.TestCase):
    def test_yearless_renamed_rule_can_match_year_specific_predecessor(self):
        old={"source":"admrul","stable_id":"X","serial":"11",
             "title":"2026년 기준 중위소득 및 생계·의료급여 선정기준과 최저보장수준",
             "ministry":"공식기관","kind":"고시","published_at":"2025-08-01",
             "effective_date":"2026-01-01"}
        new={"source":"admrul","stable_id":"Y","serial":"22",
             "title":"기준 중위소득, 생계급여ㆍ의료급여의 수급자 선정기준 및 최저보장수준",
             "ministry":"공식기관","kind":"고시","published_at":"2026-07-29",
             "effective_date":"2027-01-01"}
        found,annual=_local_predecessor(new,[old,new])
        self.assertTrue(annual)
        self.assertEqual(found["serial"],"11")
