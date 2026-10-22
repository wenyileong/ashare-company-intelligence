"""Build the documentation (v2.0).

    python packaging/build_docs.py [OUT_DIR] [--codebook]

* ``--codebook`` regenerates ``docs/codebook.md`` from the variable registry
  (run it whenever a panel variable is added or changed);
* every ``docs/*.md`` file is converted to a self-contained HTML page in
  OUT_DIR (default ``docs/html``), with the Markdown copied beside it. The
  installer and the portable zip include this folder.

The converter handles the Markdown used in these documents (headings,
paragraphs, nested lists, tables, fenced code, emphasis, inline code and
links), so no extra package is needed.
"""
from __future__ import annotations

import html
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STYLE = ("body{font:15px/1.55 system-ui,'Segoe UI','Microsoft YaHei',sans-serif;max-width:52rem;margin:2rem auto;"
         "padding:0 1rem;color:#1f2328}h1{font-size:1.7rem}h2{font-size:1.3rem;margin-top:2rem;border-bottom:1px "
         "solid #e5e7eb;padding-bottom:.2rem}h3{font-size:1.1rem;margin-top:1.4rem}code{background:#f3f4f6;"
         "padding:0 .25rem;border-radius:3px;font-size:.92em}pre{background:#f6f8fa;padding:.7rem;overflow:auto;"
         "border-radius:4px}pre code{background:none;padding:0}table{border-collapse:collapse;margin:.6rem 0}"
         "td,th{border:1px solid #d0d7de;padding:.25rem .55rem;vertical-align:top}th{background:#f6f8fa;"
         "text-align:left}a{color:#0b5cad}nav{font-size:.9rem;margin-bottom:1rem}nav a{margin-right:.8rem}")


def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: f'<a href="{m.group(2).replace(".md", ".html") if m.group(2).endswith(".md") else m.group(2)}">'
                         f"{m.group(1)}</a>", t)
    return t


def md_to_html(md: str, title: str, nav: str = "") -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []
    stack: list[int] = []            # indentation of open lists

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    def close_lists(to: int = -1):
        while stack and stack[-1] > to:
            stack.pop()
            out.append("</li></ul>")

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_para(); close_lists()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            i += 1
            continue
        if line.startswith("|"):
            flush_para(); close_lists()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                i += 1
            out.append("<table>")
            for k, r in enumerate(rows):
                tag = "th" if k == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in r) + "</tr>")
            out.append("</table>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush_para(); close_lists()
            n = len(m.group(1))
            anchor = re.sub(r"[^\w]+", "-", m.group(2).lower()).strip("-")
            out.append(f'<h{n} id="{anchor}">{_inline(m.group(2))}</h{n}>')
            i += 1
            continue
        m = re.match(r"^(\s*)(?:[-*]|\d+\.)\s+(.*)", line)
        if m:
            flush_para()
            ind = len(m.group(1))
            if not stack or ind > stack[-1]:
                out.append("<ul><li>")
                stack.append(ind)
            else:
                close_lists(ind)
                out.append("</li><li>")
            out.append(_inline(m.group(2)))
            i += 1
            continue
        if not line.strip():
            flush_para()
            if stack and not (i + 1 < len(lines) and re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[i + 1])):
                close_lists()
            i += 1
            continue
        if stack and line.startswith(" "):
            out.append(" " + _inline(line.strip()))
        else:
            close_lists()
            para.append(line.strip())
        i += 1
    flush_para(); close_lists()
    return (f"<!doctype html><html lang='en-GB'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{STYLE}</style></head><body>{nav}" + "\n".join(out) + "</body></html>")


def write_codebook() -> Path:
    sys.path.insert(0, str(ROOT))
    from ashare.panel import variables, codebook, codebook_markdown
    names = list(variables())
    md = codebook_markdown(codebook(names))
    md = md.replace("# Codebook", "# Codebook\n\nAll panel variables (`ashare-cli panel-variables` "
                                  "lists them too). A panel's own codebook, written beside it, adds coverage by "
                                  "year for that panel.", 1)
    p = DOCS / "codebook.md"
    p.write_text(md, encoding="utf-8")
    return p


TITLES = {"user_guide": "User guide", "methods": "Methods", "codebook": "Codebook",
          "developer_guide": "Developer guide", "compliance": "Compliance note"}


def build(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    pages = sorted(DOCS.glob("*.md"), key=lambda p: list(TITLES).index(p.stem) if p.stem in TITLES else 99)
    nav = "<nav>" + "".join(f'<a href="{p.stem}.html">{TITLES.get(p.stem, p.stem)}</a>' for p in pages) + "</nav>"
    written = []
    for p in pages:
        md = p.read_text(encoding="utf-8")
        h = out / f"{p.stem}.html"
        h.write_text(md_to_html(md, TITLES.get(p.stem, p.stem), nav), encoding="utf-8")
        shutil.copy2(p, out / p.name)
        written.append(h)
    shutil.copy2(ROOT / "CITATION.cff", out / "CITATION.cff")
    shutil.copy2(ROOT / "CHANGELOG.md", out / "CHANGELOG.md")   # v2.0.5: was copied by hand
    return written


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--codebook" in sys.argv:
        print("wrote", write_codebook())
    target = Path(args[0]) if args else DOCS / "html"
    for f in build(target):
        print("wrote", f)
