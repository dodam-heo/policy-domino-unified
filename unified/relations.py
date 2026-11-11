"""Evidence-typed legal provision → downstream rule → public program graph.

The source reference must identify the exact CHANGED clause. A mention of
the same law or a keyword is never a verified operational requirement.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re
from .engine import ident, load, hash256
from .verification import OFFICIAL, source_grade

CITE = re.compile(r"「([^」]{2,180})」")
ARTICLE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
OPERATIVE = re.compile(r"따라|따른|적용|준용|산정|계산|선정|지급|기준으로|규정에\s*의하여")
PARAGRAPH = re.compile(r"제\s*(\d+)\s*항")
CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def references(text: str) -> list[dict]:
    """No borrowing a clause number from a different law reference."""
    result = []
    for cite in CITE.finditer(text):
        tail = text[cite.end():]
        boundaries = [i for token in ("「", "\n", "。", ".", ";") if
                      (i := tail.find(token)) >= 0]
        window = tail[:min(boundaries)] if boundaries else tail
        window = window[:50]
        article = ARTICLE.search(window[:24])
        if not article or article.start() > 13:
            continue
        clause = "제"+article.group(1)+"조"+(
            "의"+article.group(2) if article.group(2) else "")
        extra = window[article.end():article.end()+15]
        paragraph = PARAGRAPH.search(extra)
        number = int(paragraph.group(1)) if paragraph and paragraph.start() <= 4 else None
        fragment = text[max(0, cite.start()-50):min(len(text), cite.end()+130)]
        result.append({
            "title": cite.group(1),
            "article": clause,
            "paragraph": number,
            "excerpt": fragment,
            "operational": bool(OPERATIVE.search(window[:50])),
        })
    return result


def changed_paragraph_numbers(before: str, after: str) -> set[int] | None:
    """Compare the cited paragraph, not merely its parent article."""
    def split(text):
        hits = [(n,i) for i,ch in enumerate(text) if (n:=CIRCLES.find(ch)+1)>0]
        if not hits:
            return None
        return {number: text[start: hits[i+1][1] if i+1<len(hits) else len(text)]
                for i,(number,start) in enumerate(hits)}
    a,b=split(str(before or "")),split(str(after or ""))
    if a is None or b is None:
        return None
    return {n for n in set(a)|set(b) if a.get(n)!=b.get(n)}


def index_program_references(programs: list[dict]):
    lookup = defaultdict(list)
    for program in programs:
        basis = " ".join(str(x or "") for x in program.get("basis", {}).values())
        unique = {(normalize(ref["title"]),normalize(ref["article"]))
                  for ref in references(basis)}
        for key in unique:
            lookup[key].append(program)
    return lookup


def legal_dependents(root: Path, comparisons: list[dict]) -> dict[str, list[dict]]:
    """Indexed join: scan each downstream official body only once."""
    changed = defaultdict(list)
    for comp in comparisons:
        doc = comp.get("changed_record") or {}
        if not doc:
            continue
        for change in comp.get("changes", []):
            if not change.get("clause") or change.get("before") == change.get("after"):
                continue
            changed[(normalize(doc.get("title")), normalize(change["clause"]))].append({
                "doc": doc, "change": change,
            })
    graph = defaultdict(list)
    if not changed:
        return graph
    for path in (root/"documents").glob("*/*/*.json.gz"):
        package = load(path, {})
        doc = package.get("record", {})
        body = package.get("body", {})
        if not all(doc.get(k) for k in ("source", "stable_id", "serial")):
            continue
        for clause, content in body.get("clauses", {}).items():
            for ref in references(str(content)):
                if not ref["operational"]:
                    continue
                for match in changed.get((normalize(ref["title"]),
                                          normalize(ref["article"])), []):
                    parent = match["doc"]
                    paragraphs = changed_paragraph_numbers(
                        match["change"].get("before", ""),
                        match["change"].get("after", ""))
                    if (ref.get("paragraph") is not None and
                            paragraphs is not None and ref["paragraph"] not in paragraphs):
                        continue
                    if ident(parent) == ident(doc) or (
                            parent["source"] == doc["source"] and
                            parent["stable_id"] == doc["stable_id"]):
                        continue
                    status = ("official_reference_verified" if
                              source_grade(package) == OFFICIAL and
                              (ref.get("paragraph") is None or paragraphs is not None)
                              else "reference_scope_needs_revalidation")
                    graph[ident(parent)].append({
                        "title": doc.get("title"), "id": ident(doc),
                        "source": doc.get("source", ""),
                        "article": clause,
                        "changed_article": ref["article"],
                        "referenced_paragraph": ref.get("paragraph"),
                        "reference_quote": ref["excerpt"][:300],
                        "url": doc.get("url", ""),
                        "ministry": doc.get("ministry", ""),
                        "verification": status,
                        "change_location": match["change"].get("clause"),
                    })
    for key in graph:
        uniq = {}
        for edge in graph[key]:
            identity = (edge["id"], edge["article"], edge["changed_article"])
            uniq[identity] = edge
        graph[key] = list(uniq.values())
    return graph


def two_hop_program_leads(doc: dict, comparison: dict, edges: list[dict],
                          program_index: dict) -> list[dict]:
    """Legal application chains are review leads, not proven required edits."""
    changed_clauses = {normalize(c.get("clause")): c for c in
                       comparison.get("changes", []) if c.get("before") != c.get("after")}
    leads = {}
    for edge in edges:
        change = changed_clauses.get(normalize(edge.get("changed_article")))
        if not change:
            continue
        for program in program_index.get((normalize(edge.get("title")),
                                          normalize(edge.get("article"))), []):
            if not program.get("agency") or not program.get("service_name"):
                continue
            key = (program["id"], edge["changed_article"])
            proof = {"proof_type": "two_hop_exact_changed_article_reference",
                     "reference_quote": edge["reference_quote"],
                     "intermediate_regulation": edge["title"],
                     "intermediate_article": edge["article"],
                     "intermediate_source_url": edge["url"],
                     "intermediate_verification": edge["verification"],
                     "program_reference": "「"+edge["title"]+"」 "+edge["article"],
                     "service_quote": next((v for v in
                         program.get("criteria", {}).values() if v), "")[:1200]}
            lead = {"agency": program["agency"],
                    "agency_type": program.get("agency_type", ""),
                    "service": program["service_name"],
                    "service_id": program["id"],
                    "service_url": program.get("url", ""),
                    "policy_url": doc.get("url", ""),
                    "policy": doc.get("title", ""),
                    "changed_clause": edge["changed_article"],
                    "required_change": "상위 변경 조항과 적용 규정을 근거로 해당 사업의 기준·절차 연결을 재검증",
                    "before": change.get("before", ""),
                    "after": change.get("after", ""),
                    "evidence": proof,
                    "status": "program_link_candidate_requires_operational_proof"}
            leads[key] = lead
    return list(leads.values())
