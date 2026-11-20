"""Knowledge files: save upload -> background indexing -> chunks."""
from __future__ import annotations

import secrets
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from ..db import execute, get_db, insert, query, query_one, update, utcnow
from ..knowledge.extract import ExtractionError, extract, fetch_url_text, kind_for
from ..knowledge.retrieval import chunk_sections
from ..worker import enqueue


def _storage_dir(workspace_id: int) -> Path:
    d = Path(current_app.config["UPLOAD_DIR"]) / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_files(workspace_id: int) -> list[dict]:
    files = query("SELECT id, filename, kind, source_url, size_bytes, status, error, chunk_count, "
                  "created_at, updated_at FROM knowledge_files WHERE workspace_id = ? ORDER BY id DESC",
                  [workspace_id])
    links = query("SELECT af.file_id, a.id AS agent_id, a.name FROM agent_files af "
                  "JOIN agents a ON a.id = af.agent_id WHERE a.workspace_id = ?", [workspace_id])
    by_file: dict[int, list] = {}
    for l in links:
        by_file.setdefault(l["file_id"], []).append({"id": l["agent_id"], "name": l["name"]})
    for f in files:
        f["agents"] = by_file.get(f["id"], [])
    return files


def _valid_agent_ids(workspace_id: int, agent_ids) -> list[int]:
    ids = [int(a) for a in (agent_ids or []) if str(a).isdigit()]
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = query(f"SELECT id FROM agents WHERE workspace_id = ? AND id IN ({marks})", [workspace_id, *ids])
    return [r["id"] for r in rows]


def set_agents(workspace_id: int, file_id: int, agent_ids) -> None:
    ids = _valid_agent_ids(workspace_id, agent_ids)
    db = get_db()
    db.execute("DELETE FROM agent_files WHERE file_id = ?", [file_id])
    db.executemany("INSERT INTO agent_files (agent_id, file_id) VALUES (?, ?)", [(a, file_id) for a in ids])
    db.commit()


def _create(workspace_id, filename, kind, stored_path, size, agent_ids, source_url=None) -> int:
    now = utcnow()
    fid = insert("knowledge_files", {"workspace_id": workspace_id, "filename": filename, "kind": kind,
                                     "source_url": source_url, "stored_path": str(stored_path),
                                     "size_bytes": size, "status": "pending", "created_at": now,
                                     "updated_at": now})
    set_agents(workspace_id, fid, agent_ids)
    enqueue(index_file, fid)
    return fid


def add_upload(workspace_id: int, storage, agent_ids) -> int:
    original = storage.filename or "file"
    kind = kind_for(original)
    if not kind:
        raise ExtractionError("Unsupported file type. Use PDF, DOCX, XLSX, CSV, TXT or MD.")
    safe = secure_filename(original) or f"file.{kind}"
    path = _storage_dir(workspace_id) / f"{secrets.token_hex(6)}_{safe}"
    storage.save(path)
    return _create(workspace_id, original, kind, path, path.stat().st_size, agent_ids)


def add_text(workspace_id: int, title: str, text: str, agent_ids) -> int:
    path = _storage_dir(workspace_id) / f"{secrets.token_hex(6)}_qa.md"
    path.write_text(text, encoding="utf-8")
    return _create(workspace_id, title or "Quick Q&A", "qa", path, len(text.encode()), agent_ids)


def add_url(workspace_id: int, url: str, agent_ids) -> int:
    # Fetch happens in the worker so the request returns fast.
    path = _storage_dir(workspace_id) / f"{secrets.token_hex(6)}_url.txt"
    return _create(workspace_id, url, "url", path, 0, agent_ids, source_url=url)


def index_file(file_id: int) -> None:
    """Background job: extract -> chunk -> replace chunks. Safe to re-run."""
    f = query_one("SELECT * FROM knowledge_files WHERE id = ?", [file_id])
    if not f:
        return
    update("knowledge_files", file_id, {"status": "indexing", "error": None, "updated_at": utcnow()})
    try:
        path = Path(f["stored_path"])
        if f["kind"] == "url":
            title, text = fetch_url_text(f["source_url"], current_app.config["ALLOW_PRIVATE_URL_FETCH"])
            path.write_text(text, encoding="utf-8")
            update("knowledge_files", file_id, {"filename": f"{title} ({f['source_url']})"[:200],
                                                "size_bytes": len(text.encode())})
        sections = extract(path, f["kind"])
        chunks = chunk_sections(sections, current_app.config["CHUNK_SIZE"], current_app.config["CHUNK_OVERLAP"])
        db = get_db()
        db.execute("DELETE FROM chunks WHERE file_id = ?", [file_id])
        db.executemany("INSERT INTO chunks (file_id, workspace_id, ordinal, locator, text) VALUES (?,?,?,?,?)",
                       [(file_id, f["workspace_id"], i, loc, txt) for i, (loc, txt) in enumerate(chunks)])
        db.commit()
        update("knowledge_files", file_id, {"status": "ready", "chunk_count": len(chunks), "updated_at": utcnow()})
    except ExtractionError as exc:
        update("knowledge_files", file_id, {"status": "failed", "error": str(exc), "updated_at": utcnow()})
    except Exception as exc:  # unexpected: keep the message short for the UI, full trace in logs
        current_app.logger.exception("indexing file %s failed", file_id)
        update("knowledge_files", file_id, {"status": "failed", "error": f"Indexing error: {exc.__class__.__name__}",
                                            "updated_at": utcnow()})


def delete_file(workspace_id: int, file_id: int) -> bool:
    f = query_one("SELECT stored_path FROM knowledge_files WHERE id = ? AND workspace_id = ?", [file_id, workspace_id])
    if not f:
        return False
    execute("DELETE FROM knowledge_files WHERE id = ?", [file_id])
    try:
        if f["stored_path"]:
            Path(f["stored_path"]).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("could not remove %s", f["stored_path"])
    return True
