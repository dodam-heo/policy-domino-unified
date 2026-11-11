"""Retrieve and archive official PDF/DOCX annex contents safely.

HWP and scan-only files are archived as unresolved evidence, never treated as
verified numeric comparison. XML annex text is handled by the core parser.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import io
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

BASE = "https://www.law.go.kr/LSW/"
MAX_ATTACHMENT_BYTES = 12_000_000


def normalized_url(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    full = urljoin(BASE, raw)
    parsed = urlparse(full)
    host = (parsed.hostname or "").lower()
    if (host not in ("law.go.kr", "www.law.go.kr") or
        parsed.username or parsed.password or
        parsed.scheme not in ("http", "https")):
        return ""
    # The official API itself emits http://law.go.kr/flDownload.do links.
    # Safely upgrade only this allowlisted official origin to HTTPS.
    if parsed.scheme == "http":
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed)


def fetch(url: str, transport=None):
    if transport:
        result = transport(url)
        if not isinstance(result, bytes):
            raise TypeError("Attachment transport must return bytes")
        return result
    with urlopen(Request(url, headers={
        "User-Agent": "PolicyDominoUnified/1.0",
        "Accept": "application/pdf,application/octet-stream,*/*"}), timeout=20) as response:
        if not normalized_url(response.geturl()):
            raise ValueError("Attachment redirected outside official law portal")
        return response.read(MAX_ATTACHMENT_BYTES+1)


def pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(raw), strict=False)
    return "\n".join((page.extract_text() or "") for page in pdf.pages[:80]).strip()


def docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as doc:
        if "word/document.xml" not in doc.namelist():
            return ""
        root = ET.fromstring(doc.read("word/document.xml"))
        paragraphs = []
        for node in root.iter():
            if node.tag.endswith("}p"):
                p = " ".join(t.text or "" for t in node.iter()
                             if t.tag.endswith("}t"))
                if p.strip():
                    paragraphs.append(p)
        return "\n".join(paragraphs)


def _format(raw: bytes) -> str:
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        return "docx" if b"word/" in raw[:50000] else "zip_other"
    if raw[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        return "hwp_ole"
    return "unknown"


def resolve_attachments(root: Path, original: dict,
                        transport=None, max_links: int=8) -> dict:
    links = original.get("attachment_links") or []
    if not links:
        return original
    clauses = dict(original.get("clauses") or {})
    records, unresolved = [], []
    for n, rawurl in enumerate(links):
        url = normalized_url(rawurl)
        row = {"index": n+1, "source_url": url or str(rawurl)[:120],
               "verified_text": False}
        if not url:
            row["reason"] = "non_official_or_invalid_attachment_url"
            unresolved.append(row)
            records.append(row)
            continue
        if n >= max_links:
            row["reason"] = "deferred_attachment_budget"
            unresolved.append(row)
            continue
        try:
            data = fetch(url, transport)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise ValueError("official_attachment_too_large")
            fmt = _format(data)
            sha = hashlib.sha256(data).hexdigest()
            dest = root/"attachments"/sha[:2]/(sha+".gz")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                tmp = dest.with_suffix(".tmp")
                tmp.write_bytes(gzip.compress(data, mtime=0))
                tmp.replace(dest)
            row.update({"sha256": sha, "format": fmt, "size": len(data)})
            if fmt == "pdf":
                text = pdf_text(data)
            elif fmt == "docx":
                text = docx_text(data)
            else:
                text = ""
            text = re.sub(r"[ \t]+", " ", text)
            # Image-backed, unsupported HWP and unreadable tables stay partial.
            if len(text.strip()) < 100:
                row["reason"] = "insufficient_verified_extractable_text"
                unresolved.append(row)
                continue
            clauses["첨부 "+str(n+1)] = text[:15000]
            row.update({"verified_text": True, "text_sha256":
                hashlib.sha256(text.encode("utf8")).hexdigest()})
        except Exception as exc:
            row["reason"] = type(exc).__name__+": "+str(exc)[:100]
            unresolved.append(row)
        finally:
            records.append(row)
    return {
        **original, "clauses": clauses,
        "attachments": records, "unresolved_attachments": unresolved,
        "body_sha256": hashlib.sha256(json.dumps(
            clauses, ensure_ascii=False, sort_keys=True).encode("utf8")).hexdigest(),
        "status": "complete" if clauses and not unresolved and
                    not original.get("incomplete_keys") else "partial",
    }
