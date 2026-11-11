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
    """Pair unique HWPX tables by their actual row/column coordinates.

    Annex numbering restarts within each attachment, so 'table: 1' is NOT a
    stable cross-version identifier. Ambiguous pairs stay unresolved instead
    of manufacturing before/after monetary changes.
    """
    def cells(table):
        return {(norm(c.get("row")), norm(c.get("column"))): c
                for c in table.get("cells", [])
                if norm(c.get("row")) and norm(c.get("column"))}
    def columns(table):
        return {norm(v) for v in table.get("header", [])[1:] if norm(v)}
    old_index = [(table, cells(table)) for table in old]
    used = set()
    changes = []
    for current in new:
        current_cells = cells(current)
        if not current_cells:
            continue
        scored = []
        for index, (prior, previous_cells) in enumerate(old_index):
            common = set(current_cells) & set(previous_cells)
            if not common:
                continue
            same_header = list(map(norm, prior.get("header", []))) == (
                list(map(norm, current.get("header", []))))
            # Multiple shared coordinates or one truly identical single-cell
            # table are required. A shared table ordinal is never sufficient.
            if len(common) < 2 and not (
                    len(common) == 1 and same_header and
                    len(previous_cells) == len(current_cells) == 1):
                continue
            overlap = len(common) / max(1, min(len(previous_cells), len(current_cells)))
            if overlap < 0.6:
                continue
            shared_headers = len(columns(prior) & columns(current))
            score = (len(common), overlap, shared_headers,
                     int(same_header),
                     int(prior.get("table") == current.get("table")))
            scored.append((score, index, common))
        if not scored:
            continue
        scored.sort(reverse=True)
        best_score, old_index_number, coordinates = scored[0]
        # A tie might be two attachments with identical-looking columns. No
        # arbitrary attachment-to-attachment mapping is acceptable.
        if (old_index_number in used or
                (len(scored) > 1 and scored[1][0] == best_score)):
            continue
        used.add(old_index_number)
        prior, previous_cells = old_index[old_index_number]
        for key in sorted(coordinates):
            before, after = previous_cells[key], current_cells[key]
            if norm(before["value"]) == norm(after["value"]):
                continue
            changes.append({
                "table": current.get("table"),
                "row": after["row"], "column": after["column"],
                "before": before["value"], "after": after["value"],
                "old_attachment_sha256": prior["official_attachment_sha256"],
                "new_attachment_sha256": current["official_attachment_sha256"],
                "verification": "official_hwpx_cell_pair",
                "matching_method": "unique_row_column_table_pair",
            })
    return changes
