import unittest
from unittest.mock import patch
from unified.impact import collect_programs, impact_for, proof
from unified.ai import verify, UnverifiedAnalysis


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.doc = {"title": "공공서비스 규정", "url": "https://www.law.go.kr",
                    "stable_id": "1", "serial": "2"}
        self.change = {"clause": "제3조", "before": "지원 기준은 100원으로 한다.",
                       "after": "지원 기준은 120원으로 한다."}
        self.program = {"id": "svc01", "agency": "실제공공기관",
                        "agency_type": "공공기관", "service_name": "공공지원사업",
                        "url": "https://www.gov.kr",
                        "basis": {"법령": "「공공서비스 규정」 제3조"},
                        "criteria": {"선정기준": "100원 기준을 심사에 적용"}}
    def test_exact_article_citation_and_old_value(self):
        proofed = proof(self.program, self.doc, self.change)
        self.assertTrue(proofed["numeric_value_in_operating_criteria"])
        self.assertEqual(proofed["new_value"], "120원")
    def test_title_only_does_not_prove_impact(self):
        self.program["basis"]["법령"] = "공공서비스 규정"
        self.assertIsNone(proof(self.program, self.doc, self.change))
    def test_changed_article_only(self):
        rows = impact_for(self.doc, {"status": "changed", "changes": [self.change]}, [self.program])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["agency"], "실제공공기관")
    def test_impact_only_checks_programs_citing_changed_article(self):
        unrelated = [{**self.program,
                      "id": f"other-{i}",
                      "basis": {"법령": "「다른 법률」 제3조"}}
                     for i in range(100)]
        with patch("unified.impact.proof", wraps=proof) as candidate_proof:
            rows = impact_for(
                self.doc, {"status": "changed", "changes": [self.change]},
                unrelated + [self.program])
        self.assertEqual(len(rows), 1)
        self.assertEqual(candidate_proof.call_count, 1)

    def test_ai_must_quote_original(self):
        impact = {"before": "100원", "after": "120원",
                  "evidence": {"service_quote": "100원 기준"}}
        good = {"old_quote": "100원", "new_quote": "120원",
                "program_quote": "100원", "explanation": "표준값 변경 검토"}
        self.assertTrue(verify(good, impact)["verified"])
        bad = {**good, "new_quote": "900원"}
        with self.assertRaises(UnverifiedAnalysis):
            verify(bad, impact)


if __name__ == "__main__":
    unittest.main()
