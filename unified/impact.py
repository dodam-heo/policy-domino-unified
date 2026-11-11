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
from .relations import legal_dependents, index_program_references, two_hop_program_leads, references, changed_paragraph_numbers
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
    basis = "||".join(v for v in program["basis"].values() if v)
    paragraphs = changed_paragraph_numbers(change.get("before", ""), change.get("after", ""))
    exact = [ref["excerpt"] for ref in references(basis)
             if plain(ref["title"]) == expected_title and plain(ref["article"]) == expected_article
             and (ref.get("paragraph") is None or
                  (paragraphs is not None and ref["paragraph"] in paragraphs))]
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


def impact_for(doc: dict, comparison: dict, programs: list[dict],
               program_index: dict | None = None) -> list[dict]:
    if comparison.get("status") not in ("changed", "partial_unverified"):
        return []
    if not comparison.get("changes"):
        return []
    # Reuse the exact legal-basis inverted index instead of testing every
    # one of ~10k public services against each changed clause. This keeps
    # the original proof gate, but reduces work to cited candidates only.
    lookup = program_index if program_index is not None else index_program_references(programs)
    results = []
    for change in comparison["changes"]:
        key = (plain(doc.get("title", "")), plain(change.get("clause", "")))
        for p in lookup.get(key, []):
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



def numeric_standard_leads(doc: dict, comparison: dict, program_index: dict,
                           grade: str) -> list[dict]:
    """Match official changed HWPX cells to documented program legal bases.

    Matching an amount or a title by itself never establishes an institution.
    Partial sources yield review candidates, not verified agency directives.
    """
    cells = [c for c in comparison.get("numeric_changes", [])
             if c.get("verification") == "official_hwpx_cell_pair"
             and c.get("before") and c.get("after")
             and c["before"] != c["after"]
             and c.get("old_attachment_sha256")
             and c.get("new_attachment_sha256")]
    if not cells:
        return []
    parents = {}
    for change in comparison.get("changes", []):
        passage = str(change.get("after") or "") + "\n" + str(change.get("before") or "")
        for ref in references(passage):
            if ref.get("operational"):
                parents[(plain(ref["title"]), plain(ref["article"]),
                         ref.get("paragraph"))] = ref
    if not parents:
        return []
    title_words = set()
    for word in re.findall(r"[가-힣]{3,}", str(doc.get("title", ""))):
        term = word.rstrip("의을를은는")
        if len(term) >= 3 and term not in {
                "선정기준", "최저보장수준", "일부개정", "시행규칙",
                "시행령", "법률", "행정규칙", "고시"}:
            title_words.add(term)
    def values(text):
        return {re.sub(r"\D", "", value) for value in re.findall(
            r"(?<!\d)\d[\d,]*(?!\d)", str(text or ""))
            if len(re.sub(r"\D", "", value)) >= 4}
    result = {}
    for (parent_title, parent_article, paragraph), ref in parents.items():
        for program in program_index.get((parent_title, parent_article), []):
            if not all(program.get(k) for k in ("id", "agency", "service_name")):
                continue
            basis = "||".join(str(v) for v in program.get("basis", {}).values() if v)
            links = [b for b in references(basis)
                     if plain(b["title"]) == parent_title
                     and plain(b["article"]) == parent_article
                     and (paragraph is None or b.get("paragraph") is None
                          or b["paragraph"] == paragraph)]
            if not links:
                continue
            criteria = " ".join(str(v) for v in program.get("criteria", {}).values() if v)
            if not criteria:
                continue
            nums = values(criteria)
            matched = [c for c in cells if values(c["before"]) & nums]
            subject = program["service_name"] + " " + criteria
            if not matched and not any(term in subject for term in title_words):
                continue
            if not matched and not re.search(r"선정|기준|산정|지급|소득|금액|급여", criteria):
                continue
            selected = matched or cells
            first = selected[0]
            verified = grade == "official_comparison_verified" and bool(matched)
            if program["id"] in result:
                continue
            result[program["id"]] = {
                "agency": program["agency"],
                "agency_type": program.get("agency_type", ""),
                "service": program["service_name"],
                "service_id": program["id"],
                "service_url": program.get("url", ""),
                "policy_url": doc.get("url", ""),
                "policy": doc.get("title", ""),
                "changed_clause": "공식 첨부 기준표",
                "before": first["before"], "after": first["after"],
                "affected_values": [{
                    "table": c.get("table"), "row": c.get("row", ""),
                    "column": c.get("column", ""),
                    "before": c["before"], "after": c["after"],
                } for c in selected[:24]],
                "required_change": (
                    "공식 기준표 " + str(len(selected)) + "개 행·열의 금액 변경을 "
                    "해당 사업의 선정·심사 기준 및 안내와 대조하여 적용 금액과 "
                    "시행시점을 검토"),
                "evidence": {
                    "proof_type": ("official_hwpx_cell_parent_law_criterion"
                                   if verified else
                                   "official_hwpx_parent_law_review_candidate"),
                    "reference_quote": ref["excerpt"][:300],
                    "program_reference": links[0]["excerpt"][:300],
                    "service_quote": criteria[:1200],
                    "old_value": first["before"],
                    "new_value": first["after"],
                    "numeric_value_in_operating_criteria": bool(matched),
                    "old_attachment_sha256": first["old_attachment_sha256"],
                    "new_attachment_sha256": first["new_attachment_sha256"],
                },
                "status": ("review_of_verified_citation" if verified else
                           "program_link_candidate_requires_operational_proof"),
            }
    return list(result.values())


def run(root: Path) -> dict:
    programs = list(read_programs(root))
    generated = []
    statuses = Counter()
    ai_attempts, ai_verified, ai_errors = 0, 0, 0
    key_available = bool(os.getenv("PD_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
    model_available = bool(os.getenv("PD_LLM_MODEL"))
    ai_budget = max(0, int(os.getenv("PD_LLM_MAX_REQUESTS", "12")))
    # Reassess every persisted comparison, not only a recent 300-file slice.
    # Stable per-document IDs and content-addressed writes preserve work.
    files = sorted((root / "comparisons").glob("*.json.gz"))
    comparisons = [load(source, {}) for source in files]
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
        impacted = impact_for(doc, comparison, programs, program_refs)
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
        # Include exact official HWPX table changes. These were previously
        # omitted from all program impact matching despite valid source hashes.
        existing = {(a["service_id"], a["changed_clause"]) for a in impacted}
        for lead in numeric_standard_leads(doc, comparison, program_refs, grade):
            key = (lead["service_id"], lead["changed_clause"])
            if key not in existing:
                impacted.append(lead)
                existing.add(key)
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
