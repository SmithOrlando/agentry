"""Chunking and keyword retrieval (BM25).

BM25 needs no embedding model or vector database, works offline, and handles
mixed English/Spanish/Chinese text (CJK is indexed as character bigrams).
It is a good default for FAQ-style business documents. To upgrade to vector
search, keep the `search()` signature and swap the implementation — see
docs/MAINTENANCE.md › "Upgrading retrieval to embeddings".
"""
from __future__ import annotations

import math
import re
from collections import Counter

from ..db import query

_WORD = re.compile(r"[a-z0-9áéíóúñüàèìòùâêîôûäëïöç]+", re.I)
_CJK = re.compile(r"[㐀-鿿]+")
_STOP = set("""a an the and or of to in on for is are was were be been it this that with as at by from
de la el los las y o en un una que por para con es se del al lo""".split())


def tokenize(text: str) -> list[str]:
    text = text.lower()
    toks = [w for w in _WORD.findall(text) if w not in _STOP and len(w) > 1]
    for run in _CJK.findall(text):
        toks.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return toks


def chunk_sections(sections: list[tuple[str, str]], size: int = 900, overlap: int = 120):
    """Split each section into ~size-character chunks on paragraph/sentence
    boundaries, carrying `overlap` characters between neighbours."""
    out = []
    for locator, text in sections:
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
        buf = ""
        for p in paras:
            pieces = [p] if len(p) <= size else re.split(r"(?<=[.!?。！？])\s+", p)
            for piece in pieces:
                while len(piece) > size:  # hard split very long runs
                    out.append((locator, (buf + " " + piece[:size]).strip()))
                    buf, piece = "", piece[size - overlap:]
                if len(buf) + len(piece) + 1 > size and buf:
                    out.append((locator, buf.strip()))
                    buf = buf[-overlap:] + " " + piece
                else:
                    buf = f"{buf} {piece}" if buf else piece
        if buf.strip():
            out.append((locator, buf.strip()))
    return out


def search(workspace_id: int, agent_id: int | None, text: str, k: int = 4) -> list[dict]:
    """Top-k chunks from files assigned to the agent (all workspace files when
    agent_id is None). Returns dicts with text, filename, locator, score."""
    if agent_id is None:
        rows = query("SELECT c.id, c.text, c.locator, f.filename FROM chunks c "
                     "JOIN knowledge_files f ON f.id = c.file_id "
                     "WHERE c.workspace_id = ? AND f.status = 'ready'", [workspace_id])
    else:
        rows = query("SELECT c.id, c.text, c.locator, f.filename FROM chunks c "
                     "JOIN knowledge_files f ON f.id = c.file_id "
                     "JOIN agent_files af ON af.file_id = f.id "
                     "WHERE c.workspace_id = ? AND af.agent_id = ? AND f.status = 'ready'",
                     [workspace_id, agent_id])
    q = tokenize(text)
    if not rows or not q:
        return []
    docs = [tokenize(r["text"]) for r in rows]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n or 1
    df = Counter(t for d in docs for t in set(d))
    k1, b = 1.5, 0.75
    scored = []
    for row, d in zip(rows, docs):
        tf = Counter(d)
        score = 0.0
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        if score > 0:
            scored.append({**row, "score": round(score, 3)})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:k]
