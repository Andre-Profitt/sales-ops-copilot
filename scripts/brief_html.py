#!/usr/bin/env python3
"""
Render the daily brief markdown to a standalone HTML file with embedded CSS.

No external assets — opens offline. GitHub-flavored styling (tables, code,
headings) plus print-friendly so saving to PDF from the browser works.

Used by `brief.py --open` to land the polished artifact on the user's
default browser at 7am every morning, since SimCorp's Conditional Access
blocks programmatic Teams/Outlook posts (see memory
`feedback_graph_cli_client_also_ca_blocked.md`).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import markdown

CSS = """
:root {
  --text: #1f2328;
  --muted: #59636e;
  --border: #d0d7de;
  --bg: #ffffff;
  --bg-soft: #f6f8fa;
  --accent: #1f4e78;
  --critical: #b22222;
  --important: #b88600;
  --info: #0969da;
  --good: #1a7f37;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px;
  line-height: 1.55;
  color: var(--text);
  background: var(--bg);
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 40px 80px;
}
h1, h2, h3, h4 { color: var(--accent); margin-top: 1.6em; margin-bottom: 0.5em; line-height: 1.25; }
h1 { font-size: 1.9em; border-bottom: 2px solid var(--accent); padding-bottom: 0.2em; margin-top: 0.3em; }
h2 { font-size: 1.4em; border-bottom: 1px solid var(--border); padding-bottom: 0.2em; }
h3 { font-size: 1.15em; }
p, li { margin: 0.5em 0; }
strong { color: var(--accent); }
em { color: var(--muted); }
hr { border: 0; border-top: 1px solid var(--border); margin: 2em 0; }
ul, ol { padding-left: 1.6em; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0 1.2em;
  font-size: 0.95em;
}
table thead th {
  background: var(--bg-soft);
  text-align: left;
  font-weight: 600;
  color: var(--accent);
  border-bottom: 2px solid var(--border);
  padding: 8px 10px;
}
table tbody td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
table tbody tr:hover { background: var(--bg-soft); }
table td:nth-child(n+3) { text-align: right; font-variant-numeric: tabular-nums; }
code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.9em;
  background: var(--bg-soft);
  padding: 2px 5px;
  border-radius: 4px;
}
pre {
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
  overflow-x: auto;
}
pre code { background: transparent; padding: 0; }
blockquote {
  border-left: 4px solid var(--border);
  margin: 0.8em 0;
  padding: 0.2em 1em;
  color: var(--muted);
}
.footer { margin-top: 4em; padding-top: 1em; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85em; }
@media print {
  body { max-width: none; padding: 12px; }
  h1, h2, h3 { page-break-after: avoid; }
  table { page-break-inside: avoid; }
}
"""


def render_html(markdown_text: str, title: str | None = None) -> str:
    """Convert markdown brief to standalone HTML with embedded CSS."""
    title = title or f"Sales Ops Brief — {dt.date.today().isoformat()}"
    body_html = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html",
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
<div class="footer">
  Rendered locally by <code>sales-ops-copilot/brief_html.py</code> ·
  source markdown is the authoritative artifact ·
  Save as PDF via your browser's print dialog (⌘P).
</div>
</body>
</html>
"""


def render_file(md_path: Path, html_path: Path | None = None) -> Path:
    """Read markdown from disk, write HTML alongside (or to html_path)."""
    md = md_path.read_text(encoding="utf-8")
    out = html_path or md_path.with_suffix(".html")
    out.write_text(render_html(md, title=md_path.stem), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: brief_html.py <path-to-markdown>", file=sys.stderr)
        sys.exit(1)
    md_path = Path(sys.argv[1])
    out = render_file(md_path)
    print(f"✓ Wrote {out}")
