import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unified.engine import verified_window, run


class DeadlineTests(unittest.TestCase):
    def test_expired_deadline_does_not_call_official_api(self):
        class Never:
            def search(self,*args,**kwargs):
                raise AssertionError("deadline should preempt official fetch")
        with patch("unified.engine.time.monotonic",return_value=20):
            rows,summary=verified_window(
                Never(),"admrul","2026-11-01","2026-11-02",
                "1","3",deadline=10)
        self.assertEqual(rows,[])
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["error"],"collection_time_budget_deferred")
