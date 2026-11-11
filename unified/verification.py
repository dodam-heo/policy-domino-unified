"""Evidence grades: historic extracted text is NOT official-source-complete.
The grades travel through analysis, publication and human-readable health reports.
"""
from __future__ import annotations
import base64
import binascii
import hashlib
import json
import xml.etree.ElementTree as ET

OFFICIAL = "official_original_verified"
LEGACY = "legacy_extract_needs_revalidation"
PARTIAL = "partial_or_missing_original"


def source_grade(package: dict) -> str:
    body = package.get("body") or {}
    provenance = package.get("source_snapshot_provenance") or {}
    if provenance or body.get("status") == "legacy_extracted":
        return LEGACY
    if (body.get("status") == "complete" and
            package.get("official_xml_base64") and
            body.get("raw_xml_sha256") and
            not body.get("unresolved_attachments") and
            not body.get("incomplete_keys")):
        try:
            raw = base64.b64decode(package["official_xml_base64"], validate=True)
            if hashlib.sha256(raw).hexdigest() != body["raw_xml_sha256"]:
                return PARTIAL
            ET.fromstring(raw)
            clauses = body.get("clauses") or {}
            expected = hashlib.sha256(json.dumps(
                clauses, ensure_ascii=False, sort_keys=True).encode("utf8")).hexdigest()
            if body.get("body_sha256") and expected != body["body_sha256"]:
                return PARTIAL
            return OFFICIAL
        except (ValueError, TypeError, ET.ParseError, binascii.Error):
            return PARTIAL
    return PARTIAL


def comparison_grade(status: str, prior: dict, changed: dict) -> str:
    if status not in ("changed", "no_text_change"):
        return "comparison_incomplete"
    if source_grade(prior) != OFFICIAL or source_grade(changed) != OFFICIAL:
        return "historical_comparison_needs_revalidation"
    return "official_comparison_verified"


def quality_report(events: list[dict], collector: dict, *,
                   indexed: int = 0) -> dict:
    grades = {}
    for item in events:
        grade = item.get("verification", "not_classified")
        grades[grade] = grades.get(grade, 0) + 1
    failures = [x for x in (collector.get("coverage") or {}).values()
                if isinstance(x, dict) and x.get("complete") is not True]
    return {
        "source_versions_displayed": len(events),
        "persisted_official_index_windows": indexed,
        "comparison_grades": grades,
        "failed_collection_windows": len(failures),
        "latest_collection": collector.get("last_run_stats", {}),
        "last_collection_date": collector.get("last_run", ""),
        "publication_can_claim_collection_complete": not failures and
            bool(collector.get("last_run_stats", {}).get("complete_originals_added")),
        "status": "collection_incomplete" if failures else "collection_window_checked",
    }
