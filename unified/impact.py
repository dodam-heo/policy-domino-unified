"""Evidence-gated impact identification from public-program operating records.

Only official provider names, operating criteria and exact legal evidence form
an institutional action; literal policy title overlap alone is never enough.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re

from .engine import hash256, clean, load, store, save_json, relative_path, ident
from .relations import legal_dependents, index_program_references, two_hop_program_leads
from .verification import comparison_grade

REFERENCES = re.compile(r"「([^」]{2,180})」\s*(제\s*\d+\s*조(?:의\s*\d+)?)?")
ARTICLE = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?")
NUMBERS = re.compile(r"(?<![\d,])\d[\d,]*(?:\.\d+)?\s*(?:만\s*원|원|%|명|개월)")
CRITERIA_FIELDS = ("선정기준", "지원대상", "지원내용", "신청기한", "구비서류")
BASIS_FIELDS = ("법령", "행정규칙", "자치법규")


def collect_programs(catalog: dict) -> list[dict]:
    raw = catalog.get("services") or {}
    entries = raw.values() if isinstance(raw, dict) else raw
    found = {}
    for r in entries:
        if not isinstance(r, dict):
            continue
        sid = clean(r.get("id") or r.get("서비스ID"))
        agency = clean(r.get("agency") or r.get("소관기관명"))
        name = clean(r.get("title") or r.get("서비스명"))
        agency_type = clean(r.get("agency_type") or r.get("소관기관유형"))
        if not sid or not agency or not name or "민간" in agency_type:
            continue
        detail = r.get("detail") or {}
        criteria = {k: clean(detail.get({
            "선정기준": "criteria", "지원대상": "eligible"}.get(k, "")) or
                              r.get({"선정기준": "criteria",
                                     "지원대상": "eligible",
                                     "지원내용": "benefits"}.get(k, "")) or
                              detail.get(k) or r.get(k))[:5000]
                    for k in CRITERIA_FIELDS}
        basis = {k: clean(detail.get({"법령": "laws", "행정규칙": "rules",
                                      "자치법규": "ordinances"}[k]) or r.get(k))[:5000]
                 for k in BASIS_FIELDS}
        if not any(criteria.values()) or not any(basis.values()):
            continue
        url = clean(r.get("detail_url") or r.get("상세조회URL"))
        if not url.startswith("https://"):
            url = "https://www.data.go.kr/data/15113968/openapi.do"
        found[sid] = {
            "id": sid, "agency": agency, "agency_type": agency_type,
            "service_name": name, "url": url,
            "criteria": criteria, "basis": basis,
            "origin": "official_gov24_public_service_catalog",
        }
    return list(found.values())


def import_catalog(root: Path, source: Path) -> dict:
    raw = json.loads(source.read_text("utf8"))
    if not isinstance(raw, dict):
        raise ValueError("Official public-service source must be an object")
    programs = collect_programs(raw)
    shards = {}
    for row in programs:
        key = hash256(row["id"])[:2]
        shards.setdefault(key, []).append(row)
    updated = 0
    for shard, records in shards.items():
        records.sort(key=lambda r: r["id"])
        updated += int(store(root / "programs" / (shard+".json.gz"),
                             {"source": "gov24", "records": records}))
    summary = {"official_services_indexed": len(programs),
               "shards": len(shards), "shards_changed": updated,
               "source": "gov24", "source_snapshot_hash": hash256(source.read_bytes())}
    save_json(root / "program-import.json", summary)
    return summary


def read_programs(root: Path):
    for source in sorted((root / "programs").glob("*.json.gz")):
        for row in load(source, {}).get("records", []):
            yield row


def plain(text):
    return clean(text).replace(" ", "")


def proof(program: dict, doc: dict, change: dict) -> dict | None:
    """Exact law+changed article in official program legal basis is required."""
    title, clause = doc.get("title", ""), change.get("clause", "")
    if not title or not clause:
        return None
    expected_title, expected_article = plain(title), plain(clause)
    basis = " ".join(program["basis"].values())
    # An explicit reference to the changed article, not just the legal title.
    citations = [(plain(m.group(1)), plain(m.group(2)), m.group(0))
                 for m in REFERENCES.finditer(basis)]
    exact = [quote for ref_title, ref_article, quote in citations
             if ref_title == expected_title and ref_article == expected_article]
    # Old/new must be complete, different and retained from official bodies.
    old, new = change.get("before", ""), change.get("after", "")
    if not exact or not old or not new or old == new:
        return None
    relevant = [(k, v) for k, v in program["criteria"].items() if v]
    if not relevant:
        return None
    field, source_text = relevant[0]
    old_figures = set(NUMBERS.findall(old))
    new_figures = set(NUMBERS.findall(new))
    removed = sorted(old_figures-new_figures)
    added = sorted(new_figures-old_figures)
    # No number-only join. Numerical suggestions require the exact citation
    # above AND the actual old value in the service operating criteria.
    numeric = (len(removed) == 1 and len(added) == 1 and
               any(removed[0] in val for _, val in relevant))
    matched = next(((k, val) for k, val in relevant if numeric and removed[0] in val),
                   (field, source_text))
    return {
        "proof_type": "exact_changed_article_cited_by_official_program",
        "reference_quote": exact[0],
        "service_field": matched[0],
        "service_quote": matched[1][:1200],
        "old_value": removed[0] if numeric else "",
        "new_value": added[0] if numeric else "",
        "numeric_value_in_operating_criteria": numeric,
    }


def impact_for(doc: dict, comparison: dict, programs: list[dict]) -> list[dict]:
    if comparison.get("status") not in ("changed", "partial_unverified"):
        return []
    if not comparison.get("changes"):
        return []
    results = []
    for change in comparison["changes"]:
        for p in programs:
            evidence = proof(p, doc, change)
            if evidence is None:
                continue
            field = evidence["service_field"]
            if evidence["numeric_value_in_operating_criteria"]:
                action = (field + "에 기재된 종전 " + evidence["old_value"] +
                          "을 새 공식 기준 " + evidence["new_value"] +
                          "과 대조하고, 관련 안내·심사 산식을 변경된 기준에 맞게 검토")
            else:
                action = (field + "에서 인용한 " + change["clause"] +
                          "의 개정 문구를 확인하고 사업의 해당 처리기준·안내·심사 절차에 반영할 항목 검토")
            results.append({
                "agency": p["agency"], "agency_type": p["agency_type"],
                "service": p["service_name"], "service_id": p["id"],
                "service_url": p["url"], "policy_url": doc.get("url", ""),
                "policy": doc["title"], "changed_clause": change["clause"],
                "required_change": action,
                "before": change["before"], "after": change["after"],
                "evidence": evidence,
                "status": "review_of_verified_citation",
                # This IS NOT a claim that the institution has/has not acted.
            })
    return results


def run(root: Path, limit_events: int = 300) -> dict:
    programs = list(read_programs(root))
    generated = []
    statuses = Counter()
    ai_attempts, ai_verified, ai_errors = 0, 0, 0
    key_available = bool(os.getenv("PD_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
    model_available = bool(os.getenv("PD_LLM_MODEL"))
    ai_budget = max(0, int(os.getenv("PD_LLM_MAX_REQUESTS", "12")))
    files = sorted((root / "comparisons").glob("*.json.gz"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    comparisons = [load(source, {}) for source in files[:limit_events]]
    # Index the changed clauses and official downstream rule bodies ONCE.
    # Direct and two-hop references remain distinct from verified duties.
    relation_graph = legal_dependents(root, comparisons)
    program_refs = index_program_references(programs)
    candidates = 0
    for comparison in comparisons:
        doc = comparison.get("changed_record") or {}
        if not doc:
            continue
        prior = comparison.get("prior_record") or {}
        now_package = load(root/relative_path(doc), {})
        prior_package = load(root/relative_path(prior), {}) if all(
            prior.get(k) for k in ("source", "stable_id", "serial")) else {}
        grade = comparison_grade(comparison.get("status", ""),
                                 prior_package, now_package)
        impacted = impact_for(doc, comparison, programs)
        for action in impacted:
            if grade != "official_comparison_verified":
                action["status"] = "program_link_candidate_requires_source_revalidation"
            elif not action["evidence"].get("numeric_value_in_operating_criteria"):
                action["status"] = "program_link_candidate_requires_operational_proof"
        related = relation_graph.get(ident(doc), [])
        seen = {(a["service_id"], a["changed_clause"]) for a in impacted}
        for lead in two_hop_program_leads(doc, comparison, related, program_refs):
            if (lead["service_id"], lead["changed_clause"]) not in seen:
                impacted.append(lead)
        candidates += sum(a["status"] != "review_of_verified_citation"
                          for a in impacted)
        # AI is an optional explanatory layer AFTER deterministic official
        # linkage; model text cannot create a new agency or evidence edge.
        if key_available and model_available:
            from .ai import analyze
            for action in impacted:
                if action["status"] != "review_of_verified_citation":
                    continue
                fingerprint = hash256(json.dumps(action, ensure_ascii=False, sort_keys=True))
                output = root / "ai" / (fingerprint[:24] + ".json.gz")
                verified = load(output)
                if not verified and ai_attempts < ai_budget:
                    ai_attempts += 1
                    try:
                        verified = analyze(action)
                        if verified:
                            store(output, verified)
                    except Exception:
                        ai_errors += 1
                if verified and verified.get("verified"):
                    action["ai_analysis"] = verified
                    ai_verified += 1
        payload = {"doc": doc, "comparison_status": comparison.get("status"),
                   "comparison_verification": grade,
                   "changes_count": len(comparison.get("changes", [])),
                   "related_regulations": related,
                   "institutional_actions": impacted}
        target = root / "impacts" / (hash256("|".join((
            doc.get("source", ""), doc.get("stable_id", ""),
            doc.get("serial", ""))))[:24] + ".json.gz")
        store(target, payload)
        statuses[comparison.get("status", "")] += 1
        generated.extend(impacted)
    stats = {"official_programs": len(programs), "comparisons_considered": sum(statuses.values()),
             "verified_institutional_tasks": sum(
                 a["status"] == "review_of_verified_citation" for a in generated),
             "program_review_candidates": candidates,
             "related_regulations": sum(len(x) for x in relation_graph.values()),
             "comparison_statuses": dict(statuses),
             "ai_explanation_attempts": ai_attempts,
             "ai_verified_explanations": ai_verified,
             "ai_failures": ai_errors}
    save_json(root / "impact-status.json", stats)
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--catalog", type=Path)
    args = p.parse_args()
    if args.catalog:
        print("IMPORT", json.dumps(import_catalog(args.root, args.catalog), ensure_ascii=False))
    print("IMPACT", json.dumps(run(args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
