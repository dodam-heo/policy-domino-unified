from pathlib import Path
import unittest


class SiteContractTest(unittest.TestCase):
    def test_no_fake_completed_operational_status_or_v2_ui(self):
        html = Path("site/index.html").read_text("utf8")
        js = Path("site/app.js").read_text("utf8")
        self.assertIn("정책 변경 목록", html)
        self.assertIn("영향받는 공공기관", js)
        self.assertIn("실제 변경사항 · 신구 비교", js)
        self.assertIn("기관명 필터", js)
        self.assertIn("공식 신구 검증", js)
        self.assertNotIn("반영 완료", html)
        self.assertNotIn("v2/index.html", html)
