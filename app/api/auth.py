from flask import current_app, g, jsonify, session

from ..db import insert, jdump, query_one, update, utcnow
from ..security import check_password, csrf_token, hash_password, login_required
from ..services.agents import TEMPLATES
from ..services.settings import DEFAULT_HOURS, audit
from . import body, bp, err


def _login(user_id: int):
    session.clear()
    session["uid"] = user_id
    session.permanent = True
    csrf_token()
    update("users", user_id, {"last_active_at": utcnow()})


@bp.post("/auth/register")
def register():
    """Create a workspace and its owner. With an invite token, join instead."""
    d = body()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    name = (d.get("name") or "").strip() or email.split("@")[0]
    if "@" not in email or len(password) < 8:
        return err("Enter a valid email and a password of at least 8 characters")
    if query_one("SELECT id FROM users WHERE email = ?", [email]):
        return err("An account with this email already exists", 409)
    token = d.get("invite_token")
    if token:
        inv = query_one("SELECT * FROM invites WHERE token = ? AND accepted_at IS NULL", [token])
        if not inv or inv["email"].lower() != email:
            return err("This invite is invalid or was already used", 400)
        uid = insert("users", {"workspace_id": inv["workspace_id"], "email": email, "name": name,
                               "password_hash": hash_password(password), "role": inv["role"],
                               "created_at": utcnow()})
        update("invites", inv["id"], {"accepted_at": utcnow()})
        audit(inv["workspace_id"], uid, "joined workspace", email)
    else:
        if not current_app.config["ALLOW_REGISTRATION"]:
            return err("Registration is closed", 403)
        wsid = insert("workspaces", {"name": (d.get("workspace") or f"{name}'s workspace").strip(),
                                     "business_hours": jdump(DEFAULT_HOURS), "created_at": utcnow(),
                                     "away_message": "Thanks for your message! We're closed right now and will reply when we open."})
        uid = insert("users", {"workspace_id": wsid, "email": email, "name": name,
                               "password_hash": hash_password(password), "role": "owner",
                               "created_at": utcnow()})
        now = utcnow()
        for tname, (desc, color, instr) in TEMPLATES.items():  # starter agents
            insert("agents", {"workspace_id": wsid, "name": tname, "description": desc, "color": color,
                              "instructions": instr, "active": 1, "created_at": now, "updated_at": now})
        audit(wsid, uid, "created workspace")
    _login(uid)
    return jsonify(ok=True)


@bp.post("/auth/login")
def login():
    d = body()
    user = query_one("SELECT * FROM users WHERE email = ?", [(d.get("email") or "").strip().lower()])
    if not user or not check_password(user["password_hash"], d.get("password") or ""):
        return err("Wrong email or password", 401)
    _login(user["id"])
    return jsonify(ok=True)


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.post("/auth/password")
@login_required
def change_password():
    d = body()
    user = query_one("SELECT * FROM users WHERE id = ?", [g.user["id"]])
    if not check_password(user["password_hash"], d.get("current") or ""):
        return err("Current password is wrong", 403)
    if len(d.get("new") or "") < 8:
        return err("New password must be at least 8 characters")
    update("users", user["id"], {"password_hash": hash_password(d["new"])})
    audit(g.workspace_id, user["id"], "changed password")
    return jsonify(ok=True)


@bp.get("/me")
@login_required
def me():
    ws = query_one("SELECT id, name FROM workspaces WHERE id = ?", [g.workspace_id])
    return jsonify(user=g.user, workspace=ws, csrf=csrf_token(), setup=setup_status(g.workspace_id))


def setup_status(workspace_id: int) -> dict:
    """What still stands between this workspace and real use. Shown as banners in the app."""
    from ..llm.router import model_ready
    real = query_one("SELECT COUNT(*) AS n FROM wa_connections WHERE workspace_id = ? AND provider != 'sandbox'", [workspace_id])
    return {"model_ready": model_ready(workspace_id), "real_whatsapp": bool(real["n"]),
            "test_tools": bool(current_app.config.get("ENABLE_TEST_TOOLS"))}
