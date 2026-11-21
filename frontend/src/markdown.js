// Small, safe Markdown renderer for model replies (no dependencies).
//
// Safety: ALL text is HTML-escaped first; only the tags this file emits can appear in the output,
// and links are limited to http(s). So the result is safe for v-html even though the text comes
// from a model.
//
// Supports: paragraphs and line breaks, # headings, **bold**, *italic*, ~~strike~~, `code`,
// ``` fenced code blocks, - / * / 1. lists (one nesting level), > quotes, --- rules,
// [links](https://…), bare https:// links, and simple | tables |.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (s) => s.replace(/[&<>"']/g, (c) => ESC[c]);

function inline(s) {
  // s is already escaped. Protect code spans first so nothing inside them is formatted.
  const codes = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/(?<![="'>\w/])(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__(?=\S)([\s\S]*?\S)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\w])/g, "$1<em>$2</em>");
  s = s.replace(/(^|[^_\w])_(?=[^\s_])([^_\n]*?[^\s_])_(?![_\w])/g, "$1<em>$2</em>");
  s = s.replace(/~~(?=\S)([^~\n]*?\S)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[i]}</code>`);
}

const LIST = /^(\s*)([*+-]|\d{1,3}[.)])\s+(.*)$/;
const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));

export function renderMarkdown(text) {
  const lines = esc(String(text ?? "").replace(/\r\n?/g, "\n")).split("\n");
  const out = [];
  let para = [];
  const flush = () => { if (para.length) { out.push(`<p>${para.map(inline).join("<br>")}</p>`); para = []; } };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // ``` fenced code
    if (/^\s*```/.test(line)) {
      flush();
      const body = [];
      while (++i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i]);
      out.push(`<pre><code>${body.join("\n")}</code></pre>`);
      continue;
    }
    if (!line.trim()) { flush(); continue; }

    let m;
    if ((m = line.match(/^\s*(#{1,6})\s+(.*?)\s*#*\s*$/))) {          // headings, scaled down for chat
      flush();
      const level = Math.min(m[1].length + 2, 6);
      out.push(`<h${level}>${inline(m[2])}</h${level}>`);
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); out.push("<hr>"); continue; }

    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {   // | a | b |
      flush();
      const head = cells(line);
      const rows = [];
      i += 1;
      while (i + 1 < lines.length && isTableRow(lines[i + 1])) rows.push(cells(lines[++i]));
      out.push(`<div class="md-table"><table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${
        rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }

    if (/^\s*&gt;\s?/.test(line)) {                                       // > quote
      flush();
      const q = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) q.push(lines[i++].replace(/^\s*&gt;\s?/, ""));
      i--;
      out.push(`<blockquote>${q.map(inline).join("<br>")}</blockquote>`);
      continue;
    }

    if ((m = line.match(LIST))) {                                          // lists
      flush();
      const ordered = /\d/.test(m[2]);
      const base = m[1].length;
      const items = [];
      while (i < lines.length) {
        const lm = lines[i].match(LIST);
        if (lm && lm[1].length <= base + 1) { items.push({ text: lm[3], sub: [] }); i++; continue; }
        if (lm && items.length) { items[items.length - 1].sub.push({ text: lm[3], ordered: /\d/.test(lm[2]) }); i++; continue; }
        if (lines[i].trim() && /^\s{2,}\S/.test(lines[i]) && items.length) {   // wrapped continuation line
          items[items.length - 1].text += " " + lines[i].trim(); i++; continue;
        }
        break;
      }
      i--;
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((it) => {
        const sub = it.sub.length ? `<${it.sub[0].ordered ? "ol" : "ul"}>${it.sub.map((s) => `<li>${inline(s.text)}</li>`).join("")}</${it.sub[0].ordered ? "ol" : "ul"}>` : "";
        return `<li>${inline(it.text)}${sub}</li>`;
      }).join("")}</${tag}>`);
      continue;
    }

    para.push(line);
  }
  flush();
  return out.join("");
}
