"""Independent resumable Gov24 public-service criteria collector.

The legacy public catalog is a one-time audited bootstrap only.
Subsequent updates use official Gov24 pages directly when a key is available.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .engine import load, store, save_json, hash256, clean

API = "https://api.odcloud.kr/api/gov24/v3/"
SOURCE = "https://www.data.go.kr/data/15113968/openapi.do"
CRITERIA_KEYS = ("선정기준", "지원대상", "지원내용", "신청기한", "구비서류")
LAW_KEYS = ("법령", "행정규칙", "자치법규")


def transform(row: dict, existing=None):
    existing = existing or {}
    id_ = clean(row.get("서비스ID") or existing.get("id"))
    if not id_:
        return None
    agency = clean(row.get("소관기관명") or existing.get("agency"))
    name = clean(row.get("서비스명") or existing.get("service_name"))
    agency_type = clean(row.get("소관기관유형") or existing.get("agency_type"))
    if not agency or not name or "민간" in agency_type:
        return None
    old_basis, old_criteria = existing.get("basis", {}), existing.get("criteria", {})
    basis = {k: clean(row.get(k) or old_basis.get(k))[:5000] for k in LAW_KEYS}
    criteria = {k: clean(row.get(k) or old_criteria.get(k))[:5000]
                for k in CRITERIA_KEYS}
    return {
        "id": id_, "agency": agency, "agency_type": agency_type,
        "service_name": name, "criteria": criteria, "basis": basis,
        "url": clean(row.get("상세조회URL") or existing.get("url") or SOURCE),
        "origin": "official_gov24_public_service_catalog",
        "updated": clean(row.get("수정일시") or existing.get("updated")),
    }


class Gov24Client:
    def __init__(self, key: str, transport=None):
        self.key, self.transport = key.strip(), transport
        if not self.key:
            raise ValueError("GOV24_SERVICE_KEY not configured")

    def request(self, endpoint: str, page: int, per_page: int) -> dict:
        if endpoint not in ("serviceList", "serviceDetail"):
            raise ValueError("Unsupported Gov24 endpoint")
        params = {"page": page, "perPage": per_page}
        def get(header_auth=False):
            query = dict(params)
            if not header_auth:
                query["serviceKey"] = self.key
            url = API + endpoint + "?" + urlencode(query)
            headers = {"Accept": "application/json",
                       "User-Agent": "PolicyDominoUnified/1.0"}
            if header_auth:
                headers["Authorization"] = "Infuser "+self.key
            if self.transport:
                return self.transport(endpoint, page, per_page, header_auth)
            with urlopen(Request(url, headers=headers), timeout=24) as response:
                raw = response.read(3_000_001)
            if len(raw) > 3_000_000:
                raise ValueError("Gov24 response exceeds 3MB")
            return json.loads(raw)
        try:
            response = get(False)
        except HTTPError as exc:
            if exc.code not in (401, 403):
                raise RuntimeError("Gov24 API HTTP "+str(exc.code)) from None
            response = get(True)
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ValueError("Gov24 unexpected official schema")
        if not isinstance(response.get("totalCount", 0), int):
            raise ValueError("Gov24 totalCount unavailable")
        return response


def merge_page(root: Path, records: list[dict]) -> int:
    by_shard = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        sid = clean(row.get("서비스ID"))
        if sid:
            by_shard.setdefault(hash256(sid)[:2], []).append(row)
    updated = 0
    for shard, changes in by_shard.items():
        destination = root / "programs" / (shard + ".json.gz")
        content = load(destination, {"source": "gov24", "records": []})
        previous = {r["id"]: r for r in content.get("records", [])
                    if isinstance(r, dict) and r.get("id")}
        for row in changes:
            old = previous.get(row["서비스ID"])
            new = transform(row, old)
            if new:
                previous[new["id"]] = new
        if store(destination, {"source": "gov24", "records":
                 sorted(previous.values(), key=lambda x: x["id"])}):
            updated += 1
    return updated


def collect(root: Path, client: Gov24Client, list_pages=3, detail_pages=3):
    state_file = root / "gov24-status.json"
    state = load(state_file, {}) or {}
    result = {"listed_pages": 0, "detail_pages": 0, "changed_shards": 0,
              "errors": [], "provider": SOURCE}
    for endpoint, budget, size in (("serviceList", list_pages, 1000),
                                   ("serviceDetail", detail_pages, 200)):
        field = "cursor_"+endpoint
        page = max(1, int(state.get(field, 1)))
        for _ in range(max(0, budget)):
            try:
                response = client.request(endpoint, page, size)
                rows = response["data"]
                total = int(response["totalCount"])
                if not rows and total > (page-1)*size:
                    raise ValueError("Official page missing data")
                result["changed_shards"] += merge_page(root, rows)
                result["listed_pages" if endpoint == "serviceList" else "detail_pages"] += 1
                if page*size >= total or len(rows) < size:
                    page = 1
                    state["complete_"+endpoint] = True
                    break
                page += 1
            except Exception as exc:
                result["errors"].append(endpoint+":"+
                    type(exc).__name__+":"+str(exc)[:110])
                state["complete_"+endpoint] = False
                break
            finally:
                state[field] = page
                save_json(state_file, state)
        state[field] = page
        save_json(state_file, state)
    state["last_run"] = result
    save_json(state_file, state)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--list-pages", type=int, default=3)
    p.add_argument("--detail-pages", type=int, default=3)
    args = p.parse_args()
    key = os.getenv("GOV24_SERVICE_KEY", "").strip()
    if not key:
        print('GOV24_CURRENT: no API key in this repository; cached official snapshot retained')
        return
    report = collect(args.root, Gov24Client(key), args.list_pages, args.detail_pages)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
