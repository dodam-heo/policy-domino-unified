"""Merge historic inventories and official live indexes without trusting source bodies.

Every discovered official ID/version is retained. Complete live list metadata
wins over historic listings, but neither proves a complete actual legal text.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import quote
from .engine import ident, load

TITLES={"law":"법령","admrul":"행정규칙","ordin":"자치법규"}


def official_link(record: dict) -> str:
    # A stable historical revision link is more reliable than the title-only
    # URL, which can redirect to a newer version after annual replacement.
    serial=str(record.get("serial") or "")
    if record.get("source") == "admrul" and serial.isdigit():
        return "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq="+serial
    if record.get("source") == "law" and serial.isdigit():
        return "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq="+serial
    url=str(record.get("url") or "")
    if url.startswith("https://www.law.go.kr/") or url.startswith("https://law.go.kr/"):
        return url
    title=record.get("title") or ""
    kind=TITLES.get(record.get("source"))
    return ("https://www.law.go.kr/"+quote(kind)+"/"+quote(title)
            if title and kind else "")


def indexed_documents(root: Path) -> dict[str,dict]:
    records={}
    historic=sorted((root/"indexes"/"legacy").glob("*/*.json.gz"))
    live=sorted((root/"indexes").glob("*/*.json.gz"))
    for path in [*historic,*live]:
        listing=load(path, {}) or {}
        for original in listing.get("records", []):
            if not isinstance(original, dict):
                continue
            if not all(original.get(k) for k in
                       ("source", "stable_id", "serial", "title")):
                continue
            if original["source"] not in TITLES:
                continue
            key=ident(original)
            before=records.get(key, {})
            # Metadata found later may be more precise; an empty field
            # never erases a previously retained value.
            row={k: v for k,v in before.items()}
            row.update({k:v for k,v in original.items() if v})
            row["url"]=official_link(row)
            row["index_grade"]=(
                "official_api_indexed" if path in live else
                row.get("index_grade", "historic_index_only"))
            records[key]=row
    return records
