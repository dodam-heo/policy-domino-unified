"""Auditable end-to-end regression ledger, separate from collector targeting.

Three annual standards are TEST CASES ONLY. The collection engine never
uses their titles, ministries, document serials or amounts as source targets.
General coverage also samples unrelated official documents by stable hash.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
from .engine import ident, load, hash256, relative_path
from .verification import OFFICIAL, source_grade

REGRESSIONS = (
    ("2027년도 기준 중위소득·생계·의료급여", "2100000283464"),
    ("2027년도 주거급여 선정기준", "2100000284670"),
    ("2027년도 교육급여 선정기준", "2100000285242"),
)


def evaluate(root: Path, site: Path | None = None) -> dict:
    documents = {}
    for path in (root/"documents").glob("*/*/*.json.gz"):
        package = load(path, {})
        row = package.get("record") or {}
        if all(row.get(key) for key in ("source", "stable_id", "serial")):
            documents[row["serial"]] = package
    indexed_serials = set()
    for path in (root/"indexes").rglob("*.json.gz"):
        for row in load(path, {}).get("records", []):
            if row.get("serial"):
                indexed_serials.add(str(row["serial"]))
    comparisons = {}
    for path in (root/"comparisons").glob("*.json.gz"):
        comp = load(path, {})
        rec = comp.get("changed_record") or {}
        if rec.get("serial"):
            comparisons[str(rec["serial"])] = comp
    catalog = load(site/"data.json", {}) if site else {}
    events = {entry.get("id"): entry for entry in catalog.get("events", [])}
    cases = []
    for name, serial in REGRESSIONS:
        package = documents.get(serial, {})
        record = package.get("record") or {}
        comparison = comparisons.get(serial, {})
        event = events.get(ident(record), {}) if record else {}
        extracted = source_grade(package)
        linked = bool(event.get("action_count", 0))
        stages = {
            "indexed": serial in indexed_serials,
            "original_saved": bool(package),
            "official_original_verified": extracted == OFFICIAL,
            "comparison_exists": bool(comparison),
            "official_comparison_verified":
                event.get("verification") == "official_comparison_verified",
            "institutional_action_verified": linked,
            "published": bool(event),
        }
        case = {"name": name, "official_serial": serial, "stages": stages,
                "source_title": record.get("title", ""),
                "source_url": record.get("url", ""),
                "comparison_status": comparison.get("status", "not_evaluated"),
                "missing_steps": [key for key, yes in stages.items() if not yes]}
        cases.append(case)
    samples = []
    for serial, package in sorted(documents.items(),
                                  key=lambda row: hash256(row[0])):
        record = package["record"]
        source = record.get("source", "")
        if sum(1 for row in samples if row["source"] == source) >= 3:
            continue
        samples.append({"source": source, "serial": serial,
                        "title": record.get("title", ""),
                        "verification": source_grade(package)})
    complete = all(not row["missing_steps"] for row in cases)
    return {"schema": "policy-domino-acceptance-v1",
            "criteria": "source index → verified original → verified comparison → verified public agency action → publication",
            "required_examples": cases,
            "unrelated_source_samples": samples,
            "ready_for_final_release": complete,
            "failure_count": sum(len(row["missing_steps"]) for row in cases)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--site", type=Path)
    p.add_argument("--output", type=Path, default=Path("site/acceptance.json"))
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    result = evaluate(args.root, args.site)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(json.dumps({"ready": result["ready_for_final_release"],
                      "failures": result["failure_count"],
                      "missing_by_example": [
                          (c["name"], c["missing_steps"])
                          for c in result["required_examples"]]}, ensure_ascii=False))
    if args.strict and not result["ready_for_final_release"]:
        raise SystemExit("RELEASE_GATE_FAILED: required source-grounded workflow unfinished")


if __name__ == "__main__":
    main()
