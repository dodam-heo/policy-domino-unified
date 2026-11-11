"""Read-only real-law.gov.kr acceptance probe.

The three regression document serials are TEST FIXTURES, not production
collector targeting rules. Emit only official metadata and failure reasons.
"""
from __future__ import annotations
from collections import Counter
import datetime as dt
import json
import os
from .engine import OfficialAPI, parse_body, field, tag
import xml.etree.ElementTree as ET

CASES = (
    ("2027 median-income standard", "2100000283464", "2026-07-29"),
    ("2027 housing-benefit threshold", "2100000284670", "2026-08-31"),
    ("2027 education-benefit threshold", "2100000285242", "2026-09-18"),
)


def main():
    api = OfficialAPI(os.getenv("LAW_OC", "dori"))
    success=0
    for label,serial,date in CASES:
        print("CASE",label,serial,flush=True)
        try:
            doc={"source":"admrul","serial":serial}
            raw=api.detail(doc)
            root=ET.fromstring(raw)
            body=parse_body(raw)
            print("BODY",json.dumps({
                "serial":serial,"root":tag(root),"xml_bytes":len(raw),
                "title":field(root,"행정규칙명")[:120],
                "clauses":len(body["clauses"]),"attachments":len(body["attachment_links"]),
                "body_status":body["status"],
                "unresolved_keys":body["incomplete_keys"][:5],
            },ensure_ascii=False),flush=True)
            details=[(tag(x), len((x.text or "").strip()), (x.text or "").strip()[:100])
                     for x in root.iter() if tag(x) in (
                       "조문내용","본문내용","행정규칙본문","부칙내용",
                       "별표서식PDF파일링크","별표서식파일링크",
                       "첨부파일링크","별표내용","조문형식여부")]
            print("XML_FIELDS",serial,json.dumps(details[:15],ensure_ascii=False),flush=True)
            print("LINKS",serial,json.dumps(body["attachment_links"][:3],ensure_ascii=False),flush=True)
            if body["attachment_links"]:
                from pathlib import Path
                from .attachments import resolve_attachments
                resolved=resolve_attachments(Path("/tmp/policy-live-annex"),body,max_links=3)
                print("ATTACHMENTS",serial,json.dumps(
                    resolved.get("attachments",[]),ensure_ascii=False)[:2300],flush=True)
                import gzip,io,zipfile
                for attachment in resolved.get("attachments",[]):
                    if attachment.get("format")=="zip_other" and attachment.get("sha256"):
                        sha=attachment["sha256"]
                        archive=Path("/tmp/policy-live-annex")/"attachments"/sha[:2]/(sha+".gz")
                        try:
                            with zipfile.ZipFile(io.BytesIO(gzip.decompress(archive.read_bytes()))) as package:
                                print("ZIP_MEMBERS",serial,package.namelist()[:22],flush=True)
                        except Exception as exc:
                            print("ZIP_INSPECT_ERROR",type(exc).__name__,str(exc)[:100],flush=True)
                print("EXTRACT",serial,"clauses",len(resolved.get("clauses",{})),
                      "status",resolved.get("status"),flush=True)
            if len(body["clauses"]) or body["attachment_links"]:
                success+=1
            else:
                print("BODY_MISSING",serial,"extractor or source detail returned no clauses",flush=True)
        except Exception as e:
            print("DETAIL_FAILED",serial,type(e).__name__,str(e)[:220],flush=True)
        for edition in ("1","2"):
            try:
                found,ledger=api.search("admrul",date,date,edition,"3",max_pages=12)
                matched=[row for row in found if row["serial"]==serial]
                print("INDEX",json.dumps({"serial":serial,"edition":edition,
                      "reported":ledger["reported"],"collected":ledger["collected"],
                      "complete":ledger["complete"],"matched":len(matched)},
                      ensure_ascii=False),flush=True)
            except Exception as e:
                print("INDEX_FAILED",serial,edition,type(e).__name__,str(e)[:220],flush=True)
    print("LIVE_BODY_SUCCESSES",success,"/",len(CASES),flush=True)
    if not success:
        raise SystemExit("None of the three official notice bodies were extractable")


if __name__=="__main__":
    main()
