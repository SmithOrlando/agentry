"""Scan the Vue app for backend calls and match each to a Flask route.

    python3 scripts/gen_endpoint_map.py --check  # exit 1 if any frontend call has no matching API route

`frontend_calls()` is also used by scripts/gen_api_docs.py to write the "What each screen calls" section
of docs/API_FRONTEND.md. (The older diagram writer below is kept for reference but no longer used.)

How it works (no hand-maintained lists):
  * routes, methods, handlers   ← Flask's url_map
  * required role               ← @role_required / @login_required on each handler
  * services, tables, outside   ← AST of each handler, following calls into app/services, app/llm,
    systems, background jobs       app/knowledge, app/whatsapp (SQL table names, adapter calls, enqueue())
  * which screen calls what     ← every get/post/patch/put/del(...) in frontend/src
"""
from __future__ import annotations

import ast
import inspect
import re
import subprocess
import sys
import tempfile
import textwrap
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.exceptions import MethodNotAllowed, NotFound  # noqa: E402

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402

DOCS = ROOT / "docs"
FRONT = ROOT / "frontend" / "src"
APP = ROOT / "app"

# ------------------------------------------------------------------ backend analysis
SQL_TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", re.I)
HELPER_TABLE = re.compile(r"\b(?:insert|update)\(\s*\"([a-z_]+)\"")
TABLES = {"workspaces", "users", "invites", "agents", "provider_keys", "knowledge_files", "agent_files", "chunks",
          "wa_connections", "contacts", "chats", "messages", "playground_sessions", "playground_messages",
          "usage_events", "audit_log"}
EXTERNAL = {  # call name → outside system it reaches
    "send_text": "WhatsApp provider (send)", "setup": "WhatsApp provider (create instance + webhook)",
    "qr": "WhatsApp provider (QR code)", "state": "WhatsApp provider (status)",
    "chat": "LLM provider", "list_models": "LLM provider (list models)", "fetch_url_text": "Public web page (website sources only)",
}
SKIP_FUNCS = {"get_db", "query", "query_one", "execute", "insert", "update", "jdump", "jload", "utcnow", "body", "ws",
              "err", "jsonify", "encrypt", "decrypt", "encrypt_json", "decrypt_json", "audit", "record_usage"}


def _module_functions():
    """Map 'module.func' and 'func' → function object for all app modules we follow."""
    import importlib
    mods = ["app.services.conversations", "app.services.agents", "app.services.knowledge", "app.services.connections",
            "app.services.settings", "app.llm.router", "app.knowledge.retrieval", "app.knowledge.extract",
            "app.whatsapp.adapters", "app.security", "app.worker"]
    out = {}
    for name in mods:
        m = importlib.import_module(name)
        for fname, obj in vars(m).items():
            if inspect.isfunction(obj) and obj.__module__ == name:
                out[f"{name}.{fname}"] = obj
    return out


FUNCS = None
_memo = {}


def _short(qual: str) -> str:
    return qual.replace("app.services.", "services/").replace("app.llm.", "llm/").replace("app.knowledge.", "knowledge/") \
        .replace("app.whatsapp.", "whatsapp/").replace("app.", "")


def analyse(fn, seen=None) -> dict:
    """Services called, tables touched, outside systems, background jobs — following app calls recursively."""
    key = f"{fn.__module__}.{fn.__name__}"
    if key in _memo:
        return _memo[key]
    seen = seen or set()
    if key in seen:
        return {"services": set(), "tables": set(), "external": set(), "jobs": set()}
    seen.add(key)
    src = textwrap.dedent(inspect.getsource(fn))
    res = {"services": set(), "tables": set(), "external": set(), "jobs": set()}
    res["tables"] |= {t.lower() for t in SQL_TABLE.findall(src) if t.lower() in TABLES}
    res["tables"] |= {t for t in HELPER_TABLE.findall(src) if t in TABLES}
    glb = fn.__globals__
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        target = None
        if isinstance(f, ast.Attribute):
            name = f.attr
            if name in EXTERNAL and name not in ("setup", "state") or (name in ("setup", "state", "qr") and "adapter" in ast.unparse(f.value)):
                res["external"].add(EXTERNAL[name])
            base = f.value
            if isinstance(base, ast.Name) and inspect.ismodule(glb.get(base.id)):
                mod = glb[base.id]
                target = getattr(mod, name, None)
        elif isinstance(f, ast.Name):
            name = f.id
            if name in EXTERNAL:
                res["external"].add(EXTERNAL[name])
            if name == "enqueue" and node.args:
                job = node.args[0]
                jname = ast.unparse(job)
                obj = glb.get(jname.split(".")[0])
                jfn = getattr(obj, jname.split(".")[1], None) if "." in jname and obj else obj
                if inspect.isfunction(jfn):
                    res["jobs"].add(_short(f"{jfn.__module__}.{jfn.__name__}"))
                    sub = analyse(jfn, seen)
                    for k in ("tables", "external", "jobs"):
                        res[k] |= sub[k]
                    res["services"] |= sub["services"]
                continue
            target = glb.get(name)
        if inspect.isfunction(target) and target.__module__.startswith("app.") and target.__name__ not in SKIP_FUNCS \
                and not target.__module__.startswith("app.api"):
            res["services"].add(_short(f"{target.__module__}.{target.__name__}"))
            sub = analyse(target, seen)
            for k in res:
                res[k] |= sub[k]
    _memo[key] = res
    return res


def role_of(fn) -> str:
    src = inspect.getsource(fn)
    m = re.search(r'@role_required\("(\w+)"\)', src)
    if m:
        return m.group(1)
    if "@login_required" in src:
        return "any signed-in"
    return "public"


# Access-control helpers run on every route; listing them everywhere hides what matters.
NOISE = {"security.has_role", "security.role_required", "security.login_required", "security.csrf_token",
         "knowledge/retrieval.tokenize", "services/connections.public", "services/connections.webhook_url",
         "llm/providers.make_client", "services/settings.get_section", "services/settings.get_workspace",
         "knowledge/extract.kind_for"}


def route_table(app):
    rows = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        raw = inspect.unwrap(view)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            info = analyse(raw)
            mod = raw.__module__.replace("app.", "").replace(".", "/") + ".py"
            shown = sorted(x for x in info["services"] if x not in NOISE and not x.split(".")[-1].startswith("_"))
            rows.append({"method": method, "path": rule.rule, "handler": f"{mod}::{raw.__name__}", "role": role_of(view),
                         "doc": (inspect.getdoc(raw) or "").split("\n")[0], "services": shown,
                         "tables": sorted(info["tables"]), "external": sorted(info["external"]), "jobs": sorted(info["jobs"]),
                         "module": mod})
    rows.sort(key=lambda r: (r["path"], r["method"]))
    return rows


# ------------------------------------------------------------------ frontend analysis
CALL = re.compile(r"\b(get|post|patch|put|del)\(\s*([`\"])([^`\"]+)\2")
RAW = re.compile(r"api\(\s*\"([^\"]+)\",\s*\{\s*method:\s*\"(\w+)\"")
HREF = re.compile(r"href=\"(/api/[^\"]+)\"")
VERB = {"get": "GET", "post": "POST", "patch": "PATCH", "put": "PUT", "del": "DELETE"}
SCREEN = {
    "PlaygroundView.vue": "Playground", "WhatsAppView.vue": "WhatsApp", "InboxView.vue": "Inbox", "KnowledgeView.vue": "Knowledge",
    "AuthView.vue": "Login / Register", "AppShell.vue": "Sidebar (every page)", "session.js": "Session (every page)",
    "GeneralSettings.vue": "Settings › General", "ModelsSettings.vue": "Settings › Models & API keys",
    "AgentsSettings.vue": "Settings › Agents", "WhatsAppSettings.vue": "Settings › WhatsApp", "TeamSettings.vue": "Settings › Team",
    "BillingSettings.vue": "Settings › Billing & usage", "SecuritySettings.vue": "Settings › Security",
}


CALLBACK_LABEL = {"onMounted": "on page load", "watch": "when a filter/selection changes", "setInterval": "auto-refresh (polling)",
                  "setTimeout": "auto-refresh (polling)", "useSettingsForm": "useSettingsForm (load / save)"}
KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return"}


def _still_open(text: str, start: int, pos: int, open_ch: str, close_ch: str) -> bool:
    """True if a bracket opened at/after `start` is still unclosed at `pos` (strings/templates ignored roughly)."""
    depth, i, seen = 0, start, False
    while i < pos:
        ch = text[i]
        if ch in "'\"`":                       # skip string literals
            q, i = ch, i + 1
            while i < pos and text[i] != q:
                i += 2 if text[i] == "\\" else 1
        elif ch == open_ch:
            depth, seen = depth + 1, True
        elif ch == close_ch:
            depth -= 1
            if seen and depth == 0:
                return False
        i += 1
    return seen and depth > 0


def _match(text: str, i: int, open_ch: str, close_ch: str) -> int:
    """Index of the bracket closing the one at text[i], or -1."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == open_ch:
            depth += 1
        elif text[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return -1


def enclosing_function(text: str, pos: int) -> str:
    """Name of the innermost named function or known callback (onMounted, watch, useSettingsForm…) around pos."""
    best = None
    for m in re.finditer(r"(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(|"
                         r"^\s*(\w+)\s*\([^)]*\)\s*\{", text[:pos], re.M):
        name = m.group(1) or m.group(2) or m.group(3)
        if name in KEYWORDS:
            continue
        params_open = text.find("(", m.start())
        params_close = _match(text, params_open, "(", ")") if params_open != -1 else -1
        body = text.find("{", params_close if params_close != -1 else m.end() - 1)
        arrow = text.find("=>", m.end())
        # `const f = (...) => expr` without braces: open while on the same statement
        if m.group(2) and arrow != -1 and (body == -1 or arrow < body) and text[arrow + 2:arrow + 4].strip()[:1] != "{":
            if "\n" not in text[arrow:pos] or _still_open(text, m.start(), pos, "(", ")"):
                best = (m.start(), name)
            continue
        if body != -1 and body < pos and _still_open(text, body, pos, "{", "}"):
            best = (m.start(), name)
    for m in re.finditer(r"\b(onMounted|watch|setInterval|setTimeout|useSettingsForm)\(", text[:pos]):
        if _still_open(text, m.end() - 1, pos, "(", ")") and (best is None or m.start() > best[0]):
            best = (m.start(), m.group(1))
    if best is None:
        return "on page load"
    return CALLBACK_LABEL.get(best[1], best[1])


def _strip_comments(text: str) -> str:
    """Blank out //-line comments, /* */ and <!-- --> blocks, keeping offsets (so call positions stay valid)."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    return re.sub(r"^[ \t]*//[^\n]*", blank, text, flags=re.M)


def frontend_calls(adapter):
    calls = []
    for f in sorted(FRONT.rglob("*")):
        if f.suffix not in (".vue", ".js") or f.name in ("api.js",):
            continue
        text = _strip_comments(f.read_text(encoding="utf-8"))
        found = [(VERB[m.group(1)], m.group(3), m.start()) for m in CALL.finditer(text)]
        found += [(m.group(2), m.group(1), m.start()) for m in RAW.finditer(text)]
        found += [("GET", m.group(1), -1) for m in HREF.finditer(text)]   # -1 = a link/download in the page
        for method, path, pos in found:
            p = path if path.startswith("/api") else "/api" + path
            variants = [p]
            if "${kind}" in p:  # Inbox takeover/resume share one call site
                variants = [p.replace("${kind}", k) for k in ("takeover", "resume")]
            for v in variants:
                probe = re.sub(r"\$\{[^}]+\}", "1", v)
                try:
                    endpoint, _ = adapter.match(probe, method=method)
                    ok = True
                except (NotFound, MethodNotAllowed):
                    endpoint, ok = None, False
                calls.append({"screen": SCREEN.get(f.name, f.name), "file": str(f.relative_to(ROOT)), "action": "download link" if pos == -1 else enclosing_function(text, pos),
                              "method": method, "path": re.sub(r"\$\{([^}]+)\}", lambda m: "<" + m.group(1).split(".")[-1].replace("value", "id") + ">", v),
                              "endpoint": endpoint, "ok": ok})
    return calls


# ------------------------------------------------------------------ output
WEBHOOK_SENDERS = {"/webhooks/<provider>/<int:conn_id>/<token>": "Evolution API · generic gateway · sandbox",
                   "/webhooks/meta/<int:conn_id>": "Meta WhatsApp Cloud API"}


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def write_markdown(routes, calls):
    by_rule = defaultdict(set)
    for c in calls:
        if c["ok"]:
            by_rule[(c["method"], c["endpoint"])].add(c["screen"])
    # url_map endpoint name per route
    ep_of = {}
    for r in routes:
        ep_of[(r["method"], r["path"])] = r
    lines = ["# Endpoint map", "",
             "Which screen calls which endpoint, and what each endpoint touches behind it.",
             "**Generated from the code** by `python3 scripts/gen_endpoint_map.py`. Don't edit by hand; rerun it after changing routes or screens.",
             "", "![Endpoint map](endpoint-map.png)", "",
             "Read the diagram left to right: **Vue screen → Flask API module → service → outside system**. "
             "Numbers on the lines count the endpoints involved. Which database tables each endpoint touches is in section 2.", "",
             "## 1. By screen: what each screen calls", ""]
    by_screen = defaultdict(list)
    for c in calls:
        by_screen[c["screen"]].append(c)
    order = ["Login / Register", "Session (every page)", "Sidebar (every page)", "Playground", "WhatsApp", "Inbox", "Knowledge"] + \
            sorted(s for s in by_screen if s.startswith("Settings"))
    for screen in [s for s in order if s in by_screen]:
        lines += [f"### {screen}", "", f"File: `{by_screen[screen][0]['file']}`", "", "| Action (function in the file) | Calls | Handled by |", "|---|---|---|"]
        seen = set()
        for c in by_screen[screen]:
            key = (c["action"], c["method"], c["path"])
            if key in seen:
                continue
            seen.add(key)
            handler = next((r["handler"] for r in routes if r["method"] == c["method"] and c["endpoint"] and
                            r["handler"].endswith("::" + c["endpoint"].split(".")[-1])), "**no matching route**")
            lines.append(f"| `{c['action']}` | `{c['method']} {md_escape(c['path'])}` | `{handler}` |")
        lines.append("")

    lines += ["## 2. By endpoint: what each endpoint does behind the scenes", "",
              "*Role* = minimum role required. *Services* = app functions it calls (followed recursively). "
              "*Tables* = database tables it reads or writes. *Outside* = external systems it calls, directly or through a background job.", ""]
    groups = defaultdict(list)
    for r in routes:
        groups[r["module"]].append(r)
    titles = {"api/auth.py": "Auth", "api/playground.py": "Playground", "api/agents.py": "Agents", "api/knowledge.py": "Knowledge",
              "api/whatsapp.py": "WhatsApp numbers", "api/inbox.py": "Inbox", "api/settings.py": "Settings, team, usage, audit",
              "webhooks.py": "Webhooks (called by WhatsApp providers, not the browser)", "__init__.py": "Service"}
    for mod in ["api/auth.py", "api/playground.py", "api/agents.py", "api/knowledge.py", "api/whatsapp.py", "api/inbox.py",
                "api/settings.py", "webhooks.py", "__init__.py"]:
        if mod not in groups:
            continue
        lines += [f"### {titles[mod]} (`app/{mod}`)", "",
                  "| Endpoint | Role | Used by | Services | Tables | Outside / background |", "|---|---|---|---|---|---|"]
        for r in groups[mod]:
            ep_name = next((c["endpoint"] for c in calls if c["ok"] and c["method"] == r["method"] and c["endpoint"]
                            and c["endpoint"].endswith("." + r["handler"].split("::")[1])), None)
            used = sorted(by_rule.get((r["method"], ep_name), set())) if ep_name else []
            if r["path"] in WEBHOOK_SENDERS:
                used = [WEBHOOK_SENDERS[r["path"]]]
            if r["path"] == "/healthz":
                used = ["load balancer / Docker healthcheck"]
            outside = r["external"] + [f"job: {j}" for j in r["jobs"]]
            cell = lambda xs: "<br>".join(f"`{x}`" for x in xs) if xs else "—"  # noqa: E731
            lines.append(f"| `{r['method']} {md_escape(r['path'])}`<br><sub>{r['handler']}</sub> | {r['role']} | "
                         f"{'<br>'.join(used) if used else '—'} | {cell(r['services'])} | {cell(r['tables'])} | "
                         f"{'<br>'.join(md_escape(o) for o in outside) if outside else '—'} |")
        lines.append("")

    unused = [r for r in routes if r["module"].startswith("api/") and not any(
        c["ok"] and c["method"] == r["method"] and c["endpoint"] and c["endpoint"].endswith("." + r["handler"].split("::")[1]) for c in calls)]
    lines += ["## 3. Endpoints with no caller in the UI", "",
              "Kept for API clients, scripts and tests (e.g. the tests). Remove one only after checking those.", ""]
    lines += [f"- `{r['method']} {md_escape(r['path'])}` → `{r['handler']}`" for r in unused] or ["- none"]
    lines += ["", "## 4. Inbound message flow (webhook → reply)", "",
              "```",
              "WhatsApp provider ──POST──▶ /webhooks/… (webhooks.py)",
              "    └▶ adapter.parse_webhook() ─▶ services/conversations.handle_inbound()   [contacts, chats, messages]",
              "         └▶ worker.enqueue(respond)  ── HTTP 200 returned here ──",
              "              └▶ services/conversations.respond()",
              "                   ├▶ services/agents.build_messages() ─▶ knowledge/retrieval.search()   [chunks, knowledge_files, agent_files]",
              "                   ├▶ llm/router.generate() ─▶ LLM provider                           [provider_keys, usage_events]",
              "                   └▶ draft saved, or adapter.send_text() ─▶ WhatsApp provider          [messages]",
              "```", "",
              f"_{len(routes)} route/method pairs · {len({(c['method'], c['path']) for c in calls})} distinct calls from the UI · "
              f"{sum(1 for c in calls if not c['ok'])} unmatched._", ""]
    (DOCS / "ENDPOINT_MAP.md").write_text("\n".join(lines), encoding="utf-8")


def service_externals() -> dict:
    """Outside systems each service module reaches, from that module's own functions."""
    out = defaultdict(set)
    for qual, fn in (FUNCS or {}).items():
        group = _short(qual).split(".")[0]
        if not group.startswith(("services/", "llm/", "knowledge/")):
            continue
        for e in analyse(fn)["external"]:
            out[group].add(e.split(" (")[0])
    return out


def write_diagram(routes, calls):
    screen_mod = defaultdict(int)
    for c in calls:
        if not c["ok"]:
            continue
        r = next((r for r in routes if r["method"] == c["method"] and r["handler"].endswith("::" + c["endpoint"].split(".")[-1])), None)
        if r:
            screen_mod[(c["screen"], r["module"])] += 1
    mod_svc = defaultdict(int)
    for r in routes:
        for g in {s.split(".")[0] for s in r["services"] if s.startswith(("services/", "llm/router", "knowledge/"))}:
            mod_svc[(r["module"], g)] += 1
    svc_ext = service_externals()
    nid = lambda s: "n" + re.sub(r"\W", "_", s)  # noqa: E731
    out = ['digraph endpoints {',
           'graph [rankdir=LR, fontname="Helvetica", bgcolor="white", pad=0.3, nodesep=0.18, ranksep=1.3, concentrate=false, '
           'label=<<b>Agentry — endpoint map</b><br/><font point-size="10" color="#5B6573">Vue screen → Flask API module → service → outside system. '
           'Numbers = endpoints used. Database tables per endpoint: see the tables below. (generated by scripts/gen_endpoint_map.py)</font>>, labelloc=t, labeljust=l];',
           'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#C5CCD6", fillcolor="#FFFFFF", margin="0.14,0.06"];',
           'edge [fontname="Helvetica", fontsize=9, color="#8A94A3", fontcolor="#5B6573", arrowsize=0.6];']

    def cluster(name, label, items, fill, border):
        out.append(f'subgraph cluster_{name} {{ label=<<b>{label}</b>>; style="rounded,filled"; fillcolor="{fill}"; color="{border}"; fontsize=12;')
        for i in items:
            out.append(f'{nid(i)} [label="{i}"];')
        out.append("}")

    screen_order = ["Login / Register", "Session (every page)", "Sidebar (every page)", "Playground", "WhatsApp", "Inbox", "Knowledge"]
    screens = [s for s in screen_order if any(k[0] == s for k in screen_mod)] + sorted({s for s, _ in screen_mod} - set(screen_order))
    mod_order = ["api/auth.py", "api/playground.py", "api/whatsapp.py", "api/inbox.py", "api/knowledge.py", "api/agents.py", "api/settings.py", "webhooks.py"]
    mods = [m for m in mod_order if any(k[0] == m or k[1] == m for k in list(screen_mod) + list(mod_svc))]
    svcs = sorted({s for _, s in mod_svc})
    exts = ["LLM provider", "WhatsApp provider", "Public web page"]
    cluster("screens", "Vue screens", screens, "#E8F0FE", "#BFD3F5")
    cluster("api", "Flask API modules", mods, "#FAFBFC", "#1F6FEB")
    cluster("svc", "Services (app/)", svcs, "#FFF4D6", "#E3B341")
    cluster("ext", "Outside systems", exts, "#E6F4EA", "#A7D7B5")
    for (s, m), n in sorted(screen_mod.items()):
        out.append(f'{nid(s)} -> {nid(m)} [label="{n}"];')
    for (m, s), n in sorted(mod_svc.items()):
        out.append(f'{nid(m)} -> {nid(s)} [label="{n}"];')
    for s in svcs:
        for e in sorted(svc_ext.get(s, ())):
            out.append(f'{nid(s)} -> {nid(e)} [color="#1A7F37"];')
    out.append(f'{nid("WhatsApp provider")} -> {nid("webhooks.py")} [label="inbound messages (webhook)", color="#1A7F37", style=dashed, constraint=false];')
    out.append("}")
    dot = DOCS / "endpoint-map.dot"
    dot.write_text("\n".join(out), encoding="utf-8")
    try:
        subprocess.run(["dot", "-Tpng", "-Gdpi=140", str(dot), "-o", str(DOCS / "endpoint-map.png")], check=True)
        subprocess.run(["dot", "-Tsvg", str(dot), "-o", str(DOCS / "endpoint-map.svg")], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Graphviz `dot` not found: wrote endpoint-map.dot only (install graphviz to render the picture).")


def main():
    tmp = Path(tempfile.mkdtemp())
    app = create_app(TestConfig, INSTANCE_DIR=tmp, DATABASE_PATH=tmp / "map.db", UPLOAD_DIR=tmp / "u", LOG_LEVEL="WARNING")
    adapter = app.url_map.bind("localhost")
    global FUNCS
    with app.app_context():
        FUNCS = _module_functions()
        routes = route_table(app)
    calls = frontend_calls(adapter)
    bad = [c for c in calls if not c["ok"]]
    if "--check" in sys.argv:
        for c in bad:
            print(f"UNMATCHED: {c['method']} {c['path']} in {c['file']} ({c['action']})")
        print(f"{len(calls)} frontend calls checked, {len(bad)} unmatched")
        sys.exit(1 if bad else 0)
    print("The endpoint docs are generated by scripts/gen_api_docs.py now. Use --check here.")


if __name__ == "__main__":
    main()
