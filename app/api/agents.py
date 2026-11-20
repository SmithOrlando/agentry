import sqlite3

from flask import g, jsonify

from ..db import execute, insert, jdump, update, utcnow
from ..llm import router
from ..security import role_required
from ..services import agents as agents_svc
from ..services.settings import audit
from . import body, bp, err, ws

EDITABLE = {"name", "description", "color", "instructions", "active", "model_override"}


@bp.get("/agents")
@role_required("viewer")
def agents_list():
    rows = agents_svc.list_agents(ws())
    for a in rows:
        a["active_model"] = router.describe_active_model(ws(), {**a, "model_override": jdump(a["model_override"])
                                                                if a["model_override"] else None})
    return jsonify(agents=rows, templates=list(agents_svc.TEMPLATES))


@bp.post("/agents")
@role_required("admin")
def agents_create():
    d = body()
    tpl = agents_svc.TEMPLATES.get(d.get("template") or "")
    if tpl and not d.get("name"):
        d["name"] = d["template"]
    if tpl:
        d.setdefault("description", tpl[0]); d.setdefault("color", tpl[1]); d.setdefault("instructions", tpl[2])
    if not (d.get("name") or "").strip():
        return err("Name is required")
    try:
        aid = insert("agents", agents_svc.agent_row(ws(), d))
    except sqlite3.IntegrityError:
        return err("An agent with this name already exists", 409)
    audit(ws(), g.user["id"], "created agent", d["name"])
    return jsonify(id=aid), 201


@bp.patch("/agents/<int:aid>")
@role_required("admin")
def agents_update(aid):
    if not agents_svc.get_agent(ws(), aid):
        return err("not found", 404)
    d = {k: v for k, v in body().items() if k in EDITABLE}
    if "active" in d:
        d["active"] = 1 if d["active"] else 0
    if "model_override" in d:
        d["model_override"] = jdump(d["model_override"]) if d["model_override"] else None
    d["updated_at"] = utcnow()
    try:
        update("agents", aid, d)
    except sqlite3.IntegrityError:
        return err("An agent with this name already exists", 409)
    audit(ws(), g.user["id"], "updated agent", str(aid))
    return jsonify(ok=True)


@bp.delete("/agents/<int:aid>")
@role_required("admin")
def agents_delete(aid):
    a = agents_svc.get_agent(ws(), aid)
    if not a:
        return err("not found", 404)
    execute("DELETE FROM agents WHERE id = ?", [aid])
    audit(ws(), g.user["id"], "deleted agent", a["name"])
    return jsonify(ok=True)
