"""Deterministic before/after evidence summaries without invented semantics.

A common-prefix/suffix window preserves the actual changed words instead of
displaying unchanged 15k-character clauses as the headline. The full source is
always available separately. No LLM is required to produce the excerpt.
"""
from __future__ import annotations


def compact(text: str, limit: int = 125) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit-1].rstrip() + "…"


def focused_change(before: str, after: str, context: int = 42) -> dict:
    before, after = str(before or ""), str(after or "")
    if before == after:
        return {"before": "", "after": "", "changed": False}
    n = min(len(before), len(after))
    prefix = 0
    while prefix < n and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < n-prefix and
           before[len(before)-suffix-1] == after[len(after)-suffix-1]):
        suffix += 1
    old_end = len(before)-suffix
    new_end = len(after)-suffix
    old_focus = before[max(0,prefix-context):min(len(before),old_end+context)]
    new_focus = after[max(0,prefix-context):min(len(after),new_end+context)]
    return {
        "before": compact(old_focus),
        "after": compact(new_focus),
        "changed": True,
        "old_deleted": compact(before[prefix:old_end]),
        "new_added": compact(after[prefix:new_end]),
        "precision": "single_edit" if
            len(before[prefix:old_end]) < 200 and
            len(after[prefix:new_end]) < 200 else "multi_change_excerpt",
    }


def headline(changes: list[dict], verification: str) -> str:
    if not changes:
        return "신구 원문의 실질 변경 내용을 확인하고 있습니다"
    selected = next((c for c in changes if c.get("before") != c.get("after")), None)
    if not selected:
        return "현재 확보한 본문에서 실질 변경이 확인되지 않았습니다"
    focus = focused_change(selected.get("before", ""), selected.get("after", ""))
    article = selected.get("clause") or selected.get("article") or "해당 기준"
    if not focus["changed"]:
        return "실질 변경 대조 중"
    brief = (article+": "+focus["before"]+" → "+focus["after"])
    if verification != "official_comparison_verified":
        return "원문 재검증 필요 · "+compact(brief, 210)
    return compact(brief, 210)
