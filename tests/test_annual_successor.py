import unittest
from unified.engine import _local_predecessor


class AnnualTests(unittest.TestCase):
    def test_yearly_successor_can_have_changed_name_and_official_id(self):
        prior={"source":"admrul","stable_id":"1","serial":"100",
               "ministry":"공식 중앙부처","kind":"고시",
               "title":"2026년 기준소득 및 지원금액의 고시",
               "published_at":"2025-07-01"}
        current={**prior,"stable_id":"2","serial":"200",
                 "published_at":"2026-07-01",
                 "title":"2027년도 기준소득 및 지원금액 결정에 관한 고시"}
        found,annual=_local_predecessor(current,[prior,current])
        self.assertTrue(annual)
        self.assertEqual(found["serial"],"100")

    def test_no_cross_ministry_or_title_only_fabrication(self):
        prior={"source":"admrul","stable_id":"1","serial":"100",
               "ministry":"다른 부처","kind":"고시",
               "title":"2026년도 기준소득","published_at":"2025-07-01"}
        current={**prior,"stable_id":"2","serial":"200",
                 "ministry":"원래 부처",
                 "published_at":"2026-07-01",
                 "title":"2027년도 기준소득"}
        self.assertEqual(_local_predecessor(current,[prior,current]),(None,False))
