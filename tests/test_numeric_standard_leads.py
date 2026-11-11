import unittest
from unified.impact import numeric_standard_leads
from unified.relations import index_program_references


class NumericStandardLeadTests(unittest.TestCase):
    def setUp(self):
        self.doc = {"title": "2027년 주거급여 선정기준",
                    "url": "https://www.law.go.kr"}
        self.comparison = {
            "status": "partial_unverified",
            "changes": [{
                "clause": "본문 1",
                "before": "「주거급여법」 제5조제1항에 따라 주거급여 선정기준을 정한다.",
                "after": "「주거급여법」 제5조제1항에 따라 주거급여 선정기준을 정한다.",
            }],
            "numeric_changes": [{
                "table": 1, "row": "금액 (원/월)", "column": "4인 가구",
                "before": "3,117,474", "after": "3,326,345",
                "old_attachment_sha256": "a"*64,
                "new_attachment_sha256": "b"*64,
                "verification": "official_hwpx_cell_pair",
            }],
        }
        self.program = {
            "id": "svc1", "agency": "공식 서비스기관", "agency_type": "공공기관",
            "service_name": "주거급여 지원",
            "basis": {"법령": "주거급여법(제5조, 제1항)"},
            "criteria": {"선정기준": "4인 가구 소득 3,117,474원 이하"},
            "url": "https://www.gov.kr",
        }

    def test_requires_exact_parent_law_and_operational_criteria(self):
        idx = index_program_references([self.program])
        leads = numeric_standard_leads(self.doc, self.comparison, idx,
                                       "comparison_incomplete")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["status"],
                         "program_link_candidate_requires_operational_proof")
        self.assertEqual(leads[0]["before"], "3,117,474")
        self.assertEqual(leads[0]["after"], "3,326,345")
        self.assertEqual(len(leads[0]["affected_values"]), 1)

    def test_other_law_never_matches_numeric_coincidence(self):
        unrelated = {**self.program,
                     "basis": {"법령": "전혀 다른 법(제5조, 제1항)"}}
        idx = index_program_references([unrelated])
        self.assertEqual(numeric_standard_leads(
            self.doc, self.comparison, idx, "comparison_incomplete"), [])

    def test_exact_parent_title_and_old_amount_yield_review_only(self):
        source = {**self.program,
                  "basis": {"법령": "주거급여법(제0조의0, 제0항)"}}
        idx = index_program_references([source])
        self.assertEqual(len(idx), 0)
        leads = numeric_standard_leads(self.doc, self.comparison, idx,
                                       "official_comparison_verified", [source])
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["status"],
                         "program_link_candidate_requires_operational_proof")
        self.assertEqual(leads[0]["evidence"]["old_value"], "3,117,474")

    def test_parent_law_title_only_never_creates_a_lead(self):
        source = {**self.program,
                  "basis": {"법령": "주거급여법(제0조의0, 제0항)"},
                  "criteria": {"선정기준": "주거급여 선정대상"}}
        self.assertEqual(numeric_standard_leads(
            self.doc, self.comparison, index_program_references([source]),
            "comparison_incomplete", [source]), [])

    def test_unverified_annex_sha_never_matches(self):
        self.comparison["numeric_changes"][0]["new_attachment_sha256"] = ""
        idx = index_program_references([self.program])
        self.assertEqual(numeric_standard_leads(
            self.doc, self.comparison, idx, "comparison_incomplete"), [])


if __name__ == "__main__":
    unittest.main()
