from flask import g, jsonify, request

from ..db import query_one, update, utcnow
from ..knowledge.extract import ExtractionError
from ..security import role_required
from ..services import knowledge as ksvc
from ..services.settings import audit
from ..worker import enqueue
from . import body, bp, err, ws


@bp.get("/knowledge/files")
@role_required("viewer")
def k_list():
    files = ksvc.list_files(ws())
    return jsonify(files=files, total_chunks=sum(f["chunk_count"] for f in files))


@bp.post("/knowledge/files")
@role_required("supervisor")
def k_upload():
    uploads = request.files.getlist("files")
    if not uploads:
        return err("Choose at least one file")
    agent_ids = request.form.getlist("agent_ids")
    created, errors = [], []
    for f in uploads:
        try:
            created.append(ksvc.add_upload(ws(), f, agent_ids))
        except ExtractionError as exc:
            errors.append({"file": f.filename, "error": str(exc)})
    if created:
        audit(ws(), g.user["id"], "uploaded knowledge", f"{len(created)} file(s)")
    return jsonify(created=created, errors=errors), (201 if created else 400)


@bp.post("/knowledge/text")
@role_required("supervisor")
def k_text():
    d = body()
    if not (d.get("text") or "").strip():
        return err("Text is empty")
    fid = ksvc.add_text(ws(), d.get("title") or "Quick Q&A", d["text"], d.get("agent_ids"))
    return jsonify(id=fid), 201


@bp.post("/knowledge/url")
@role_required("supervisor")
def k_url():
    d = body()
    url = (d.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return err("Enter a full URL starting with https://")
    fid = ksvc.add_url(ws(), url, d.get("agent_ids"))
    return jsonify(id=fid), 201


@bp.patch("/knowledge/files/<int:fid>")
@role_required("supervisor")
def k_update(fid):
    if not query_one("SELECT id FROM knowledge_files WHERE id = ? AND workspace_id = ?", [fid, ws()]):
        return err("not found", 404)
    d = body()
    if "agent_ids" in d:
        ksvc.set_agents(ws(), fid, d["agent_ids"])
    return jsonify(ok=True)


@bp.post("/knowledge/files/<int:fid>/reindex")
@role_required("supervisor")
def k_reindex(fid):
    if not query_one("SELECT id FROM knowledge_files WHERE id = ? AND workspace_id = ?", [fid, ws()]):
        return err("not found", 404)
    update("knowledge_files", fid, {"status": "pending", "updated_at": utcnow()})
    enqueue(ksvc.index_file, fid)
    return jsonify(ok=True)


@bp.delete("/knowledge/files/<int:fid>")
@role_required("supervisor")
def k_delete(fid):
    if not ksvc.delete_file(ws(), fid):
        return err("not found", 404)
    audit(ws(), g.user["id"], "deleted knowledge file", str(fid))
    return jsonify(ok=True)
