"""One-time reuse of conflict-free v2/v4/NEXT verified source bodies.

Preserves the original version identity and provenance. Never copies a
conflicting/partial source as a verified official original, and never
requires legacy repositories during future independent collection runs.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re
from collections import defaultdict

from .audit import audit, body_info, digest
from .engine import (relative_path, store, load, compare_bodies, hash256,
                     ident, save_json)


def _body(clauses: dict):
    return {
        "status": "legacy_extracted",
        "clauses": {str(k): (v["text"] if isinstance(v, dict) else v)
                    for k, v in clauses.items()},
        "attachment_links": [],
        "incomplete_keys": [],
        "body_sha256": digest(json.dumps(
            {str(k): (v["text"] if isinstance(v, dict) else v)
             for k, v in clauses.items()}, ensure_ascii=False, sort_keys=True)),
        "raw_xml_sha256": "",
        "original_xml_available": False,
    }


def extract_origin(label, state, wanted):
    if label == "v2":
        snapshots = state.get("snapshots", {})
        for doc in state.get("events", {}).values():
            if not isinstance(doc, dict):
                continue
            key = (str(doc.get("source")), str(doc.get("stable_id")),
                   str(doc.get("serial")))
            if key not in wanted:
                continue
            snap = snapshots.get(digest("|".join(key[:2]))[:20], {})
            if str(snap.get("serial")) != key[2]:
                continue
            yield key, doc, snap.get("clauses", {})
    elif label == "v4":
        snapshots = state.get("verified_snapshots", {}).values()
        catalog = {(str(r.get("source")), str(r.get("stable_id")),
                    str(r.get("serial"))): r
                   for r in state.get("catalog", {}).values()
                   if isinstance(r, dict)}
        for snap in snapshots:
            if not isinstance(snap, dict) or snap.get("complete_source") is not True:
                continue
            key = (str(snap.get("source")), str(snap.get("stable_id")),
                   str(snap.get("serial")))
            if key in wanted:
                yield key, catalog.get(key, snap), snap.get("clauses", {})
    elif label == "next":
        versions = state.get("versions", {})
        for id_, doc in state.get("documents", {}).items():
            if not isinstance(doc, dict):
                continue
            key = (str(doc.get("source")), str(doc.get("stable_id")),
                   str(doc.get("serial")))
            if key not in wanted:
                continue
            version = versions.get(id_, {})
            if version.get("status") == "extracted":
                yield key, doc, version.get("clauses", {})


def _normalize_record(record, key):
    source, stable, serial = key
    return {
        "source": source, "stable_id": stable, "serial": serial,
        "title": record.get("title", ""),
        "published_at": record.get("published_at") or record.get("promulgated_at") or "",
        "effective_date": record.get("effective_date") or "",
        "kind": record.get("law_type") or record.get("kind") or "",
        "ministry": record.get("ministry") or "",
        "revision": record.get("revision") or "",
        "url": record.get("url") or "",
    }


def compare_imported(root: Path, migrated: list[dict]) -> int:
    grouped = defaultdict(list)
    for record in migrated:
        grouped[(record["source"], record["stable_id"])].append(record)
    total = 0
    for records in grouped.values():
        records.sort(key=lambda r: (r["published_at"], r["serial"]))
        for previous, current in zip(records, records[1:]):
            if not (previous["published_at"] and current["published_at"] and
                    previous["published_at"] < current["published_at"]):
                continue
            destination = root / "comparisons" / (hash256(ident(current))[:24]+".json.gz")
            if destination.exists():
                continue
            before = load(root / relative_path(previous))
            after = load(root / relative_path(current))
            if not before or not after:
                continue
            result = compare_bodies(before["body"], after["body"])
            result["prior_record"] = previous
            result["changed_record"] = current
            result["source_of_comparison"] = "independently_approved_legacy_originals"
            if store(destination, result):
                total += 1
    return total


def migrate(paths: dict[str, Path], root: Path) -> dict:
    report, manifest = audit(paths)
    wanted = defaultdict(dict)
    for row in manifest:
        key = (row["source"], row["stable_id"], row["serial"])
        wanted[row["origin"]][key] = row
    imported, skipped, migrated = 0, 0, []
    for label in ("v2", "v4", "next"):
        if not wanted[label]:
            continue
        with paths[label].open("r", encoding="utf8") as stream:
            data = json.load(stream)
        seen = set()
        for key, doc, clauses in extract_origin(label, data, wanted[label]):
            if key in seen:
                continue
            seen.add(key)
            actual = body_info(clauses)
            expected = wanted[label][key]
            if not actual["complete"] or actual["hash"] != expected["sha256"]:
                skipped += 1
                continue
            rec = _normalize_record(doc, key)
            destination = root / relative_path(rec)
            if destination.exists():
                skipped += 1  # Independently obtained newer original wins.
                continue
            item = {
                "identity": ident(rec), "record": rec,
                "body": _body(clauses),
                "source_snapshot_provenance": {
                    "generation": label, "original_version_sha256": actual["hash"],
                    "original_source_pointer": expected["pointer"],
                    "has_raw_official_xml": False,
                    "status": "verified_complete_extracted_text",
                },
                "imported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            if store(destination, item):
                imported += 1
                migrated.append(rec)
        del data
    compared = compare_imported(root, migrated)
    status = {
        "candidate_complete_versions": len(manifest),
        "imported_originals": imported,
        "skipped_or_superseded": skipped,
        "built_comparisons": compared,
        "unresolved_candidate_origins": len(manifest)-imported-skipped,
        "full_document_originals_not_inferred_from_excerpts": True,
        "latest_source_identity_maintained": True,
        "source_snapshot_pins": {
            "v2": "66212ee4060e7742ce37f114287f5afecb0244e9",
            "v4": "b590e4324d5b6e55d805914862c8356d0bf7c1b4",
            "next": "898db398694f55fc95d1d2ac188c7ea67b9e623e",
        },
    }
    save_json(root / "migration-status.json", status)
    return status


def main():
    parser = argparse.ArgumentParser()
    for version in ("v2", "v4", "next"):
        parser.add_argument("--"+version, type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data"))
    opts = parser.parse_args()
    result = migrate({v: getattr(opts, v) for v in ("v2", "v4", "next")}, opts.root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
