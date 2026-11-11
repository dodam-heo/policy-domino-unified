"""Stable cell-by-cell comparison of numeric tables in official HWPX annex text.

The table heading, row and column must match between document versions.
The cell itself is taken verbatim from official downloaded annex content.
"""
from __future__ import annotations
import re

NUMBER = re.compile(r"(?<!\d)\d[\d,]*(?:\.\d+)?(?:\s*(?:원|만원|%))?(?!\d)")


def norm(value):
    return re.sub(r"\s+","",str(value or ""))


def extract_tables(text: str, source_sha: str) -> list[dict]:
    if not source_sha or "공식 표:\n" not in text:
        return []
    result=[]
    for number,block in enumerate(text.split("공식 표:\n")[1:],start=1):
        lines=[ln.strip() for ln in block.splitlines() if "|" in ln]
        if len(lines)<2:
            continue
        grid=[[part.strip() for part in line.split("|")] for line in lines]
        headers=grid[0]
        if len(headers)<2 or len(set(map(norm,headers)))!=len(headers):
            continue
        cells=[]
        for row in grid[1:]:
            if len(row)!=len(headers):
                continue
            for col in range(1,len(row)):
                label=row[0]
                cell=row[col]
                if not label or not NUMBER.search(cell) or not norm(headers[col]):
                    continue
                cells.append({"row":label,"column":headers[col],
                              "value":cell})
        if cells:
            result.append({"table":number,
                           "header":headers,
                           "cells":cells,
                           "official_attachment_sha256":source_sha})
    return result


def compare_tables(old: list[dict], new: list[dict]) -> list[dict]:
    previous={r["table"]:r for r in old}
    changes=[]
    for current in new:
        prior=previous.get(current.get("table"))
        if not prior or (list(map(norm,prior["header"])) !=
                        list(map(norm,current["header"]))):
            continue
        old_cells={(norm(c["row"]),norm(c["column"])):c
                   for c in prior["cells"]}
        for cell in current["cells"]:
            pair=(norm(cell["row"]),norm(cell["column"]))
            former=old_cells.get(pair)
            if not former or norm(former["value"])==norm(cell["value"]):
                continue
            changes.append({
                "table":current["table"],
                "row":cell["row"],"column":cell["column"],
                "before":former["value"],"after":cell["value"],
                "old_attachment_sha256":prior["official_attachment_sha256"],
                "new_attachment_sha256":current["official_attachment_sha256"],
                "verification":"official_hwpx_cell_pair",
            })
    return changes
