"""Publish versioned, source-grounded policy events as an incremental static site.

Small list JSON + one detail JSON per official document version. The browser
must not assume that a previously extracted text is official-source verified.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from .engine import ident, load, save_json, hash256
from .verification import (comparison_grade, quality_report,
                           source_grade, OFFICIAL)

AREAS = (
    ("복지·소득", r"중위소득|생계급여|의료급여|기초생활|사회보장|복지|연금|수급"),
    ("교육·장학", r"교육급여|장학|학교|대학|교육|학자금|교원"),
    ("주거·국토", r"주거급여|주택|임대|국토|토지|도시|건축|청약"),
    ("금융·보험", r"예금|금융|은행|보험|대출|신용|투자"),
    ("보건·의료", r"의료|보건|진료|병원|건강|약제|질병"),
    ("환경·에너지", r"환경|폐기물|기후|탄소|에너지|전력|수질|대기"),
    ("조세·재정", r"조세|세율|관세|세금|부담금|예산|재정|보조금"),
    ("노동·인사", r"근로|임금|고용|노동|직급|인사|공무원|산재"),
    ("산업·조달", r"산업|기업|조달|입찰|계약|중소기업|농업|수산"),
    ("안전·사법", r"안전|재난|소방|경찰|형사|법원|치안|국방"),
    ("정보·통신", r"정보화|정보통신|데이터|전산|개인정보|통신|방송"),
    ("조직·행정", r"직제|조직|정원|행정절차|행정기관|사무분장"),
)
REGEX_AREAS = [(name, re.compile(pattern)) for name, pattern in AREAS]
SOURCE_NAMES = {"law": "법령", "admrul": "행정규칙", "ordin": "자치법규"}


def classify(doc: dict, changes: list[dict]) -> tuple[str, str]:
    # The subject classification is an explainable *navigation aid*, not an
    # official government taxonomy; source kind is always kept separately.
    title = doc.get("title", "")
    for name, pattern in REGEX_AREAS:
        if pattern.search(title):
            return name, "policy_title_text_rule"
    excerpt = " ".join((c.get("before", "")+" "+c.get("after", ""))[:500]
                       for c in changes[:4])
    for name, pattern in REGEX_AREAS:
        if pattern.search(excerpt):
            return name, "verified_excerpt_text_rule"
    return "분야 미확정", "not_verified"


def kind_of(doc: dict) -> str:
    revision = str(doc.get("revision") or "").replace(" ", "")
    if "폐지" in revision or "폐기" in revision:
        return "repealed"
    if "제정" in revision:
        return "new"
    if "개정" in revision or "수정" in revision:
        return "amended"
    return "unclassified"


def detail_path(event_id: str) -> str:
    return "details/" + hash256(event_id)[:24] + ".json"


def assemble(root: Path, limit: int = 1200) -> dict:
    versions = {}
    documents = []
    for path in (root/"documents").glob("*/*/*.json.gz"):
        package = load(path, {})
        doc = package.get("record") or {}
        if not all(doc.get(k) for k in ("source", "stable_id", "serial", "title")):
            continue
        versions[ident(doc)] = package
        documents.append(doc)
    documents.sort(key=lambda v: (v.get("published_at", ""), v.get("serial", "")),
                   reverse=True)
    comparisons = {}
    for path in (root/"comparisons").glob("*.json.gz"):
        c = load(path, {})
        row = c.get("changed_record") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            comparisons[ident(row)] = c
    impacts = {}
    regulations = {}
    for path in (root/"impacts").glob("*.json.gz"):
        payload = load(path, {})
        row = payload.get("doc") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            impacts[ident(row)] = payload.get("institutional_actions", [])
            regulations[ident(row)] = payload.get("related_regulations", [])
    events = []
    for doc in documents[:limit]:
        key = ident(doc)
        comp = comparisons.get(key, {})
        changes = comp.get("changes", [])
        old = comp.get("prior_record") or {}
        old_package = versions.get(ident(old), {}) if all(old.get(k) for k in
            ("source", "stable_id", "serial")) else {}
        present_package = versions[key]
        source_status = source_grade(present_package)
        comparison_status = comp.get("status", "original_saved_comparison_pending")
        verification = comparison_grade(comparison_status,
                                        old_package, present_package)
        category, category_reason = classify(doc, changes)
        actions = impacts.get(key, [])
        before_after = [{
            "article": c.get("clause", ""), "before": c.get("before", "")[:15000],
            "after": c.get("after", "")[:15000],
            "verification": verification,
        } for c in changes[:80]]
        row = {
            "id": key, "title": doc.get("title", ""),
            "source": doc.get("source", ""),
            "source_kind": SOURCE_NAMES.get(doc.get("source", ""), "기타"),
            "kind": doc.get("kind", ""),
            "ministry": doc.get("ministry", ""),
            "published_at": doc.get("published_at", ""),
            "effective_date": doc.get("effective_date", ""),
            "revision": doc.get("revision", ""),
            "change_type": kind_of(doc),
            "number": doc.get("number", ""),
            "url": doc.get("url", ""),
            "category": category,
            "category_basis": category_reason,
            "source_grade": source_status,
            "verification": verification,
            "comparison_status": comparison_status,
            "relationship": comp.get("relationship", ""),
            "change_count": len(changes),
            "changes": before_after,
            "unresolved": comp.get("unresolved", [])[:40],
            "institutions": actions,
            "related_regulations": regulations.get(key, []),
            "linked_regulation_count": len(regulations.get(key, [])),
            "institution_count": len({a.get("agency") for a in actions if a.get("agency")}),
            "action_count": sum(a.get("status") == "review_of_verified_citation"
                                for a in actions),
            "details_path": detail_path(key),
            "prior_url": old.get("url", ""),
            "source_documents": [
                {"title": old.get("title", ""), "url": old.get("url", ""),
                 "id": ident(old) if old.get("source") else "",
                 "verification": source_grade(old_package)},
                {"title": doc.get("title", ""), "url": doc.get("url", ""),
                 "id": key, "verification": source_status},
            ],
        }
        events.append(row)
    report = {
        "schema": "policy-domino-unified-ui-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "independently sourced document versions; verified event impact is explicitly distinguished from review leads",
        "total_source_versions_saved": len(documents),
        "events": events,
        "summary": {
            "displayed_events": len(events),
            "with_source_changes": sum(e["change_count"] > 0 for e in events),
            "with_verified_changes": sum(e["change_count"] > 0 and
                e["verification"] == "official_comparison_verified" for e in events),
            "with_institutional_actions": sum(e["action_count"] > 0 for e in events),
            "agency_action_count": sum(e["action_count"] for e in events),
            "by_category": dict(Counter(e["category"] for e in events)),
        },
    }
    archived = load(root/"legacy-index-status.json", {})
    ledger = load(root/"collection-state.json", {})
    index_windows = len(list((root/"indexes").glob("*/*.json.gz")))
    report["quality"] = quality_report(events, ledger, indexed=index_windows)
    report["quality"]["historic_index_versions"] = archived.get("unique_official_versions", 0)
    return report


INDEX_KEYS = (
    "id", "title", "source", "source_kind", "kind", "ministry",
    "published_at", "effective_date", "revision", "change_type", "number",
    "category", "category_basis", "comparison_status", "verification",
    "source_grade", "relationship", "change_count", "institution_count",
    "action_count", "details_path", "linked_regulation_count",
)


def write_site(payload: dict, output: Path) -> dict:
    folder = output.parent/"details"
    folder.mkdir(parents=True, exist_ok=True)
    retained = set()
    small = []
    for event in payload["events"]:
        path = output.parent/event["details_path"]
        save_json(path, {"schema": "policy-domino-unified-detail-v2", **event})
        retained.add(path.name)
        small.append({key: event.get(key) for key in INDEX_KEYS})
    for previous in folder.glob("*.json"):
        if previous.name not in retained:
            previous.unlink()
    index = {key: value for key, value in payload.items() if key != "events"}
    index["events"] = small
    save_json(output, index)
    return index


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--output", type=Path, default=Path("site/data.json"))
    args = p.parse_args()
    payload = assemble(args.root)
    write_site(payload, args.output)
    print(json.dumps({**payload["summary"],
                      "quality": payload["quality"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
