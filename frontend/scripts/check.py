"""Static checks for the Vue sources that need no npm install (used where the registry
is unreachable; `npm run build` remains the real check). Run: python frontend/scripts/check.py

1. every <script> block and .js file parses (node --check)
2. every template has balanced tags
3. every PascalCase component used in a template is imported
4. every relative import resolves, and named imports exist in the target module
5. identifiers used in templates are defined in the script (heuristic)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
GLOBALS = {"RouterLink", "RouterView", "Teleport", "Transition", "KeepAlive", "component", "template", "slot"}
JS_BUILTINS = set("""true false null undefined String Number Boolean Math Date JSON Object Array encodeURIComponent
$event $emit $attrs $slots $refs window document console Infinity NaN parseInt""".split())
errors = []


def err(f, msg):
    errors.append(f"{f.relative_to(SRC.parent)}: {msg}")


class Balance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.problems.append(f"unexpected </{tag}> at line {self.getpos()[0]} (open: {self.stack[-1] if self.stack else None})")
            # try to recover
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
        else:
            self.stack.pop()


def exports_of(path: Path) -> set:
    text = path.read_text(encoding="utf-8")
    names = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)", text))
    if re.search(r"export\s+default", text):
        names.add("default")
    return names


def resolve(base: Path, spec: str) -> Path | None:
    p = (base.parent / spec).resolve()
    for cand in (p, p.with_suffix(".js"), p.with_suffix(".vue")):
        if cand.exists():
            return cand
    return None


def check_imports(f: Path, script: str):
    for m in re.finditer(r"^import\s+([^\n]+?)\s+from\s+['\"](\.[^'\"]+)['\"]", script, re.M):
        what, spec = m.group(1), m.group(2)
        target = resolve(f, spec)
        if not target:
            err(f, f"import not found: {spec}")
            continue
        if target.suffix == ".js":
            named = re.search(r"\{([^}]*)\}", what)
            if named:
                have = exports_of(target)
                for n in [x.strip().split(" as ")[0] for x in named.group(1).split(",") if x.strip()]:
                    if n not in have:
                        err(f, f"'{n}' is not exported by {spec}")
    for m in re.finditer(r"import\(['\"](\.[^'\"]+)['\"]\)", script):
        if not resolve(f, m.group(1)):
            err(f, f"lazy import not found: {m.group(1)}")


def node_check(f: Path, code: str):
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as t:
        t.write(code)
    r = subprocess.run(["node", "--check", t.name], capture_output=True, text=True)
    if r.returncode:
        err(f, "JS syntax: " + (r.stderr.strip().splitlines() or ["?"])[-1] + "\n" + r.stderr[:600])


def template_identifiers(tpl: str) -> set:
    exprs = re.findall(r'(?:v-[\w:.-]+|:[\w.-]+|@[\w.-]+)="([^"]*)"', tpl) + re.findall(r"\{\{(.*?)\}\}", tpl, re.S)
    ids = set()
    for e in exprs:
        e = re.sub(r"'[^']*'|`[^`]*`|\"[^\"]*\"", "", e)
        e = re.sub(r"([A-Za-z_$][\w$]*)\s*:(?!:)", ":", e)   # drop object-literal keys {key: …}
        for m in re.finditer(r"(?<![\w$.?])([A-Za-z_$][\w$]*)", e):
            ids.add(m.group(1))
    return ids


def script_names(script: str) -> set:
    names = set(re.findall(r"(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", script))
    for m in re.finditer(r"(?:const|let)\s*\{([^}]*)\}\s*=", script):
        names |= {x.strip().split(":")[-1].strip() for x in m.group(1).split(",") if x.strip()}
    for m in re.finditer(r"^import\s+([^\n]+?)\s+from", script, re.M):
        names |= set(re.findall(r"[A-Za-z_$][\w$]*", m.group(1).replace(" as ", " ")))
    if "defineProps" in script:
        m = re.search(r"defineProps\(\s*\{(.*?)\}\s*\)", script, re.S)
        if m:
            names |= set(re.findall(r"(\w+)\s*:", m.group(1)))
    return names


KEYWORDS = set("if else in of typeof instanceof new return const let var function true false null undefined this".split())

for f in sorted(SRC.rglob("*")):
    if f.suffix == ".js":
        code = f.read_text(encoding="utf-8")
        node_check(f, code)
        check_imports(f, code)
    elif f.suffix == ".vue":
        text = f.read_text(encoding="utf-8")
        tpl_m = re.search(r"^<template>(.*)^</template>", text, re.S | re.M)
        scr_m = re.search(r"<script setup>(.*?)</script>", text, re.S)
        if not tpl_m or not scr_m:
            err(f, "missing <template> or <script setup>")
            continue
        tpl, script = tpl_m.group(1), scr_m.group(1)
        node_check(f, script)
        check_imports(f, script)
        b = Balance()
        b.feed(tpl)
        for p in b.problems:
            err(f, p)
        if b.stack:
            err(f, f"unclosed tags: {b.stack}")
        names = script_names(script)
        for comp in set(re.findall(r"<([A-Z][A-Za-z0-9]+)", tpl)) - GLOBALS:
            if comp not in names:
                err(f, f"component <{comp}> used but not imported")
        # v-for aliases and slot props are local to the template
        local = set()
        for m in re.finditer(r'v-for="\(?([^)]+?)\)?\s+in\s', tpl):
            local |= set(re.findall(r"[A-Za-z_$][\w$]*", m.group(1)))
        for m in re.finditer(r'(?:v-slot[^=]*|#\w+)="\{?([^"}]*)\}?"', tpl):
            local |= set(re.findall(r"[A-Za-z_$][\w$]*", m.group(1)))
        for m in re.finditer(r'\(?\s*([\w$, ]*)\)?\s*=>', tpl):
            local |= set(re.findall(r"[A-Za-z_$][\w$]*", m.group(1)))
        unknown = template_identifiers(tpl) - names - local - JS_BUILTINS - KEYWORDS
        if unknown:
            err(f, f"template uses undefined names: {sorted(unknown)}")

print("\n".join(errors) if errors else "OK: all Vue/JS sources passed static checks")
sys.exit(1 if errors else 0)
