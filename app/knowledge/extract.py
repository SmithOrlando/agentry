"""Turn uploaded files into plain text sections: [(locator, text), ...].

Locator is a short human pointer shown as a citation ("p.2", "Sheet1").
"""
from __future__ import annotations

import csv
import io
import ipaddress
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

SUPPORTED = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".csv": "csv", ".txt": "txt", ".md": "md"}


class ExtractionError(Exception):
    pass


def kind_for(filename: str) -> str | None:
    return SUPPORTED.get(Path(filename).suffix.lower())


def extract(path: Path, kind: str) -> list[tuple[str, str]]:
    fn = {"pdf": _pdf, "docx": _docx, "xlsx": _xlsx, "csv": _csv, "txt": _text, "md": _text,
          "qa": _text, "url": _text}.get(kind)
    if not fn:
        raise ExtractionError(f"unsupported file type: {kind}")
    sections = [(loc, t.strip()) for loc, t in fn(path) if t and t.strip()]
    if not sections:
        if kind == "pdf":
            raise ExtractionError("Scanned PDF — no text layer found (OCR is not configured)")
        raise ExtractionError("No text found in file")
    return sections


def _pdf(path):
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf raises many types
        raise ExtractionError(f"Could not open PDF: {exc}") from exc
    for i, page in enumerate(reader.pages, start=1):
        try:
            yield f"p.{i}", page.extract_text() or ""
        except Exception:
            continue


def _docx(path):
    import docx
    d = docx.Document(str(path))
    heading, buf = "", []
    for p in d.paragraphs:
        if p.style is not None and p.style.name.lower().startswith("heading") and p.text.strip():
            if buf:
                yield heading or "body", "\n".join(buf)
                buf = []
            heading = p.text.strip()[:60]
        elif p.text.strip():
            buf.append(p.text)
    if buf:
        yield heading or "body", "\n".join(buf)
    for t_i, table in enumerate(d.tables, start=1):
        rows = [" | ".join(c.text.strip() for c in r.cells) for r in table.rows]
        yield f"table {t_i}", "\n".join(rows)


def _xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(h).strip() if h is not None else f"col{i+1}" for i, h in enumerate(rows[0])]
        lines = []
        for r in rows[1:]:
            pairs = [f"{header[i]}: {v}" for i, v in enumerate(r) if v not in (None, "") and i < len(header)]
            if pairs:
                lines.append("; ".join(pairs))
        yield ws.title, "\n".join(lines)


def _csv(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    reader = list(csv.reader(io.StringIO(raw)))
    if not reader:
        return
    header = reader[0]
    lines = ["; ".join(f"{header[i] if i < len(header) else i}: {v}" for i, v in enumerate(r) if v)
             for r in reader[1:]]
    yield "rows", "\n".join(lines)


def _text(path):
    yield "text", path.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------ website sources
class _TextHTML(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip, self.title = [], 0, ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def _is_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def fetch_url_text(url: str, allow_private: bool = False, timeout: int = 15) -> tuple[str, str]:
    """Fetch one web page and return (title, text). Blocks internal addresses (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ExtractionError("URL must start with http:// or https://")
    if not allow_private and _is_private(parsed.hostname):
        raise ExtractionError("That address is not allowed")
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "AgentryBot/1.0"},
                            allow_redirects=False)
    except requests.RequestException as exc:
        raise ExtractionError(f"Could not fetch page: {exc.__class__.__name__}") from exc
    if resp.status_code >= 300:
        raise ExtractionError(f"Page returned HTTP {resp.status_code}")
    parser = _TextHTML()
    parser.feed(resp.text[:2_000_000])
    text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
    if not text:
        raise ExtractionError("No readable text on that page")
    return parser.title.strip() or parsed.hostname, text
