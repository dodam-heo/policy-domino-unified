"""One-time, idempotent legacy *metadata* bootstrap.

Reads the three pinned historic state files. Only normalized official version
identities and metadata are carried forward; no legacy inferred impact or AI
response is imported. Preserves all 46k+ listed versions, not only extracted
body versions. Existing source documents are never downgraded or overwritten.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
from .audit import list_v2, list_v4, list_next
from .engine import hash256, load, store, ident


def bootstrap(inputs: dict[str, Path], root: Path) -> dict:
    by_id = {}
    origins = defaultdict(set)
    factories = {"v2": list_v2, "v4": list_v4, "next": list_next}
    seen_per_source = {}
    for name, factory in factories.items():
        with inputs[name].open(encoding="utf8") as handle:
            state = json.load(handle)
        n = 0
        for record in factory(state):
            if not record:
                continue
            source, stable_id, serial = record["key"]
            key = "|".join(record["key"])
            origins[key].add(name)
            earlier = by_id.get(key, {})
            info = {"source": source, "stable_id": stable_id, "serial": serial,
                    "title": record.get("title") or earlier.get("title") or "",
                    "published_at": record.get("published_at") or
                                    earlier.get("published_at") or "",
                    "effective_date": record.get("effective_date") or
                                      earlier.get("effective_date") or "",
                    "kind": record.get("kind") or earlier.get("kind") or ""}
            # Preserve the best available metadata, never infer a complete original.
            if not earlier or sum(bool(v) for v in info.values()) >= sum(
                    bool(v) for v in earlier.values()):
                by_id[key] = info
            n += 1
        seen_per_source[name] = n
        del state
    shards = defaultdict(list)
    for key, info in by_id.items():
        info["origin_archives"] = sorted(origins[key])
        info["content_status"] = "historic_index_only"
        shard = hash256(key)[:2]
        shards[(info["source"], shard)].append(info)
    changed = 0
    for (source, shard), records in sorted(shards.items()):
        records.sort(key=lambda x: ident(x))
        target = root / "indexes" / "legacy" / source / (shard+".json.gz")
        changed += int(store(target, {"schema": "policy-domino-legacy-index-v1",
                                     "records": records}))
    output = {"unique_official_versions": len(by_id),
              "shards": len(shards), "changed_shards": changed,
              "source_record_counts": seen_per_source,
              "status": "metadata_only_not_verified_source_original"}
    target = root / "legacy-index-status.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf8")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2", required=True, type=Path)
    parser.add_argument("--v4", required=True, type=Path)
    parser.add_argument("--next", required=True, type=Path)
    parser.add_argument("--root", default=Path("data"), type=Path)
    args = parser.parse_args()
    print(json.dumps(bootstrap({"v2": args.v2, "v4": args.v4,
                                "next": args.next}, args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
