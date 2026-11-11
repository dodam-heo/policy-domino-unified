import unittest
import base64
import hashlib
from unified.verification import (OFFICIAL, LEGACY, PARTIAL, source_grade,
                                  comparison_grade, quality_report)


class VerificationTests(unittest.TestCase):
    def test_archived_text_cannot_be_official_verified(self):
        package = {"body": {"status": "complete", "clauses": {"제1조": "내용"}},
                   "source_snapshot_provenance": {"has_raw_official_xml": False}}
        self.assertEqual(source_grade(package), LEGACY)

    def test_actual_official_xml_required(self):
        raw = b"<root/>"
        package = {"body": {"status": "complete",
                            "raw_xml_sha256": hashlib.sha256(raw).hexdigest()},
                   "official_xml_base64": base64.b64encode(raw).decode()}
        self.assertEqual(source_grade(package), OFFICIAL)
        self.assertEqual(source_grade({"body": package["body"]}), PARTIAL)

    def test_no_legacy_verification_promotion(self):
        old = {"body": {"status": "complete"},
               "source_snapshot_provenance": {"has_raw_official_xml": False}}
        raw = b"<root/>"
        new = {"body": {"status": "complete",
                        "raw_xml_sha256": hashlib.sha256(raw).hexdigest()},
               "official_xml_base64": base64.b64encode(raw).decode()}
        self.assertEqual(comparison_grade("changed", old, new),
                         "historical_comparison_needs_revalidation")
        self.assertEqual(comparison_grade("changed", new, new),
                         "official_comparison_verified")

    def test_collection_failures_not_represented_as_current(self):
        row = quality_report([], {"coverage": {"x": {"complete": False}},
                                 "last_run_stats": {"complete_originals_added": 0}})
        self.assertEqual(row["failed_collection_windows"], 1)
        self.assertFalse(row["publication_can_claim_collection_complete"])
