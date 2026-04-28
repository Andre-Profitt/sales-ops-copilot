#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""
Render the daily / weekly Sales Ops brief markdown to a memo-grade PDF.

WeasyPrint-backed renderer. Adds a consulting-style cover block, page footer
with running page numbers, page breaks before major sections, and tabular-aligned
currency. Sister to `brief_html.render_file` — same input contract, PDF output.

System libraries (installed via Homebrew on this Mac):
    brew install pango cairo glib

If WeasyPrint complains about `libgobject-2.0-0`, add Homebrew's lib dir to the
dynamic linker search path; we set DYLD_FALLBACK_LIBRARY_PATH at import time so
launchd / direct CLI runs work without the user thinking about it.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

# WeasyPrint loads pango/cairo/gobject via dlopen. Homebrew installs them under
# /opt/homebrew/lib on Apple Silicon; the system linker doesn't search there by
# default for non-Homebrew Pythons. Setting this BEFORE the weasyprint import
# is required.
_BREW_LIB = "/opt/homebrew/lib"
if os.path.isdir(_BREW_LIB):
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    if _BREW_LIB not in existing.split(":"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            f"{_BREW_LIB}:{existing}" if existing else _BREW_LIB
        )

import markdown  # noqa: E402
from weasyprint import CSS, HTML  # noqa: E402

PAGE_SIZES = {"Letter": "Letter", "A4": "A4"}

_LONG_DATE = "%A, %B %-d, %Y"

_METHODOLOGY = (
    "Pipeline data from Salesforce preprod (apro@simcorp.com). "
    "Stage probabilities are empirically derived from last-4-quarters "
    "OpportunityFieldHistory. ARR / ACV reported separately per SimCorp "
    "Commercial Handbook."
)

_CONFIDENTIALITY = "Internal — Sales Operations only"


def _build_css(page_size: str, footer_left: str) -> str:
    return f"""
@page {{
  size: {page_size};
  margin: 0.75in;
  @bottom-left {{
    content: "{footer_left}";
    font-family: Georgia, Charter, serif;
    font-size: 9pt;
    color: #59636e;
    border-top: 0.5pt solid #d0d7de;
    padding-top: 6pt;
    width: 50%;
  }}
  @bottom-right {{
    content: counter(page) " / " counter(pages);
    font-family: Georgia, Charter, serif;
    font-size: 9pt;
    color: #59636e;
    border-top: 0.5pt solid #d0d7de;
    padding-top: 6pt;
    text-align: right;
    width: 50%;
  }}
}}

:root {{
  --text: #1f2328;
  --muted: #59636e;
  --border: #d0d7de;
  --bg: #ffffff;
  --bg-soft: #f6f8fa;
  --accent: #1f4e78;
  --accent-soft: #eef4fa;
}}

* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}

body {{
  font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: var(--text);
  background: var(--bg);
}}

h1, h2, h3, h4 {{
  font-family: Georgia, Charter, "Times New Roman", serif;
  color: var(--accent);
  line-height: 1.2;
  page-break-after: avoid;
}}

h1 {{
  font-size: 18pt;
  margin: 0 0 0.4em;
  border-bottom: 2pt solid var(--accent);
  padding-bottom: 0.15em;
}}
h2 {{
  font-size: 14pt;
  margin: 1.4em 0 0.4em;
  border-bottom: 0.5pt solid var(--border);
  padding-bottom: 0.1em;
}}
h3 {{ font-size: 11.5pt; margin: 1.1em 0 0.3em; }}
h4 {{ font-size: 10.5pt; margin: 0.9em 0 0.25em; color: var(--muted); }}

p, li {{ margin: 0.4em 0; }}
strong {{ color: var(--accent); }}
em {{ color: var(--muted); }}
hr {{ border: 0; border-top: 0.5pt solid var(--border); margin: 1.4em 0; }}
ul, ol {{ padding-left: 1.4em; }}

table {{
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0 1em;
  font-size: 9.5pt;
  page-break-inside: avoid;
}}
table thead {{ display: table-header-group; }}
table thead th {{
  background: var(--bg-soft);
  text-align: left;
  font-weight: 600;
  color: var(--accent);
  border-bottom: 1pt solid var(--accent);
  padding: 5pt 7pt;
}}
table tbody td {{
  padding: 4pt 7pt;
  border-bottom: 0.5pt solid var(--border);
  font-variant-numeric: tabular-nums;
}}
table td:nth-child(n+3), table th:nth-child(n+3) {{ text-align: right; }}

code {{
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 9pt;
  background: var(--bg-soft);
  padding: 1pt 4pt;
  border-radius: 3pt;
}}
pre {{
  background: var(--bg-soft);
  border: 0.5pt solid var(--border);
  border-radius: 4pt;
  padding: 8pt 10pt;
  font-size: 9pt;
  overflow-x: auto;
  page-break-inside: avoid;
}}
pre code {{ background: transparent; padding: 0; }}

blockquote {{
  border-left: 3pt solid var(--accent);
  margin: 0.6em 0;
  padding: 0.1em 0.9em;
  color: var(--muted);
}}

/* Cover block on page 1 */
.cover {{
  margin-bottom: 1.8em;
  padding-bottom: 1em;
  border-bottom: 1.5pt solid var(--accent);
}}
.cover .eyebrow {{
  font-family: Georgia, Charter, serif;
  font-size: 9pt;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.4em;
}}
.cover h1.title {{
  font-size: 24pt;
  margin: 0 0 0.15em;
  border: 0;
  padding: 0;
}}
.cover .subtitle {{
  font-family: Georgia, Charter, serif;
  font-size: 13pt;
  color: var(--muted);
  margin: 0 0 0.9em;
}}
.cover .meta {{
  font-size: 9.5pt;
  color: var(--text);
  margin: 0.2em 0;
}}
.cover .meta strong {{ color: var(--text); }}
.cover .audience-note {{
  font-size: 9.5pt;
  color: var(--muted);
  font-style: italic;
  margin: 0.6em 0 0;
}}
.cover .methodology {{
  font-size: 8.5pt;
  color: var(--muted);
  margin: 0.6em 0 0;
  line-height: 1.35;
}}
.cover .conf {{
  display: inline-block;
  margin-top: 0.6em;
  font-size: 8pt;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #b22222;
  border: 0.5pt solid #b22222;
  padding: 2pt 6pt;
  border-radius: 2pt;
}}

/* Synthesis = the executive summary; visual emphasis */
.synthesis-wrap {{
  background: var(--accent-soft);
  border-left: 3pt solid var(--accent);
  padding: 0.6em 1em 0.4em;
  margin: 0.4em 0 1em;
  page-break-inside: avoid;
}}
.synthesis-wrap h2 {{
  margin-top: 0.2em;
  border-bottom: 0;
}}

/* Page-break controls for major sections */
.page-break {{
  page-break-before: always;
}}
"""


def _long_date(date: dt.date) -> str:
    try:
        return date.strftime(_LONG_DATE)
    except ValueError:
        return date.strftime("%A, %B %d, %Y").replace(" 0", " ")


def _infer_date_from_stem(stem: str) -> dt.date:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return dt.date.today()


def _build_cover_html(title: str, date: dt.date, audience_note: str | None) -> str:
    long = _long_date(date)
    audience_block = f'<p class="audience-note">{audience_note}</p>' if audience_note else ""
    return f"""
<section class="cover">
  <p class="eyebrow">SimCorp · Sales Operations</p>
  <h1 class="title">{title}</h1>
  <p class="subtitle">{long}</p>
  <p class="meta"><strong>Prepared by:</strong> sales-ops-copilot</p>
  <p class="meta"><strong>For:</strong> Andre Profitt</p>
  <p class="meta"><strong>Audience:</strong> Sales Operations leadership</p>
  {audience_block}
  <p class="methodology">{_METHODOLOGY}</p>
  <span class="conf">{_CONFIDENTIALITY}</span>
</section>
"""


def _strip_leading_h1(body_html: str) -> str:
    return re.sub(r"^\s*<h1[^>]*>.*?</h1>\s*", "", body_html, count=1, flags=re.S | re.I)


def _wrap_synthesis(body_html: str) -> str:
    # The first <h2>Synthesis</h2> through the next <h2> gets visual emphasis.
    pattern = re.compile(r"(<h2[^>]*>\s*Synthesis\s*</h2>.*?)(?=<h2|\Z)", re.S | re.I)
    return pattern.sub(
        lambda m: f'<div class="synthesis-wrap">{m.group(1)}</div>', body_html, count=1
    )


def _insert_page_breaks(body_html: str) -> str:
    # Memo-grade pacing: major sections start on a fresh page after the cover.
    targets = ("Active alerts", "Pipeline this quarter")
    for label in targets:
        body_html = re.sub(
            rf"(<h2[^>]*>\s*{re.escape(label)}[^<]*</h2>)",
            r'<div class="page-break"></div>\1',
            body_html,
            count=1,
            flags=re.I,
        )
    return body_html


def render_pdf(
    markdown_text: str,
    out_path: Path,
    title: str,
    audience_note: str | None = None,
    page_size: str = "Letter",
    date: dt.date | None = None,
) -> Path:
    page_size = PAGE_SIZES.get(page_size, "Letter")
    date = date or dt.date.today()

    body_html = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html",
    )
    body_html = _strip_leading_h1(body_html)
    body_html = _wrap_synthesis(body_html)
    body_html = _insert_page_breaks(body_html)

    cover = _build_cover_html(title, date, audience_note)
    footer_left = f"Sales Ops Brief — {date.isoformat()}"
    css = _build_css(page_size, footer_left)

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — {date.isoformat()}</title>
</head>
<body>
{cover}
{body_html}
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=doc).write_pdf(str(out_path), stylesheets=[CSS(string=css)])
    return out_path


def render_file(md_path: Path, pdf_path: Path | None = None) -> Path:
    md = md_path.read_text(encoding="utf-8")
    out = pdf_path or md_path.with_suffix(".pdf")
    stem = md_path.stem
    date = _infer_date_from_stem(stem)
    if stem.startswith("weekly-"):
        title = "Sales Operations Weekly Rollup"
        audience = "Week ending " + _long_date(date)
    else:
        title = "Sales Operations Brief"
        audience = None
    return render_pdf(md, out, title=title, audience_note=audience, date=date)


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if a != "--pdf"]
    if not args:
        print("usage: brief_pdf.py <path-to-markdown> [<output.pdf>]", file=sys.stderr)
        sys.exit(1)
    md_path = Path(args[0])
    pdf_path = Path(args[1]) if len(args) >= 2 else None
    out = render_file(md_path, pdf_path)
    print(f"OK Wrote {out}")
