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

    def test_uncertain_excerpt_not_labelled_verified(self):
        changes = [{"clause": "제1조", "before": "100원", "after": "120원"}]
        self.assertTrue(headline(changes, "comparison_incomplete").startswith(
            "원문 재검증 필요"))
        self.assertIn("100원", headline(changes, "official_comparison_verified"))
