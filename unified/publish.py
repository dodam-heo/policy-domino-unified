"""Generate the single static UI catalog from independent version files.

The UI never calls unofficial data sources and displays only linked official
agency actions actually supported by the rule's changed article evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from .engine import ident, load, save_json

TOPICS = (
    ("급여·지원기준", re.compile(r"급여|지원대상|선정기준|기준 중위소득|소득인정액|보조금|복지")),
    ("행정절차·인허가", re.compile(r"허가|승인|신고|등록|제출|심사|접수|증빙|서식")),
    ("공공재정·요율", re.compile(r"예산|수수료|요율|부담금|세율|재정|공공요금")),
    ("조직·인력", re.compile(r"직제|조직|정원|직급|사무분장|정원규정")),
)


def classify(doc, changes) -> str:
    context = " ".join([doc.get("title", "")] + [
        (x.get("before", "") + " " + x.get("after", ""))[:300]
        for x in changes[:3]])
    for label, pattern in TOPICS:
        if pattern.search(context):
            return label
    return "기타 제·개정"


def assemble(root: Path, limit: int = 1200) -> dict:
    sources = []
    for path in (root / "documents").glob("*/*/*.json.gz"):
        value = load(path, {})
        doc = value.get("record", {})
        if not all(doc.get(k) for k in ("source", "stable_id", "serial", "title")):
            continue
        sources.append(doc)
    sources.sort(key=lambda v: (v.get("published_at", ""), v.get("serial", "")), reverse=True)
    comparisons = {}
    for path in (root / "comparisons").glob("*.json.gz"):
        c = load(path, {})
        row = c.get("changed_record") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            comparisons[ident(row)] = c
    impacts = {}
    for path in (root / "impacts").glob("*.json.gz"):
        payload = load(path, {})
        row = payload.get("doc") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            impacts[ident(row)] = payload.get("institutional_actions", [])
    events = []
    for doc in sources[:limit]:
        key = ident(doc)
        comp = comparisons.get(key, {})
        changes = comp.get("changes", [])
        before_after = [{
            "article": c.get("clause", ""), "before": c.get("before", "")[:15000],
            "after": c.get("after", "")[:15000],
        } for c in changes[:80]]
        candidates = impacts.get(key, [])
        events.append({
            "id": key, "title": doc.get("title", ""),
            "source": doc["source"], "kind": doc.get("kind", ""),
            "ministry": doc.get("ministry", ""), "published_at": doc.get("published_at", ""),
            "effective_date": doc.get("effective_date", ""),
            "revision": doc.get("revision", ""), "url": doc.get("url", ""),
            "category": classify(doc, changes),
            "comparison_status": comp.get("status", "original_saved_comparison_pending"),
            "relationship": comp.get("relationship", ""),
            "changes": before_after,
            "unresolved": comp.get("unresolved", [])[:20],
            "institutions": candidates,
            "prior_url": (comp.get("prior_record") or {}).get("url", ""),
        })
    report = {
        "schema": "policy-domino-unified-ui-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "source-backed version catalog; institutional actions only for exact citation evidence",
        "total_source_versions_saved": len(sources),
        "events": events,
        "summary": {
            "displayed_events": len(events),
            "with_verified_changes": sum(bool(e["changes"]) for e in events),
            "with_institutional_actions": sum(bool(e["institutions"]) for e in events),
            "agency_action_count": sum(len(e["institutions"]) for e in events),
            "by_category": dict(Counter(e["category"] for e in events)),
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("site/data.json"))
    args = parser.parse_args()
    payload = assemble(args.root)
    save_json(args.output, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
