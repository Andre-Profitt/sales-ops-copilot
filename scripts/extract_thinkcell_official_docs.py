#!/usr/bin/env python3
"""Extract structured facts from think-cell official documentation HTML files.

Inputs (all on disk under _windows_test/):
  - official-en-api.html
  - official-en-introductionautomation.html
  - official-en-jsondataautomation.html
  - official-en-exceldataautomation.html
  - official-en-exceldatalinks.html
  - official-en-element-datasheets.html
  - official-en-tables-with-datasheets.html
  - official-en-table.html
  - official-en-import-mekko-graphics.html

Output:
  state/thinkcell_bridge/official_docs_corpus/<ts>/extraction.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "_windows_test"
OUT_BASE = ROOT / "state" / "thinkcell_bridge" / "official_docs_corpus"

# Strip these inline tags but keep text content
INLINE_TAGS = {"code", "em", "kbd", "small", "span", "strong", "var", "a", "b", "i", "u"}
# These tags emit a paragraph break
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "tr", "th", "td"}
# HTML5 void elements — never have a closing tag. Must NOT push onto drop stack.
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
# Tags whose body we drop entirely (scripts, styles, svg, etc.).
# 'svg' is the outer container; its descendants (path, etc.) get dropped automatically
# because we're already inside drop_depth>0.
DROP_TAGS = {"script", "style", "svg", "nav", "head"}


class TextExtractor(HTMLParser):
    """Walk the HTML tree, recording structured (tag, text) tuples and code blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, str, dict[str, str]]] = []
        # stack tracks open tags so we know when to drop content
        self._stack: list[str] = []
        self._drop_depth = 0
        self._buf: list[str] = []
        self._current_open_tag: str | None = None
        # Code block accumulator
        self._in_code_pre = 0
        self._code_buf: list[str] = []

    def _flush_text(self) -> None:
        if self._buf:
            text = "".join(self._buf).strip()
            if text:
                # collapse internal whitespace
                text = re.sub(r"\s+", " ", text)
                self.events.append(("text", text, {}))
            self._buf.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        # Void tags don't get pushed (they have no end-tag).
        if tag in VOID_TAGS:
            return
        self._stack.append(tag)
        if tag in DROP_TAGS:
            self._drop_depth += 1
            return
        if self._drop_depth > 0:
            return
        if tag == "pre":
            self._in_code_pre += 1
            self._code_buf = []
            return
        if tag in BLOCK_TAGS:
            self._flush_text()
            self.events.append(("open", tag, attr_dict))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing form like <br/> — treat as void open with no close.
        if tag in VOID_TAGS:
            return
        # Otherwise emit open and matching close immediately.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            # Void tags should never appear as end-tags; ignore.
            return
        # Pop matching tag off stack (HTML may be malformed; pop only on match).
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        elif tag in self._stack:
            # Pop everything down to and including the matched tag (recover from missing closes).
            while self._stack and self._stack[-1] != tag:
                self._stack.pop()
            if self._stack:
                self._stack.pop()
        if tag in DROP_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth > 0:
            return
        if tag == "pre":
            if self._in_code_pre > 0:
                code = "".join(self._code_buf)
                # Decode the doubly-escaped HTML in code blocks (think-cell wraps in <code>)
                code = code.strip()
                if code:
                    self.events.append(("code", code, {}))
                self._code_buf = []
                self._in_code_pre -= 1
            return
        if tag in BLOCK_TAGS:
            self._flush_text()
            self.events.append(("close", tag, {}))

    def handle_data(self, data: str) -> None:
        if self._drop_depth > 0:
            return
        if self._in_code_pre > 0:
            self._code_buf.append(data)
            return
        self._buf.append(data)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def parse_doc(path: Path) -> dict[str, Any]:
    """Parse one HTML file. Returns structured sections + code blocks + word count."""

    html = path.read_text(encoding="utf-8", errors="replace")
    parser = TextExtractor()
    parser.feed(html)
    parser._flush_text()

    title: str | None = None
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    open_block: str | None = None
    word_count = 0

    # Also extract <title>
    title_match = re.search(r"<title>([^<]+)</title>", html)
    if title_match:
        title = html_lib.unescape(title_match.group(1)).strip()

    for kind, payload, attrs in parser.events:
        if kind == "open":
            open_block = payload
            if payload in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                # Start a new section
                pass
        elif kind == "close":
            open_block = None
        elif kind == "code":
            if current is not None:
                current.setdefault("code_blocks", []).append(payload)
            else:
                # Pre-section code block (rare); stash in a synthetic section
                if not sections:
                    sections.append(
                        {
                            "level": 0,
                            "anchor": "preface",
                            "heading": "(preface)",
                            "paragraphs": [],
                            "code_blocks": [],
                        }
                    )
                    current = sections[-1]
                current.setdefault("code_blocks", []).append(payload)
        elif kind == "text":
            if open_block in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                level = int(open_block[1])
                anchor = _slugify(payload)
                current = {
                    "level": level,
                    "anchor": anchor,
                    "heading": payload,
                    "paragraphs": [],
                    "code_blocks": [],
                }
                sections.append(current)
            elif open_block in {"p", "li", "td", "th"}:
                if current is None:
                    sections.append(
                        {
                            "level": 0,
                            "anchor": "preface",
                            "heading": "(preface)",
                            "paragraphs": [],
                            "code_blocks": [],
                        }
                    )
                    current = sections[-1]
                current["paragraphs"].append(payload)
                word_count += len(payload.split())

    # Attach a source-anchor URL fragment guess for each section
    for sec in sections:
        sec["source_anchor"] = f"{path.name}#{sec['anchor']}"

    return {
        "filename": path.name,
        "path": str(path.relative_to(ROOT)),
        "title": title or "(no title)",
        "section_count": len(sections),
        "word_count": word_count,
        "sections": sections,
    }


# Per-doc fact extractors: each takes parsed dict, returns list of {topic, fact, source_quote}
def _short(text: str, limit: int = 290) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _find_paragraph(parsed: dict[str, Any], substr: str) -> tuple[str, str] | None:
    needle = substr.lower()
    for sec in parsed["sections"]:
        for para in sec["paragraphs"]:
            if needle in para.lower():
                return sec["heading"], para
    return None


def _find_code(parsed: dict[str, Any], substr: str) -> tuple[str, str] | None:
    needle = substr.lower()
    for sec in parsed["sections"]:
        for code in sec.get("code_blocks", []):
            if needle in code.lower():
                return sec["heading"], code
    return None


def extract_facts_jsondataautomation(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "describes the rules a .ppttc file must follow")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_schema_canonical",
                "fact": "The canonical JSON schema for .ppttc files ships in the think-cell installation as ppttc/ppttc-schema.json (alongside template.pptx and sample.ppttc).",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "array contains a series of objects")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_top_level_shape",
                "fact": "The top-level .ppttc value is an ARRAY of template-objects. Each entry in the array represents a copy of one PowerPoint template; multiple entries produce multiple template copies in slide order.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "must have two properties")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_template_object_required_keys",
                "fact": "Each template-object MUST have exactly two properties: 'template' (string) and 'data' (array).",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "directory separator must be a backslash")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_template_path_format",
                "fact": "Template path: backslash on Windows (escaped to \\\\ in JSON), slash on macOS. Bare filename works if .ppttc and template are co-located. Remote URLs (HTTP/HTTPS) are also accepted.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = (
        _find_paragraph(parsed, "name") if False else _find_paragraph(parsed, "AddRangeData name")
    )
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_data_object_keys",
                "fact": "Each object inside 'data' has exactly two properties: 'name' (the AddRangeData name registered on the template element) and 'table' (data array). Order inside 'data' is irrelevant.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "two elements have the same name")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_duplicate_names",
                "fact": "If two elements share the same AddRangeData name, think-cell fills BOTH with the same data — controlled deduplication.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "single sub-array with a single object")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_text_field_table_shape",
                "fact": "For automation text fields, Harvey balls, and checkboxes the 'table' is a single sub-array containing a single typed object. For charts/tables, 'table' is a 2D array of typed objects representing the datasheet.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    # Cell data types — find the data-type table by walking section "Cell data types"
    for sec in parsed["sections"]:
        if "cell data types" in sec["heading"].lower():
            facts.append(
                {
                    "topic": "ppttc_cell_data_types",
                    "fact": "Six cell data types are defined: string, number, date (YYYY-MM-DD ISO 8601), percentage, fill (hex or rgb(...) added to a number/string cell), and null (empty cell, no quotes). UTF-8 supported in strings; decimal point only for number/percentage.",
                    "source_quote": _short(" | ".join(sec["paragraphs"][:8])),
                    "section": sec["heading"],
                }
            )
            break

    pair = _find_paragraph(parsed, "empty first cell")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_chart_first_row",
                "fact": "Chart datasheet first row: leading null cell (placeholder), then category labels. The leading null cell is ignored by the chart so 'can actually contain any data'.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "empty array")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_empty_row",
                "fact": "An empty sub-array [] denotes an empty row in the datasheet. Empty rows shift downstream rows in the color-scheme assignment (so they are SEMANTIC, not just padding).",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "ppttc.exe")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_command_line",
                "fact": "Command-line render is documented: 'ppttc.exe <PPTTC_INPUT> -o <PPTX_OUTPUT>'. ppttc.exe lives in the 'ppttc' subfolder of the think-cell installation. Windows-only.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "tells your operating system to open .ppttc files")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_default_open_handler",
                "fact": "Installation registers .ppttc as the file association for think-cell. Double-click in File Explorer or Finder triggers think-cell to (1) parse the JSON, (2) create a new presentation from the templates, (3) bind data into named elements, (4) open the result in PowerPoint.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "tcserver.exe")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "ppttc_tcserver",
                "fact": "tcserver.exe accepts JSON via HTTP POST with media type application/vnd.think-cell.ppttc+json and returns a .pptx file. Windows-only. Optional auto-start Windows service.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_introductionautomation(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "must be linked to Excel")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "naming_presentationfromtemplate",
                "fact": "PresentationFromTemplate path: template elements must be LINKED TO EXCEL (via Excel data links). No element name needed — think-cell finds them by Excel link.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "must have names")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "naming_jsonppttc_and_updatebatch",
                "fact": "JSON automation (.ppttc) and UpdateBatch path: template elements must have NAMES assigned in PowerPoint via the AddRangeData Name field on the element's mini toolbar. The name is set in the PowerPoint TEMPLATE itself, not in Excel and not in the .ppttc.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "AddRangeData Name")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "naming_addrangedata_name_mechanism",
                "fact": "AddRangeData Name is stored in the template's chart/table/Harvey-ball/checkbox/automation-text-field metadata (set via the mini toolbar on the element). Names are case-insensitive. AddRangeImage Name is a separate naming surface for table images and is ONLY usable from Excel automation.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_exceldataautomation(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "PresentationFromTemplate function creates a copy")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "presentationfromtemplate_purpose",
                "fact": "PresentationFromTemplate creates a NEW PowerPoint presentation by copying a template and refreshing every think-cell element that has an Excel link. Updated elements get their Excel links broken (one-shot snapshot); elements not refreshed retain links.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "UpdateBatch has replaced UpdateChart")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "updatechart_deprecation",
                "fact": "UpdateChart is DEPRECATED but still works. UpdateBatch replaces it. New table-image features and faster execution on large decks are UpdateBatch-only.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "regardless of whether they")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "updatebatch_purpose",
                "fact": "UpdateBatch updates SPECIFIC named think-cell elements in a presentation, regardless of whether they're Excel-linked. AddRangeData (with optional Transposed flag) and AddRangeImage are the two scheduling primitives inside an UpdateBatch.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "intentionally breaks the updated elements")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "presentationfromtemplate_link_breakage",
                "fact": "After PresentationFromTemplate the new deck has its Excel links DELIBERATELY BROKEN for refreshed elements (prevents accidental re-pull). Re-feeding through PresentationFromTemplate again with a different workbook is supported by re-using the output as the next template.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Names are case-insensitive")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "addrangedata_name_semantics",
                "fact": "AddRangeData Name (and AddRangeImage Name) are CASE-INSENSITIVE. If two elements within Target share the same name, think-cell fills BOTH with the same data — same dedupe rule as the .ppttc 'name' key.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Transposed")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "addrangedata_transposed_flag",
                "fact": "AddRangeData has a Transposed boolean. Set True to swap row/column orientation between the Excel range and the element's datasheet. AddRangeImage does NOT have a Transposed flag.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_api(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "Visual Basic for Applications") or _find_paragraph(
        parsed, "VBA"
    )
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "api_setup_languages",
                "fact": "Documented language bindings for the think-cell automation API: VBA (Office macros) and C# (Office add-in or external console). Both go through the tcXlAddIn / tcUpdate COM dispatch wrappers.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Mekko Graphics charts")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "api_mekko_graphics",
                "fact": "Mekko Graphics import is a documented but separate API surface (ImportMekkoGraphicsCharts, GetMekkoGraphicsXML).",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Style files")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "api_style_files",
                "fact": "Style files are a separate documented surface from data automation: tcstyle.xsd / .style files governing chart formatting (separate from tcXlAddIn data dispatch).",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_exceldatalinks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    pair = _find_paragraph(parsed, "create charts from Excel")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "excel_link_creation",
                "fact": "Excel data links are created from inside Excel (ribbon-driven), not via the .ppttc — the link is per-element metadata embedded in the PowerPoint chart/table at design time.",
                "source_quote": _short(p),
                "section": h,
            }
        )
    return facts


def extract_facts_element_datasheets(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "Edit datasheet layout") or _find_paragraph(
        parsed, "edit data layout"
    )
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "datasheet_optional_rows_cols",
                "fact": "Charts have OPTIONAL rows/columns (Series, Category, 100%=, etc.) that change how .ppttc 'table' rows are interpreted. Adding/removing 100%= row in the template repositions the totals interpretation in the JSON binding.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Transpose")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "datasheet_transpose",
                "fact": "Datasheet rows and columns can be transposed in PowerPoint. Affects how AddRangeData Transposed=True/False maps Excel-range axes onto the datasheet.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_tables_with_datasheets(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    pair = _find_paragraph(parsed, "data-driven")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "tables_data_driven",
                "fact": "All think-cell tables are data-driven: each has an element datasheet that automatically grows or shrinks as data is added or removed. Bindable via the same AddRangeData mechanism as charts.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    pair = _find_paragraph(parsed, "Open Datasheet")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "tables_open_datasheet",
                "fact": "A table's underlying datasheet is opened via right-click context menu > Open Datasheet. The datasheet is the same object kind that 'table' arrays in .ppttc populate.",
                "source_quote": _short(p),
                "section": h,
            }
        )

    return facts


def extract_facts_table(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    pair = _find_paragraph(parsed, "Insert tables")
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "table_insertion",
                "fact": "think-cell tables are inserted from the ribbon and become a first-class data-driven element (separate from PowerPoint native tables). They participate in the AddRangeData binding surface.",
                "source_quote": _short(p),
                "section": h,
            }
        )
    return facts


def extract_facts_mekko(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    pair = _find_paragraph(parsed, "ImportMekkoGraphicsCharts") or _find_paragraph(
        parsed, "Import Mekko Graphics charts to think-cell"
    )
    if pair:
        h, p = pair
        facts.append(
            {
                "topic": "mekko_import_api",
                "fact": "Mekko Graphics charts are imported via the dedicated ImportMekkoGraphicsCharts API (and inspected via GetMekkoGraphicsXML). NOT addressable via .ppttc data automation; this is a parallel COM surface.",
                "source_quote": _short(p),
                "section": h,
            }
        )
    return facts


EXTRACTORS = {
    "official-en-jsondataautomation.html": extract_facts_jsondataautomation,
    "official-en-introductionautomation.html": extract_facts_introductionautomation,
    "official-en-exceldataautomation.html": extract_facts_exceldataautomation,
    "official-en-api.html": extract_facts_api,
    "official-en-exceldatalinks.html": extract_facts_exceldatalinks,
    "official-en-element-datasheets.html": extract_facts_element_datasheets,
    "official-en-tables-with-datasheets.html": extract_facts_tables_with_datasheets,
    "official-en-table.html": extract_facts_table,
    "official-en-import-mekko-graphics.html": extract_facts_mekko,
}


# Per-doc resolution claims (which open questions does this doc answer?)
RESOLVES = {
    "official-en-jsondataautomation.html": ["A_ppttc_schema", "C_presentations_open"],
    "official-en-introductionautomation.html": ["B_named_ranges", "E_element_naming"],
    "official-en-exceldataautomation.html": ["D_updatechart_vs_ppttc", "C_presentations_open"],
    "official-en-api.html": ["D_updatechart_vs_ppttc"],
    "official-en-exceldatalinks.html": ["B_named_ranges"],
    "official-en-element-datasheets.html": ["A_ppttc_schema"],
    "official-en-tables-with-datasheets.html": ["E_element_naming"],
    "official-en-table.html": [],
    "official-en-import-mekko-graphics.html": [],
}


def collect_json_examples(parsed: dict[str, Any]) -> list[dict[str, str]]:
    examples = []
    for sec in parsed["sections"]:
        for code in sec.get("code_blocks", []):
            stripped = code.strip()
            if (
                stripped.startswith(("[", "{"))
                or "ppttc" in stripped.lower()
                or "AddRangeData" in stripped
            ):
                examples.append(
                    {
                        "section": sec["heading"],
                        "snippet": stripped[:600],
                    }
                )
    return examples


ANSWERS = {
    "A_ppttc_schema": (
        "Canonical schema is the file ppttc/ppttc-schema.json shipped INSIDE the think-cell installation "
        "(alongside ppttc/template.pptx and ppttc/sample.ppttc) [official-en-jsondataautomation.html]. "
        "Top-level shape: an ARRAY of template-objects. Each template-object has exactly two keys: "
        "'template' (string path or HTTP/HTTPS URL) and 'data' (array of {name, table} pairs). "
        "Multiple top-level entries produce multiple template copies in the output deck, in array order. "
        "Cell data types: string, number, date (YYYY-MM-DD ISO 8601), percentage (no % sign, dot decimal), "
        "fill (hex or rgb() — added to a number/string key), null (empty cell, no quotes). "
        "Text-field/Harvey-ball/checkbox 'table' = single sub-array with single typed object. "
        "Chart/table 'table' = 2D sub-arrays = datasheet rows. First row of chart datasheet has a leading "
        "null + category labels; [] denotes an empty row (semantic — shifts color-scheme assignment). "
        "Render mode controlled at file level (no flags inside JSON itself); SaveAs path is set in the "
        "renderer call (tcXlAddIn.SaveAs in COM, or -o flag for ppttc.exe), NOT in the .ppttc body. "
        "Source: official-en-jsondataautomation.html sections #json-schema-example-files, #sect_json-elements, "
        "#sect_json-cell-data-types, #sect_first-rows, #sect_empty-rows, #sect_json-command-line."
    ),
    "B_named_ranges": (
        "Excel NAMED RANGES are NOT the binding mechanism. The .ppttc 'name' key refers to the "
        "AddRangeData Name field on the PowerPoint template element, registered via the element's "
        "mini toolbar in PowerPoint. This is think-cell template metadata (chart/table/Harvey-ball/"
        "checkbox/automation-text-field-level), NOT an Excel workbook-level Name. That is exactly why "
        "openpyxl reports 0 named ranges on Jesper-Tyrer-land.xlsx — there are none, by design. The 42 "
        "names like S01_DirectorName are AddRangeData names embedded in the .pptx template's element "
        "metadata; the .ppttc references them; the workbook is decoupled. "
        "PresentationFromTemplate uses Excel LINKS (cell-range references stored in the chart's "
        "definition), which is also separate from Excel's Name Manager. "
        "Source: official-en-introductionautomation.html section #sect_report-automation-templates, "
        "official-en-exceldataautomation.html #sect_updatebatch-description (Names are case-insensitive)."
    ),
    "C_presentations_open": (
        "There is no documented PowerPoint-COM 'Presentations.Open(.ppttc)' entry point. The documented "
        "ways to render a .ppttc are: (1) double-click in File Explorer/Finder — installer registers the "
        ".ppttc extension with think-cell; (2) command-line: 'ppttc.exe <input.ppttc> -o <output.pptx>' "
        "(Windows-only; ppttc.exe lives in the 'ppttc' subfolder of the install); (3) HTTP POST to "
        "tcserver.exe with media type application/vnd.think-cell.ppttc+json — server returns the .pptx. "
        "(4) for Excel-linked templates only, tcXlAddIn.PresentationFromTemplate(...) returns a "
        "PowerPoint.Presentation object via COM. There is NO documented flag to suppress PowerPoint UI "
        "in modes (1)/(2); ppttc.exe -o is the closest to a headless render. tcserver.exe HTTP POST is "
        "the documented headless path. "
        "Source: official-en-jsondataautomation.html #sect_jsoncreatepresentation, #sect_json-command-line, "
        "#sect_jsontcserver."
    ),
    "D_updatechart_vs_ppttc": (
        ".ppttc and UpdateBatch are TWO DIFFERENT API surfaces that BOTH key on AddRangeData names. "
        "(a) .ppttc = JSON file consumed by ppttc.exe / file-association / tcserver.exe; data is in the "
        "JSON. (b) UpdateBatch = COM API on tcXlAddIn that takes Excel ranges and a target Presentation. "
        "(c) UpdateChart is DEPRECATED — UpdateBatch supersedes it; UpdateChart still runs but lacks "
        "AddRangeImage and is slow on big decks. (d) PresentationFromTemplate is a third path that "
        "creates a NEW deck from a template whose elements have Excel LINKS (not AddRangeData names). "
        "Composability: PresentationFromTemplate output can be fed back as a new template for another "
        "PresentationFromTemplate call (chained Excel-link refresh). UpdateBatch can be applied to any "
        "deck/template whose elements have AddRangeData names — including the output of "
        "PresentationFromTemplate. So the docs DO support 'PresentationFromTemplate then UpdateBatch' "
        "as a refresh chain, provided the elements have names. "
        "Source: official-en-api.html #sect_apireference, official-en-exceldataautomation.html "
        "#sect_introduction-excel-automation, #sect_updatebatch."
    ),
    "E_element_naming": (
        "The element name is set IN THE POWERPOINT TEMPLATE via the element's mini-toolbar field "
        "AddRangeData Name (and AddRangeImage Name for Excel-only table images). NOT registered in a "
        "separate file, NOT in Excel, NOT in the .ppttc — the .ppttc only REFERENCES the name. The same "
        "name applies to charts, tables, Harvey balls, checkboxes, and automation text fields (the "
        "<<>>-style two-angle-bracket placeholder inserted via Insert > Elements > Automation Text "
        "Field). Names are case-insensitive. Two elements with the same name receive the same data. "
        "Source: official-en-introductionautomation.html #sect_report-automation-templates, "
        "official-en-exceldataautomation.html #sect_updatebatch-description."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC_DIR)
    parser.add_argument("--out-base", type=Path, default=OUT_BASE)
    args = parser.parse_args()

    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_base / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(args.src.glob("official-en-*.html"))
    docs = []
    for fp in files:
        parsed = parse_doc(fp)
        extractor = EXTRACTORS.get(fp.name)
        key_facts = extractor(parsed) if extractor else []
        json_examples = (
            collect_json_examples(parsed) if "json" in fp.name or "automation" in fp.name else []
        )
        resolved = RESOLVES.get(fp.name, [])
        unresolved_note: list[str] = []
        if not resolved:
            unresolved_note.append(
                "Doc has no specific open-question mapping; treated as supplementary context."
            )
        docs.append(
            {
                "filename": fp.name,
                "title": parsed["title"],
                "section_count": parsed["section_count"],
                "word_count": parsed["word_count"],
                "key_facts": key_facts,
                "json_schema_examples": json_examples[:6],
                "open_questions_resolved": resolved,
                "unresolved_notes": unresolved_note,
            }
        )

    extraction = {
        "schema": "thinkcell-official-docs-extraction/v1",
        "timestamp_utc": ts,
        "source_dir": str(args.src.relative_to(ROOT))
        if args.src.is_relative_to(ROOT)
        else str(args.src),
        "doc_count": len(docs),
        "total_words": sum(d["word_count"] for d in docs),
        "docs": docs,
        "answers_to_open_questions": ANSWERS,
        "open_questions_unresolved_by_corpus": [
            "Whether tcserver.exe accepts a .ppttc that itself omits 'template' (remote template via URL is documented; an in-memory template upload is NOT documented).",
            "Whether AddRangeData Name length / character constraints are bounded (no character-set or max-length spec given).",
            "Whether SaveAs absolute paths in PresentationFromTemplate accept UNC / network paths (only local-file examples shown).",
            "Whether ppttc.exe exposes a headless / no-UI flag — only -o is documented.",
            "How tcserver.exe authenticates POST requests (no auth section in docs; the cloud-side BCrypt+HMAC scheme remains unconfirmed by these official files).",
        ],
    }

    out_path = out_dir / "extraction.json"
    out_path.write_text(json.dumps(extraction, indent=2) + "\n", encoding="utf-8")
    print(f"docs={len(docs)} total_words={extraction['total_words']}")
    print(f"out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
