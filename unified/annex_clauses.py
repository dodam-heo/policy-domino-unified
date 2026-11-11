"""Recover image tables only from matching clauses in the same official HWPX."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET


def hwpx_sections(raw):
    lines=[]
    def local(n): return n.tag.rsplit('}',1)[-1]
    def walk(node):
        if local(node)=='tbl':
            rows=[]
            for row in node:
                if local(row)!='tr': continue
                cells=[' '.join(t.text or '' for t in cell.iter() if local(t)=='t').strip()
                       for cell in row if local(cell)=='tc']
                if any(cells): rows.append(' | '.join(cells))
            if rows: lines.append('공식 표:\n'+'\n'.join(rows))
            return
        if local(node)=='t' and node.text: lines.append(node.text)
        for child in node: walk(child)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=sorted((n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)),
                     key=lambda n:int(re.search(r'section(\d+)',n).group(1)))
        for name in names: walk(ET.fromstring(z.read(name)))
    text='\n'.join(lines)
    # Only actual article starts, not citations within sentences.
    parts=re.split(r'(?m)^(?=제\s*\d+\s*조(?:의\s*\d+)?\s*\()',text)
    out={}
    for part in parts:
        m=re.match(r'제\s*(\d+)\s*조(?:의\s*(\d+))?',part)
        if m:
            key='제'+m[1]+'조'+('의'+m[2] if m[2] else '')
            out.setdefault(key,[]).append(part.strip())
    return out


def recover(clauses, incomplete, raw):
    candidates=hwpx_sections(raw)
    recovered={}
    norm=lambda s: re.sub(r'[^0-9a-zA-Z가-힣]', '', s)
    for key in incomplete:
        original=clauses.get(key,'')
        chunks=re.split(r'<\s*img\b[^>]*>\s*(?:</img\s*>)?',original,flags=re.I)
        images=len(chunks)-1
        matches=candidates.get(key,[])
        if not images or len(matches)!=1: continue
        candidate=matches[0]
        if candidate.count('공식 표:\n')!=images or len(candidate)>=15000: continue
        target=norm(candidate); cursor=0
        for chunk in chunks:
            needle=norm(chunk)
            if not needle: continue
            pos=target.find(needle,cursor)
            if pos<0: break
            cursor=pos+len(needle)
        else:
            recovered[key]=candidate
    return recovered
