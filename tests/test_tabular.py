import unittest
from unified.tabular import extract_tables,compare_tables


class TabularTests(unittest.TestCase):
    def test_preserve_exact_household_column_and_price(self):
        old=extract_tables("공식 표:\n구 분 | 1인가구 | 4인가구\n금액(원/월) | 100 | 200\n","a")
        new=extract_tables("공식 표:\n구 분 | 1인가구 | 4인가구\n금액(원/월) | 100 | 230\n","b")
        changes=compare_tables(old,new)
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["column"],"4인가구")
        self.assertEqual(changes[0]["before"],"200")
        self.assertEqual(changes[0]["after"],"230")
        self.assertEqual(changes[0]["verification"],"official_hwpx_cell_pair")

    def test_same_ordinal_from_separate_attachments_does_not_override(self):
        original=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 100 | 200\n","a")
        unrelated=extract_tables(
            "공식 표:\n구 분 | 6인가구 | 7인가구\n금액 | 500 | 600\n","b")
        revised=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 100 | 230\n","c")
        results=compare_tables(original+unrelated,revised)
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]["before"],"200")
        self.assertEqual(results[0]["after"],"230")
        self.assertEqual(results[0]["old_attachment_sha256"],"a")

    def test_column_reordering_is_not_lost(self):
        old=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 100 | 200\n","a")
        new=extract_tables(
            "공식 표:\n구 분 | 4인가구 | 1인가구\n금액 | 230 | 100\n","b")
        results=compare_tables(old,new)
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]["column"],"4인가구")
        self.assertEqual(results[0]["after"],"230")

    def test_ambiguous_duplicate_table_is_not_paired(self):
        first=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 100 | 200\n","a")
        second=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 140 | 280\n","b")
        now=extract_tables(
            "공식 표:\n구 분 | 1인가구 | 4인가구\n금액 | 150 | 300\n","c")
        self.assertEqual(compare_tables(first+second,now),[])

    def test_unrelated_table_headers_are_not_forced_into_diff(self):
        old=extract_tables("공식 표:\n구 분 | 1인가구\n금액 | 100\n","a")
        new=extract_tables("공식 표:\n구 분 | 2인가구\n금액 | 200\n","b")
        self.assertEqual(compare_tables(old,new),[])
