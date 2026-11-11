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

    def test_unrelated_table_headers_are_not_forced_into_diff(self):
        old=extract_tables("공식 표:\n구 분 | 1인가구\n금액 | 100\n","a")
        new=extract_tables("공식 표:\n구 분 | 2인가구\n금액 | 200\n","b")
        self.assertEqual(compare_tables(old,new),[])
