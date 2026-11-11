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

    def test_official_hwpx_amount_beats_image_placeholder(self):
        c = [{"clause": "본문 1",
              "before": '<img id="159311793"/>', "after": '<img id="169491527"/>'}]
        numeric = [{"column": "4인 가구", "row": "금액 (원/월)",
                    "before": "3,117,474", "after": "3,326,345",
                    "verification": "official_hwpx_cell_pair"}]
        result = headline(c, "comparison_incomplete", numeric)
        self.assertIn("3,117,474", result)
        self.assertIn("3,326,345", result)
        self.assertNotIn("img", result)
        self.assertIn("재검증", result)

    def test_img_markup_is_not_reported_as_substantive_change(self):
        result = headline([{"clause": "본문", "before": '<img id="7"/>',
                           "after": '<img id="9"/>'}], "comparison_incomplete")
        self.assertIn("첨부자료 대조 필요", result)
        self.assertNotIn('id="', result)

    def test_uncertain_excerpt_not_labelled_verified(self):
        changes = [{"clause": "제1조", "before": "100원", "after": "120원"}]
        self.assertTrue(headline(changes, "comparison_incomplete").startswith(
            "원문 재검증 필요"))
        self.assertIn("100원", headline(changes, "official_comparison_verified"))
