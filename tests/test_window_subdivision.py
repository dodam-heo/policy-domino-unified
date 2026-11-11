import unittest
from unified.engine import verified_window


class WindowSubdivisionTests(unittest.TestCase):
    def test_overfull_query_is_split_and_no_rows_are_lost(self):
        class Official:
            calls = []
            def search(self, source, start, end, edition, kind, query=""):
                self.calls.append((start,end))
                if start != end:
                    return [], {"reported": 2001, "collected": 0,
                                "pages": 1, "complete": False,
                                "error": "date_window_split_required"}
                serial = start.replace("-","")
                return [{"source":"admrul","stable_id":"notice",
                         "serial":serial,"title":"임의 정책",
                         "published_at":start}], {
                         "reported":1,"collected":1,"pages":1,"complete":True}
        api=Official()
        rows,info=verified_window(api,"admrul","2026-11-01",
                                  "2026-11-04","1","3")
        self.assertEqual(len(rows),4)
        self.assertEqual(info["reported"],4)
        self.assertTrue(info["complete"])
        self.assertGreater(len(api.calls),4)

    def test_irrecoverable_single_day_is_never_marked_complete(self):
        class Official:
            def search(self,*args,**kwargs):
                return [],{"reported":2001,"collected":0,
                          "pages":20,"complete":False,"error":"pagination_limit"}
        rows,info=verified_window(Official(),"admrul","2026-11-01",
                                  "2026-11-01","1","3")
        self.assertFalse(info["complete"])
