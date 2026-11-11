import tempfile
import unittest
from pathlib import Path
from unified.acceptance import evaluate


class AcceptanceTests(unittest.TestCase):
    def test_fail_closed_when_required_examples_missing(self):
        with tempfile.TemporaryDirectory() as d:
            result=evaluate(Path(d))
            self.assertFalse(result["ready_for_final_release"])
            self.assertEqual(len(result["required_examples"]),3)
            for item in result["required_examples"]:
                self.assertIn("official_original_verified",item["missing_steps"])
                self.assertIn("institutional_action_verified",item["missing_steps"])
