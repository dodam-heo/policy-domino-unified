"""Read-only cross-generation census of official legal identifiers and complete body versions.

Never treats absence from a partial historical collector as absence from the official corpus.
Never equates a v2 diff excerpt with a complete original document.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

SOURCES = {"law", "admrul", "ordin"}
REQUIRED_REGRESSIONS = {
    "기준 중위소득": ("기준 중위소득", "기준중위소득"),
    "주거급여": ("주거급여", "주거 급여"),
    "교육급여": ("교육급여", "교육 급여"),
}
LABELS = ("v2", "v4", "next")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_version(row: dict) -> tuple[str, str, str] | None:
    source, sid, serial = (str(row.get(k) or "").strip()
                           for k in ("source", "stable_id", "serial"))
    return (source, sid, serial) if source in SOURCES and sid and serial else None


def body_info(clauses: object, *, next_style: bool = False,
              required_complete: bool = True) -> dict:
    if not isinstance(clauses, dict) or not clauses:
        return {"complete": False, "hash": "", "parts": 0, "chars": 0}
    parts, total = [], 0
    for key, val in sorted(clauses.items(), key=lambda x: str(x[0])):
        if isinstance(val, dict):
            if not val.get("complete"):
                return {"complete": False, "hash": "", "parts": len(clauses), "chars": 0}
            value = val.get("text", "")
        elif isinstance(val, str):
            value = val
        else:
            return {"complete": False, "hash": "", "parts": len(clauses), "chars": 0}
        value = normalize_text(value)
        if not value or (required_complete and len(value) >= 12000):
            return {"complete": False, "hash": "", "parts": len(clauses), "chars": 0}
        parts.append((str(key), value))
        total += len(value)
    return {"complete": True, "hash": digest(json.dumps(parts, ensure_ascii=False,
              separators=(",", ":"))), "parts": len(parts), "chars": total}


def record_from(row: dict, label: str, locator: str, body: dict | None = None) -> dict | None:
    key = stable_version(row)
    if not key:
        return None
    title = normalize_text(row.get("title"))
    return {
        "key": key, "label": label, "locator": locator, "title": title,
        "published_at": row.get("published_at") or row.get("promulgated_at") or "",
        "effective_date": row.get("effective_date") or "",
        "kind": row.get("law_type") or row.get("kind") or "",
        "body": body or {"complete": False, "hash": "", "parts": 0, "chars": 0},
    }


def list_v2(state: dict):
    items = state.get("events", {})
    if not isinstance(items, dict):
        raise ValueError("v2 events should be a dictionary")
    snapshots = state.get("snapshots", {})
    if not isinstance(snapshots, dict):
        raise ValueError("v2 snapshots should be a dictionary")
    for row in items.values():
        if not isinstance(row, dict):
            continue
        source, sid, serial = stable_version(row) or ("", "", "")
        snapshot = snapshots.get(digest("|".join((source, sid)))[:20], {})
        clauses = {}
        if isinstance(snapshot, dict) and str(snapshot.get("serial")) == serial:
            clauses = snapshot.get("clauses", {})
        yield record_from(row, "v2", "data/v2_state.json:events", body_info(clauses))
    for row in state.get("pending", []):
        if isinstance(row, dict):
            yield record_from(row, "v2", "data/v2_state.json:pending")


def list_v4(state: dict):
    catalog = state.get("catalog", {})
    if not isinstance(catalog, dict):
        raise ValueError("v4 catalog should be a dictionary")
    snapshots = defaultdict(list)
    for r in state.get("verified_snapshots", {}).values():
        if not isinstance(r, dict):
            continue
        key = stable_version(r)
        if key:
            snapshots[key].append(r)
    for row in catalog.values():
        if not isinstance(row, dict):
            continue
        key = stable_version(row)
        body = None
        if key:
            for snapshot in snapshots.get(key, []):
                if snapshot.get("complete_source") is True:
                    info = body_info(snapshot.get("clauses", {}))
                    if info["complete"]:
                        body = info
                        break
        yield record_from(row, "v4", "data/v4_state.json:catalog", body)


def list_next(state: dict):
    documents = state.get("documents", {})
    versions = state.get("versions", {})
    if not isinstance(documents, dict) or not isinstance(versions, dict):
        raise ValueError("NEXT documents and versions should be dictionaries")
    for doc_id, row in documents.items():
        if not isinstance(row, dict):
            continue
        body = None
        version = versions.get(doc_id, {})
        if isinstance(version, dict) and version.get("status") == "extracted":
            body = body_info(version.get("clauses", {}), next_style=True)
        yield record_from(row, "next", "data/state.json:documents/"+str(doc_id), body)


def coverage_summary(label: str, state: dict) -> dict:
    if label == "next":
        windows = list((state.get("collection_windows") or {}).values())
        windows = [w for w in windows if isinstance(w, dict)]
    elif label == "v4":
        windows = [w for w in state.get("coverage", []) if isinstance(w, dict)]
    else:
        windows = []
    kinds = Counter(str(r.get("rule_category") or r.get("rule_kind") or
                        r.get("source") or "unknown") for r in windows)
    return {
        "windows_checked": len(windows),
        "complete": sum(w.get("complete") is True for w in windows),
        "incomplete": sum(w.get("complete") is not True for w in windows),
        "by_kind": dict(sorted(kinds.items())),
        "bounded_examples": [w for w in windows if w.get("complete") is not True][:12],
        "coverage_statement": "해당 버전이 기록한 조사 구간만 집계; 공식 전체 모집단과 다름",
    }


def audit(inputs: dict[str, Path]) -> tuple[dict, list[dict]]:
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    per_label = {x: Counter() for x in LABELS}
    by_source = {x: Counter() for x in LABELS}
    coverage = {}
    malformed = Counter()
    for label in LABELS:
        # Sequential parsing avoids retaining all three original JSON trees.
        with inputs[label].open("r", encoding="utf-8") as file:
            state = json.load(file)
        coverage[label] = coverage_summary(label, state)
        factory = {"v2": list_v2, "v4": list_v4, "next": list_next}[label]
        for r in factory(state):
            if r is None:
                malformed[label] += 1
                continue
            by_key[r["key"]].append(r)
            per_label[label]["records"] += 1
            by_source[label][r["key"][0]] += 1
            if r["body"]["complete"]:
                per_label[label]["complete_originals"] += 1
        del state
    overlaps, collisions, duplicates = [], [], []
    unique_by_label = {k: set() for k in LABELS}
    reusable = []
    for key, rows in by_key.items():
        present = {r["label"] for r in rows}
        for label in present:
            unique_by_label[label].add(key)
        if len(present) > 1:
            overlaps.append(key)
        for label in present:
            candidates = [r for r in rows if r["label"] == label]
            if len(candidates) > 1:
                duplicates.append({"key": key, "label": label, "count": len(candidates)})
        titles = {r["title"] for r in rows if r["title"]}
        body_hashes = {r["body"]["hash"] for r in rows if r["body"]["complete"]}
        if len(titles) > 1 or len(body_hashes) > 1:
            collisions.append({"key": key, "titles": sorted(titles),
                               "body_conflict": len(body_hashes) > 1,
                               "locations": [r["locator"] for r in rows]})
        full = [r for r in rows if r["body"]["complete"]]
        if full and len(body_hashes) == 1:
            preferred = sorted(full, key=lambda x: {"v4": 0, "next": 1, "v2": 2}[x["label"]])[0]
            reusable.append({"source": key[0], "stable_id": key[1],
                             "serial": key[2], "sha256": preferred["body"]["hash"],
                             "parts": preferred["body"]["parts"],
                             "original_chars": preferred["body"]["chars"],
                             "origin": preferred["label"], "pointer": preferred["locator"]})
    missing = {
        label: {other: len(unique_by_label[other] - unique_by_label[label])
                for other in LABELS if other != label}
        for label in LABELS
    }
    all_titles = {k: set(r["title"] for r in rows) for k, rows in by_key.items()}
    checks = {}
    for name, terms in REQUIRED_REGRESSIONS.items():
        matched = [(key, rows) for key, rows in by_key.items()
                   if key[0] == "admrul" and any(
                       any(t in title.replace(" ", "") for t in terms)
                       for title in all_titles[key])]
        checks[name] = {
            "matched_versions": len(matched),
            "present_in": {label: sum(any(r["label"] == label for r in rows)
                                      for _, rows in matched) for label in LABELS},
            "complete_body_versions": sum(any(r["body"]["complete"] for r in rows)
                                           for _, rows in matched),
            "validated": bool(matched),
        }
    report = {
        "schema": "policy-domino-cross-version-audit-v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_files": {k: str(v) for k, v in inputs.items()},
        "scope": "3개 역사 원장의 상호 대조; 공식 전체 누락 규모는 완결된 수집 구간과 따로 평가",
        "totals": {
            "unique_versions_union": len(by_key),
            "unique_versions_by_generation": {k: len(v) for k, v in unique_by_label.items()},
            "records_and_complete_originals": {k: dict(v) for k, v in per_label.items()},
            "source_breakdown": {k: dict(v) for k, v in by_source.items()},
            "overlapping_versions": len(overlaps),
            "duplicate_occurrences": len(duplicates),
            "metadata_or_original_conflicts": len(collisions),
            "body_conflicts": sum(x["body_conflict"] for x in collisions),
            "reusable_complete_versions": len(reusable),
            "invalid_identity_rows": dict(malformed),
            "relative_missing_versions": missing,
        },
        "coverage": coverage,
        "required_examples": checks,
        "duplicate_examples": duplicates[:60],
        "conflict_examples": collisions[:100],
        "warnings": ["상대적 누락과 공식 모집단의 절대 누락을 혼동하지 않음",
                     "완전하지 않은 별표·원문은 재사용 가능 건수에서 제외",
                     "같은 문서명만으로 다른 공식 ID를 병합하지 않음"],
    }
    return report, reusable


def write_reports(inputs: dict[str, Path], out: Path) -> dict:
    report, reuse = audit(inputs)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf8")
    (out / "reuse-manifest.json").write_text(json.dumps(reuse, ensure_ascii=False,
        separators=(",", ":")), "utf8")
    totals = report["totals"]
    lines = ["# 기존 v2·v4·NEXT 원천 데이터 전수 감사", "",
             "생성 시각: " + report["generated_at"], "",
             "## 실제 집계", "",
             "| 구분 | 결과 |", "| --- | ---: |"]
    lines.extend("| " + k.replace("_", " ") + " | " + str(totals[k]) + " |"
                 for k in ("unique_versions_union", "overlapping_versions",
                           "duplicate_occurrences", "metadata_or_original_conflicts",
                           "body_conflicts", "reusable_complete_versions"))
    lines += ["", "## 버전별 고유 판본", ""]
    for label, count in totals["unique_versions_by_generation"].items():
        lines.append("- " + label + ": " + str(count))
    lines += ["", "## 상대적 누락 (다른 원장에서 발견된 판본)", ""]
    for label, others in totals["relative_missing_versions"].items():
        lines.append("- " + label + ": " + ", ".join(
            other + "=" + str(count) for other, count in others.items()))
    lines += ["", "## 필수 회귀 예시", ""]
    for name, check in report["required_examples"].items():
        lines.append("- " + name + ": " + json.dumps(check, ensure_ascii=False))
    lines += ["", "## 수집 구간 완결성", ""]
    for name, row in report["coverage"].items():
        lines.append("- " + name + ": " + str(row["complete"]) + " 완결 / " +
                     str(row["incomplete"]) + " 미완결 / " +
                     str(row["windows_checked"]) + " 기록 구간")
    lines += ["", "전체 충돌 예시와 재사용 가능 원문 판본의 출처는 audit.json 및 reuse-manifest.json 참고.",
             "현재 데이터는 완전한 공식 모집단이라고 주장하지 않습니다.", ""]
    (out / "audit.md").write_text("\n".join(lines), "utf8")
    return report


def main():
    parser = argparse.ArgumentParser()
    for label in LABELS:
        parser.add_argument("--" + label, type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports"))
    args = parser.parse_args()
    report = write_reports({label: getattr(args, label) for label in LABELS}, args.out)
    print(json.dumps(report["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
