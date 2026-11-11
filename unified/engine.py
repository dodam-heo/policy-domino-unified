"""Independent official-law incremental collection and version comparison.

New discovery does not import historical V2/V4/NEXT code or state.
One immutable compressed source file per official document version.
Unresolved annexes/attachments are explicitly incomplete, never invented.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
from dataclasses import dataclass, asdict
import gzip
import html
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, quote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

API = "https://www.law.go.kr/DRF/"
FIELDS = {
    "law": ("법령명한글", "법령ID", "법령일련번호", "공포일자", "ancYd", "MST"),
    "admrul": ("행정규칙명", "행정규칙ID", "행정규칙일련번호", "발령일자", "prmlYd", "ID"),
    "ordin": ("자치법규명", "자치법규ID", "자치법규일련번호", "공포일자", "ancYd", "MST"),
}
KINDS = {"1": "훈령", "2": "예규", "3": "고시", "4": "공고", "5": "지침", "6": "기타"}
CLAUSE_TAGS = ("조문내용", "조내용", "항내용", "호내용", "목내용")
LINK_TAGS = {"별표서식파일링크", "별표서식PDF파일링크", "첨부파일링크", "별표파일링크"}
MAX_RESPONSE = 16_000_000
YEAR = re.compile(r"(?:19|20)\d{2}\s*년(?:도)?")


def hash256(raw: bytes | str) -> str:
    return hashlib.sha256(raw.encode("utf8") if isinstance(raw, str) else raw).hexdigest()


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def tag(el) -> str:
    return el.tag.split("}")[-1]


def field(node, name: str, direct=False) -> str:
    els = list(node) if direct else node.iter()
    match = next((x for x in els if tag(x) == name), None)
    return clean("".join(match.itertext())) if match is not None else ""


def ymd(text: str) -> str:
    digits = re.sub("[^0-9]", "", text or "")
    if len(digits) != 8:
        return ""
    try:
        return dt.date(int(digits[:4]), int(digits[4:6]), int(digits[6:])).isoformat()
    except ValueError:
        return ""


def ident(rec) -> str:
    return "|".join((rec["source"], rec["stable_id"], rec["serial"]))


def relative_path(rec: dict) -> Path:
    source, stable, serial = rec["source"], rec["stable_id"], rec["serial"]
    if source not in FIELDS or not stable or not serial:
        raise ValueError("Incomplete official document identity")
    # IDs enter paths only after hashing; cannot traverse output directories.
    return Path("documents") / source / hash256(source + "|" + stable)[:16] / (
        hash256(ident(rec))[:24] + ".json.gz")


def store(path: Path, obj: dict):
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf8")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = gzip.compress(data, compresslevel=6, mtime=0)
    if path.exists() and path.read_bytes() == content:
        return False
    # Concurrent version recovery can write the same predecessor. Each writer
    # must own its temporary path; atomic replacement preserves a complete blob.
    temp = path.with_name(path.name + "." + str(threading.get_ident()) + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)
    return True


def load(path: Path, default=None):
    if not path.exists():
        return default
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf8") as handle:
            return json.load(handle)
    return json.loads(path.read_text("utf8"))


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(data, "utf8")
    temp.replace(path)


def parse_index(root, source, rule_kind=""):
    cfg = FIELDS[source]
    needed = {cfg[0], cfg[2]}
    result = {}
    for node in root.iter():
        children = {tag(el) for el in node}
        if not needed <= children:
            continue
        title, stable, serial = (field(node, col, True) for col in cfg[:3])
        issued = ymd(field(node, cfg[3], True) or field(node, "공포일자", True))
        if not (title and stable and serial and issued):
            continue
        kind = (KINDS.get(rule_kind) or
                field(node, "행정규칙종류", True) if source == "admrul" else
                field(node, "법령구분명", True) or
                field(node, "법령구분", True) if source == "law" else
                "자치법규")
        rec = {
            "source": source, "stable_id": stable, "serial": serial,
            "title": title, "published_at": issued,
            "effective_date": ymd(field(node, "시행일자", True)),
            "revision": field(node, "제개정구분명", True) or field(node, "제개정구분", True),
            "kind": kind, "ministry": field(node, "소관부처명", True) or
                                        field(node, "지자체기관명", True),
            "url": "https://www.law.go.kr/" +
                   quote({"law": "법령", "admrul": "행정규칙",
                          "ordin": "자치법규"}[source]) + "/" + quote(title),
        }
        result[ident(rec)] = rec
    return list(result.values())


def parse_body(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    clauses = {}
    links = []
    for el in root.iter():
        k = tag(el)
        if k in LINK_TAGS:
            url = clean("".join(el.itertext()))
            if url and url not in links:
                links.append(url)
        if k == "조문단위":
            number = field(el, "조문번호")
            if not number:
                continue
            branch = field(el, "조문가지번호")
            key = "제" + number + "조" + ("의" + branch if branch not in ("", "0") else "")
            pieces = []
            for child in el.iter():
                if tag(child) not in CLAUSE_TAGS:
                    continue
                # Inner text only for wrappers to avoid duplicated parent+children.
                nested = any(tag(grandchild) in CLAUSE_TAGS for grandchild in child)
                text = clean(child.text if nested else "".join(child.itertext()))
                if text and text not in pieces:
                    pieces.append(text)
            if pieces:
                clauses[key] = " ".join(pieces)
        elif k in ("별표단위", "서식단위"):
            number = field(el, "별표번호") or field(el, "서식번호")
            title = field(el, "별표제목") or field(el, "서식제목")
            value = field(el, "별표내용") or field(el, "서식내용") or field(el, "본문내용")
            if value:
                key = ("별표 " if k == "별표단위" else "서식 ") + (number or str(len(clauses)+1))
                if title:
                    key += " (" + title + ")"
                clauses[key] = value
        elif k in ("조항", "자치법규조문"):
            number, value = field(el, "조문번호", True), field(el, "조내용", True)
            if number and value:
                clauses["제"+number+"조"] = value
    if not clauses:
        # Official AdmRulService XML commonly exposes multiple flat
        # <조문내용> elements directly, without a <조문단위> wrapper.
        flat = [html.unescape(clean("".join(node.itertext())))
                for node in root.iter() if tag(node) == "조문내용"]
        flat = list(dict.fromkeys(x for x in flat if x))
        for index, value in enumerate(flat, 1):
            match = re.search(r"^제\s*(\d+)\s*조(?:의\s*(\d+))?", value)
            key = ("제"+match.group(1)+"조"+
                   ("의"+match.group(2) if match.group(2) else "")
                   if match else "본문 "+str(index))
            if key in clauses:
                key += " ("+str(index)+")"
            clauses[key] = value
        if not clauses:
            fallback = [field(el, tag(el)) for el in root.iter()
                        if tag(el) in ("본문내용", "행정규칙본문") and
                        not any(tag(child) in CLAUSE_TAGS for child in el)]
            fallback = [html.unescape(x) for x in fallback if x]
            if fallback:
                clauses["본문"] = " ".join(dict.fromkeys(fallback))
    if clauses:
        addenda = [html.unescape(clean("".join(node.itertext())))
                   for node in root.iter() if tag(node) == "부칙내용"]
        if addenda:
            clauses["부칙"] = " ".join(dict.fromkeys(x for x in addenda if x))
    incomplete = [k for k, v in clauses.items() if not v or len(v) >= 15000 or
                  re.search(r"<\s*img\b|&lt;\s*img\b", v, re.I)]
    return {
        "status": "complete" if clauses and not incomplete and not links else "partial",
        "clauses": clauses,
        "attachment_links": links,
        "incomplete_keys": incomplete,
        "raw_xml_sha256": hash256(xml),
        "body_sha256": hash256(json.dumps(clauses, sort_keys=True, ensure_ascii=False)),
    }


def compare_bodies(before: dict, after: dict, *, annual=False) -> dict:
    a, b = before.get("clauses", {}), after.get("clauses", {})
    changes = []
    unresolved = []
    for clause in sorted(set(a) | set(b)):
        old, new = a.get(clause), b.get(clause)
        if old is None or new is None:
            unresolved.append({"clause": clause, "reason": "counterpart_not_verified"})
        elif old != new:
            changes.append({"clause": clause, "before": old, "after": new,
                            "before_hash": hash256(old), "after_hash": hash256(new)})
    if before.get("status") != "complete" or after.get("status") != "complete":
        unresolved.append({"reason": "incomplete_original_or_attachment"})
    from .tabular import compare_tables
    numeric_changes=compare_tables(before.get("numeric_tables",[]),
                                   after.get("numeric_tables",[]))
    return {
        "status": ("partial_unverified" if unresolved else
                   "changed" if changes else "no_text_change"),
        "relationship": "annual_successor" if annual else "same_official_id_revision",
        "changes": changes, "numeric_changes": numeric_changes,
        "unresolved": unresolved,
        "counts": {"changed": len(changes), "numeric": len(numeric_changes),
                   "unresolved": len(unresolved)},
    }


class OfficialAPI:
    def __init__(self, oc, transport=None):
        if not oc:
            raise ValueError("LAW_OC is required")
        self.oc, self.transport = oc, transport

    def request(self, endpoint, source, **params):
        query=urlencode({"OC": self.oc, "target": source, "type": "XML", **params})
        url = API + endpoint + "?" + query
        if self.transport:
            raw = self.transport(url)
        else:
            # The official service has intermittent runner-level connection
            # errors. Try both official HTTPS hostnames before a failure is
            # recorded in coverage; never silently mark the date as complete.
            urls=(url, "https://law.go.kr/DRF/" + endpoint + "?" + query)
            last=None
            for alternate in urls:
                for n in range(2):
                    try:
                        with urlopen(Request(alternate, headers={
                                "User-Agent":"Mozilla/5.0 (PolicyDominoUnified/2.0)",
                                "Accept":"application/xml,text/xml,*/*"}), timeout=13) as r:
                            raw=r.read(MAX_RESPONSE+1)
                        break
                    except (OSError, TimeoutError) as exc:
                        last=exc
                        if n==0:time.sleep(0.5)
                else:
                    continue
                break
            else:
                raise RuntimeError("official_api_network_error: "+
                    type(last).__name__+": "+str(last)[:130])
        if len(raw) > MAX_RESPONSE:
            raise ValueError("official_api_payload_too_large")
        root = ET.fromstring(raw)
        if tag(root).lower() in ("html", "error"):
            raise ValueError("official_api_error_document")
        if tag(root).lower() == "response":
            error = field(root, "msg") or field(root, "result")
            if error and not field(root, "totalCnt"):
                raise RuntimeError("official_api_access_error: " + error[:95])
        return root, raw

    def search(self, source, start, end, edition="1", kind="", max_pages=20,
               query=""):
        if source not in FIELDS:
            raise ValueError("Unsupported source")
        params = {FIELDS[source][4]: start.replace("-", "") +
                  "~" + end.replace("-", ""), "sort": "ddes", "display": 100}
        if source != "law":
            params["nw"] = edition
        if kind and source == "admrul":
            params["knd"] = kind
        if query:
            params["query"] = query
        found, reported, seen_pages = {}, None, 0
        for page in range(1, max_pages+1):
            root, _ = self.request("lawSearch.do", source, page=page, **params)
            count = field(root, "totalCnt")
            if not count.isdigit():
                raise ValueError("official_totalCnt_missing")
            if reported is not None and int(count) != reported:
                raise ValueError("official_totalCnt_changed_during_pagination")
            reported = int(count)
            rows = parse_index(root, source, kind)
            if page == 1 and reported > 1500 and start != end:
                return [], {"reported": reported, "collected": 0,
                            "pages": 1, "complete": False,
                            "error": "date_window_split_required"}
            if reported and not rows:
                raise ValueError("official_rows_not_parsed")
            for row in rows:
                if start <= row["published_at"] <= end:
                    found[ident(row)] = row
            seen_pages = page
            if reported == 0 or page*100 >= reported:
                return list(found.values()), {
                    "reported": reported, "collected": len(found),
                    "pages": seen_pages, "complete": len(found) == reported}
        return list(found.values()), {"reported": reported, "collected": len(found),
                                     "pages": seen_pages, "complete": False,
                                     "error": "pagination_limit"}

    def detail(self, record):
        param = FIELDS[record["source"]][5]
        root, xml = self.request("lawService.do", record["source"],
                                 **{param: record["serial"]})
        return xml

    def predecessor(self, record):
        src = record["source"]
        if src == "law":
            root, _ = self.request("lawSearch.do", "eflaw", LID=record["stable_id"],
                                   nw="1,2,3", page=1, display=100, sort="ddes")
        else:
            root, _ = self.request("lawSearch.do", src, query=record["title"],
                                   nw="2", page=1, display=100, sort="ddes")
        rows = parse_index(root, src)
        candidates = [r for r in rows if r["stable_id"] == record["stable_id"] and
                      (r["published_at"], r["serial"]) <
                      (record["published_at"], record["serial"])]
        if candidates:
            prior=max(candidates, key=lambda r: (r["published_at"], r["serial"]))
            annual=src=="admrul" and _effective_year(prior)>0 and (
                _effective_year(record)==_effective_year(prior)+1)
            return prior,annual
        if src == "admrul":
            m = YEAR.search(record["title"])
            if m:
                year = int(m.group()[:4])
                previous_title = record["title"][:m.start()] + str(year-1) + record["title"][m.start()+4:]
                for edition in ("1", "2"):
                    root, _ = self.request("lawSearch.do", "admrul",
                                           query=previous_title, nw=edition,
                                           page=1, display=100, sort="ddes")
                    prior = [r for r in parse_index(root, "admrul")
                             if r["title"] == previous_title and
                             r["published_at"] < record["published_at"] and
                             (not record.get("ministry") or
                              r.get("ministry") == record["ministry"])]
                    if prior:
                        return max(prior, key=lambda r: r["published_at"]), True
        # A renamed annual notice may have an entirely different official ID.
        # Search using distinctive title tokens without enrolling policy names.
        if src=="admrul" and _effective_year(record)>0:
            tokens=[t for t in re.findall(r"[가-힣]{3,}",record["title"])
                    if t not in ("기준", "고시", "제정", "개정", "년도")]
            tokens=sorted(set(tokens),key=len,reverse=True)[:3]
            for token in tokens:
                for edition in ("2","1"):
                    try:
                        root,_=self.request("lawSearch.do","admrul",query=token,
                                          nw=edition, page=1,display=100,sort="ddes")
                        pool=parse_index(root,"admrul")
                        candidate,annual=_local_predecessor(record,pool)
                        if candidate and annual:
                            return candidate,True
                    except (OSError,ValueError,RuntimeError):
                        continue
        return None, False


def verified_window(api, source: str, start: str, end: str,
                    edition: str, kind: str, query: str = "",
                    depth: int = 0, max_depth: int = 12,
                    deadline: float | None = None):
    """Split incomplete official result windows instead of abandoning page 1501+.

    Never mark a wide window complete merely because the first page succeeded.
    The exact split leaves are fully checked against official totalCnt.
    """
    if deadline is not None and time.monotonic() >= deadline:
        return [], {"reported": 0, "collected": 0,
                    "pages": 0, "complete": False,
                    "error": "collection_time_budget_deferred"}
    rows, info = api.search(source, start, end, edition, kind, query=query)
    if info.get("complete"):
        return rows, info
    if info.get("error") == "collection_time_budget_deferred":
        return rows, info
    if start >= end or depth >= max_depth:
        return rows, info
    # Request or parsing errors are raised by api.search; only incomplete
    # official pagination/count evidence is eligible for date bisection.
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    mid = a + (b - a) // 2
    if mid >= b:
        return rows, info
    left, left_info = verified_window(
        api, source, start, mid.isoformat(), edition, kind, query,
        depth + 1, max_depth, deadline)
    right, right_info = verified_window(
        api, source, (mid + dt.timedelta(days=1)).isoformat(), end,
        edition, kind, query, depth + 1, max_depth, deadline)
    unique = {ident(row): row for row in [*left, *right]}
    reported = int(left_info.get("reported") or 0) + int(
        right_info.get("reported") or 0)
    finished = (left_info.get("complete") is True and
                right_info.get("complete") is True and
                len(unique) == reported)
    return list(unique.values()), {
        "reported": reported, "collected": len(unique),
        "pages": int(left_info.get("pages") or 0) +
                 int(right_info.get("pages") or 0),
        "complete": finished, "subwindow_count":
            int(left_info.get("subwindow_count") or 1) +
            int(right_info.get("subwindow_count") or 1),
        "error": "" if finished else "subwindow_incomplete",
    }


def _windows(root, state, source, edition, kind, today):
    name = "|".join((source, edition, kind))
    start_recent = today - dt.timedelta(days=6)
    old_end = dt.date.fromisoformat(state.get("backfill", {}).get(
        name, (today - dt.timedelta(days=7)).isoformat()))
    first = old_end - dt.timedelta(days=13)
    return [
        (start_recent.isoformat(), today.isoformat(), "recent"),
        (first.isoformat(), old_end.isoformat(), "historical"),
    ]


def streams():
    return ([("admrul", "1", "3"), ("admrul", "2", "3"),
             ("law", "1", "")] +
            [(src, edition, kind)
             for src in ("admrul", "ordin")
             for edition in ("1", "2")
             for kind in (KINDS if src == "admrul" else ("",))
             if not (src == "admrul" and kind == "3")])


def process(api, root: Path, state: dict, record: dict) -> dict:
    destination = root / relative_path(record)
    existing = load(destination)
    # Archived extracted text is not proof of a complete official original.
    if (existing and existing.get("body", {}).get("status") == "complete"
            and existing.get("official_xml_base64")
            and not existing.get("source_snapshot_provenance")):
        return existing
    # Reuse already verified, immutable official XML for incomplete annex
    # recovery. Repeated network downloads are not required for this version.
    xml = None
    if existing and not existing.get("source_snapshot_provenance"):
        encoded = existing.get("official_xml_base64")
        try:
            saved = base64.b64decode(encoded, validate=True) if encoded else b""
            if saved and hash256(saved) == existing.get("body", {}).get("raw_xml_sha256"):
                xml = saved
        except (ValueError, TypeError):
            pass
    if xml is None:
        xml = api.detail(record)
    body = parse_body(xml)
    if body.get("attachment_links") and os.getenv(
            "PD_FETCH_OFFICIAL_ATTACHMENTS", "true").lower() == "true":
        from .attachments import resolve_attachments
        body = resolve_attachments(root, body,
                                   previous=existing.get("body") if existing else None)
    if (existing and body.get("status") != "complete"
            and existing.get("body", {}).get("clauses")):
        # Preserve an older extracted body in a separate immutable archive,
        # while retaining the newly retrieved official XML and all unresolved
        # annexes for later re-extraction. Neither source is lost or promoted.
        archive = root / "historic_extracts" / (
            hash256(ident(record))[:24] + ".json.gz")
        store(archive, existing)
    obj = {"identity": ident(record), "record": record, "body": body,
           "official_xml_base64": base64.b64encode(xml).decode("ascii"),
           "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    store(destination, obj)
    return obj


def _index_path(root: Path, source: str, edition: str, kind: str,
                start: str, end: str, stage: str) -> Path:
    key = "|".join((source, edition, kind, start, end, stage))
    return root / "indexes" / source / (hash256(key)[:24] + ".json.gz")


def _priority(rec: dict, today: dt.date) -> tuple:
    """Generic date/year priority, not a policy-name or institution whitelist."""
    target = today.year + 1
    years = [int(x[:4]) for x in YEAR.findall(rec.get("title", ""))]
    # YEAR.findall includes its whole 4-digit match when there are no captures.
    annual = any(y >= target for y in years)
    future = rec.get("effective_date", "") > today.isoformat()
    current = rec.get("published_at", "") >= (
        today - dt.timedelta(days=90)).isoformat()
    return (int(annual)*5 + int(future)*3 + int(current),
            rec.get("published_at", ""), rec.get("serial", ""))


def _effective_year(record: dict) -> int:
    value=str(record.get("effective_date") or "")[:4]
    if value.isdigit() and 1900<int(value)<2100:
        return int(value)
    match=YEAR.search(record.get("title", ""))
    return int(match.group()[:4]) if match else 0


def _annual_name_signature(title: str) -> set[str]:
    """Generic year-neutral bigrams for renamed annual official standards."""
    stripped = YEAR.sub("", str(title or ""))
    plain = re.sub(r"[^가-힣a-zA-Z0-9]", "", stripped)
    return {plain[i:i+2] for i in range(max(0,len(plain)-1))}


def _local_predecessor(record: dict, records: list[dict]):
    """Select only an unambiguous official predecessor.

    Different legal IDs may represent a later year's identical policy family.
    Require same issuing authority and kind, preceding year, strong title
    similarity and a gap to the runner-up; never infer changed amounts.
    """
    older = [x for x in records if x.get("source") == record.get("source") and
             x.get("published_at", "") < record.get("published_at", "") and
             x.get("serial") != record.get("serial")]
    same_id = [x for x in older if x.get("stable_id") == record.get("stable_id")]
    if same_id:
        previous=max(same_id,key=lambda x:(x.get("published_at",""),x.get("serial","")))
        return previous,(_effective_year(record)>0 and
                         _effective_year(record)==_effective_year(previous)+1)
    title = record.get("title", "")
    ministry = record.get("ministry", "")
    current_year=_effective_year(record)
    if not current_year or not ministry or record.get("source") != "admrul":
        return None,False
    basis = _annual_name_signature(title)
    if not basis:
        return None,False
    matches=[]
    for candidate in older:
        if (candidate.get("ministry") != ministry or
            candidate.get("kind") != record.get("kind")):
            continue
        previous_year=_effective_year(candidate)
        if previous_year != current_year-1:
            continue
        past = _annual_name_signature(candidate["title"])
        score = 2*len(basis & past)/max(1,len(basis)+len(past))
        if score >= .56:
            matches.append((score,candidate))
    matches.sort(key=lambda x:(x[0],x[1].get("published_at","")),reverse=True)
    if not matches or (len(matches)>1 and matches[0][0]-matches[1][0]<.12):
        return None,False
    return matches[0][1],True


def _pending_index_records(root: Path, max_files=15000) -> list[dict]:
    """Never lose official list results when per-run detail budget is exhausted."""
    pending = {}
    historic = sorted((root / "indexes" / "legacy").glob("*/*.json.gz"))
    live = sorted((root / "indexes").glob("*/*.json.gz"))[-max_files:]
    for path in [*historic, *live]:
        index = load(path, {})
        for record in index.get("records", []):
            if all(record.get(key) for key in ("source", "stable_id", "serial")):
                pending[ident(record)] = record  # Live evidence supersedes historic.
    return list(pending.values())


def run(root: Path, api: OfficialAPI, limit_streams=3, detail_budget=20,
        today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    state_file = root / "collection-state.json"
    state = load(state_file, {}) or {}
    for key in ("backfill", "coverage", "attempts", "errors", "last_detail_attempt"):
        state.setdefault(key, {})
    states = streams()
    offset = int(state.get("stream_offset", 0)) % len(states)
    schedule = (states[offset:] + states[:offset])[:min(len(states), limit_streams)]
    failed = 0
    started_at = time.monotonic()
    max_seconds = max(45.0, float(os.getenv("PD_COLLECTION_MAX_SECONDS", "420")))
    deadline = started_at + max_seconds
    # Reserve most of each run for detailed original recovery. Date-range
    # discovery must not consume the entire run before document validation.
    collection_deadline = started_at + max_seconds * .4
    collection_deferred = False
    connection_failures = 0
    network_unavailable = False

    def collect_window(source, edition, kind, start, end, stage, query=""):
        nonlocal failed, connection_failures, network_unavailable, collection_deferred
        if time.monotonic() >= collection_deadline:
            collection_deferred = True
            return False
        key = "|".join((source, edition, kind, start, end, stage))
        if network_unavailable:
            failed += 1
            state["coverage"][key] = {
                "source": source, "edition": edition, "kind": kind,
                "first": start, "last": end, "stage": stage,
                "query_year": query, "complete": False,
                "error": "official_api_unavailable_deferred"}
            save_json(state_file, state)
            return False
        try:
            records, info = verified_window(
                api, source, start, end, edition, kind, query=query,
                deadline=collection_deadline)
            if info.get("error") == "collection_time_budget_deferred":
                collection_deferred = True
                return False
            connection_failures = 0
            saved = {
                **info, "source": source, "edition": edition, "kind": kind,
                "first": start, "last": end, "stage": stage,
                "query_year": query, "checked_at": dt.datetime.now(
                    dt.timezone.utc).isoformat()}
            state["coverage"][key] = saved
            store(_index_path(root, source, edition, kind, start, end, stage),
                  {"coverage": saved, "records": records})
            if not info.get("complete"):
                failed += 1
            elif stage == "historical":
                state["backfill"]["|".join((source, edition, kind))] = (
                    dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
            return info.get("complete", False)
        except Exception as exc:
            failed += 1
            message = type(exc).__name__ + ": " + str(exc)[:150]
            if any(marker in message for marker in (
                    "official_api_network_error", "official_api_access_error",
                    "official_api_error_document")):
                connection_failures += 1
                if connection_failures >= 2:
                    network_unavailable = True
            else:
                connection_failures = 0
            state["coverage"][key] = {
                "source": source, "edition": edition, "kind": kind,
                "first": start, "last": end, "stage": stage,
                "query_year": query, "complete": False, "error": message}
            return False
        finally:
            save_json(state_file, state)

    # Failed page windows are retried explicitly, ahead of advancing backfill.
    prior_failures = [entry for entry in list(state["coverage"].values())
                      if isinstance(entry, dict) and entry.get("complete") is not True
                      and all(entry.get(k) for k in ("source", "edition", "first", "last"))]
    for win in prior_failures[:2]:
        collect_window(win["source"], win["edition"], win.get("kind", ""),
                       win["first"], win["last"], win.get("stage", "retry"),
                       win.get("query_year", ""))

    # One uniform index for all official source/date/kind streams.
    for source, edition, kind in schedule:
        for start, end, stage in _windows(root, state, source, edition, kind, today):
            collect_window(source, edition, kind, start, end, stage)

    # Annual announcements are sometimes issued many months before taking
    # effect. Search next-year notices across official administrative-rule
    # categories, without enrolling any policy title.
    annual_types = ["3", "1", "2", "4", "5", "6"]
    shift = int(state.get("annual_kind_offset", 0)) % len(annual_types)
    for kind in (annual_types[shift], annual_types[(shift+1) % len(annual_types)]):
        for edition in ("1", "2"):
            collect_window("admrul", edition, kind,
                           (today - dt.timedelta(days=540)).isoformat(),
                           today.isoformat(), "annual_forward",
                           str(today.year+1))
    state["annual_kind_offset"] = (shift+2) % len(annual_types)

    # Reuse metadata saved by EVERY prior run, not only the latest window.
    records = _pending_index_records(root)
    prioritized = sorted(records, key=lambda r: (
        -int(state["attempts"].get(ident(r), 0)), _priority(r, today)), reverse=True)
    if network_unavailable:
        state["stream_offset"] = (offset + len(schedule)) % len(states)
        state["last_run"] = today.isoformat()
        state["last_run_stats"] = {
            "detail_attempted": 0, "complete_originals_added": 0,
            "compared_pairs_processed": 0, "failed_windows": failed,
            "streams_checked": len(schedule),
            "pending_index_versions": len(records),
            "year_search_year": today.year + 1,
            "source_connection": "unavailable_deferred",
            "collection_elapsed_seconds": round(time.monotonic()-started_at,1)}
        save_json(state_file, state)
        return state["last_run_stats"]
    # Every run reserves work for older undigested versions, while prioritizing
    # recent standards. The capped per-run budget cannot erase the full queue.
    aged = sorted(records, key=lambda r: (
        int(state["attempts"].get(ident(r), 0)), r.get("published_at", ""), ident(r)))
    reserve = max(1, detail_budget // 4)
    selected = prioritized[:max(0, detail_budget-reserve)] + aged[:reserve] + prioritized + aged
    ordered, seen = [], set()
    for rec in selected:
        if ident(rec) not in seen:
            ordered.append(rec)
            seen.add(ident(rec))
    attempted, complete, compared = 0, 0, 0
    deadline_deferred = False

    def recover_one(rec):
        # Separate documents may be retrieved concurrently. Only the main
        # thread mutates the checkpoint ledger.
        after = process(api, root, state, rec)
        obtained = bool(after.get("body", {}).get("status") == "complete" and
                        after.get("official_xml_base64") and
                        not after.get("source_snapshot_provenance"))
        if not after.get("body", {}).get("clauses"):
            return obtained, False
        try:
            prev, annual = api.predecessor(rec)
        except (OSError, RuntimeError, ValueError):
            prev, annual = None, False
        if not prev:
            prev, annual = _local_predecessor(rec, records)
        if not prev:
            return obtained, False
        before = process(api, root, state, prev)
        result = compare_bodies(before["body"], after["body"], annual=annual)
        result["prior_record"] = prev
        result["changed_record"] = rec
        store(root / "comparisons" / (hash256(ident(rec))[:24] + ".json.gz"), result)
        return obtained, True

    # Three bounded workers recover independent official originals without
    # making every 13-second transport timeout block the entire pipeline.
    workers = min(3, max(1, detail_budget))
    cursor = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while cursor < len(ordered) and attempted < detail_budget:
            if time.monotonic() >= deadline:
                deadline_deferred = True
                break
            batch = []
            while cursor < len(ordered) and len(batch) < workers and attempted < detail_budget:
                rec = ordered[cursor]
                cursor += 1
                stored = load(root / relative_path(rec))
                if (stored and stored.get("body", {}).get("status") == "complete"
                        and stored.get("official_xml_base64")
                        and not stored.get("source_snapshot_provenance")):
                    continue
                attempted += 1
                state["attempts"][ident(rec)] = int(state["attempts"].get(ident(rec), 0)) + 1
                state["last_detail_attempt"][ident(rec)] = dt.datetime.now(
                    dt.timezone.utc).isoformat()
                batch.append(rec)
            if not batch:
                continue
            save_json(state_file, state)
            futures = {pool.submit(recover_one, rec): rec for rec in batch}
            for future in as_completed(futures):
                rec = futures[future]
                try:
                    original_ok, comparison_ok = future.result()
                    complete += int(original_ok)
                    compared += int(comparison_ok)
                    state["errors"].pop(ident(rec), None)
                except Exception as exc:
                    state["errors"][ident(rec)] = type(exc).__name__ + ": " + str(exc)[:150]
                finally:
                    save_json(state_file, state)
    if cursor < len(ordered) and time.monotonic() >= deadline:
        deadline_deferred = True
    state["stream_offset"] = (offset + len(schedule)) % len(states)
    state["last_run"] = today.isoformat()
    state["last_run_stats"] = {
        "detail_attempted": attempted, "complete_originals_added": complete,
        "compared_pairs_processed": compared,
        "failed_windows": failed, "streams_checked": len(schedule),
        "pending_index_versions": len(records),
        "year_search_year": today.year+1,
        "time_budget_deferred": deadline_deferred or collection_deferred,
        "collection_elapsed_seconds": round(time.monotonic()-started_at,1),
    }
    save_json(state_file, state)
    return state["last_run_stats"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--streams", type=int, default=3)
    p.add_argument("--details", type=int, default=20)
    args = p.parse_args()
    oc = os.getenv("LAW_OC", "").strip()
    result = run(args.root, OfficialAPI(oc), max(1, args.streams), max(1, args.details))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
