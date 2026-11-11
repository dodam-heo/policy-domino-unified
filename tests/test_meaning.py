import unittest
from unified.meaning import focused_change, headline


class MeaningTests(unittest.TestCase):
    def test_focus_is_real_text_not_generated_claim(self):
        a = "종전 내용 " * 100 + "선정기준은 100원" + " 동일 내용" * 100
        b = "종전 내용 " * 100 + "선정기준은 120원" + " 동일 내용" * 100
        pair = focused_change(a, b)
        self.assertIn("100원", pair["before"])
        self.assertIn("120원", pair["after"])
        self.assertNotIn("200", pair["new_added"])

    def test_flattened_annex_border_does_not_become_headline(self):
        before = "┌────────┬──────┐ 기준 100원 └────────┴──────┘"
        after = "┌────────┬──────┐ 기준 120원 └────────┴──────┘"
        value = headline([{"clause":"별표 1","before":before,"after":after}],
                         "historical_comparison_needs_revalidation")
        self.assertIn("표·서식", value)
        self.assertNotIn("┌", value)
        self.assertTrue(value.startswith("원문 재검증 필요"))

    def test_uncertain_excerpt_not_labelled_verified(self):
        changes = [{"clause": "제1조", "before": "100원", "after": "120원"}]
        self.assertTrue(headline(changes, "comparison_incomplete").startswith(
            "원문 재검증 필요"))
        self.assertIn("100원", headline(changes, "official_comparison_verified"))
