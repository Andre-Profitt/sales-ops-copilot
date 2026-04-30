"""Build per-director think-cell-ready PowerPoint templates.

This module takes the branded placeholder deck at `assets/LAND_template.pptx`,
bakes the non-think-cell slides with native PowerPoint text/tables, then
injects named think-cell chart donors into the analytical slides at the OpenXML
package layer. The generated template is the `.pptx` that `.ppttc` should
reference.
"""

from __future__ import annotations

import copy
import math
import numbers
import posixpath
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parent.parent

BAR_COLUMN_DONOR = Path(
    "/Library/Application Support/Microsoft/think-cell/templates/think-cell Charts/Bar, Column/Bar, Column.potx"
)
MEKKO_DONOR = Path(
    "/Library/Application Support/Microsoft/think-cell/templates/think-cell Charts/Mekko/Mekko.potx"
)
WATERFALL_DONOR = Path(
    "/Library/Application Support/Microsoft/think-cell/templates/think-cell Charts/Waterfall/Waterfall.potx"
)

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)

COLOR_HEADER_FILL = RGBColor(0x08, 0x3E, 0xA7)
COLOR_HEADER_TEXT = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_ROW_ALT = RGBColor(0xF2, 0xF4, 0xF7)
COLOR_BODY_TEXT = RGBColor(0x1A, 0x1D, 0x31)
COLOR_MUTED_TEXT = RGBColor(0x66, 0x66, 0x66)
COLOR_RULE = RGBColor(0xD6, 0xDE, 0xEA)
COLOR_ACCENT = RGBColor(0xEF, 0x3E, 0x4A)


@dataclass(frozen=True)
class DonorSlide:
    template_path: Path
    slide_number: int
    exclude_names: tuple[str, ...] = ()
    exclude_text_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartInjection:
    slide_number: int
    chart_name: str
    donor: DonorSlide
    text_replacements: tuple[tuple[str, str], ...] = ()


COMMON_DONOR_EXCLUDES = (
    "Title 4",
    "tc_columnhead",
    "tc_columnheadline",
    "Rectangle 18",
    "Text Placeholder 15",
    "Rechteck 137",
)

BAR_DONOR = DonorSlide(
    template_path=BAR_COLUMN_DONOR,
    slide_number=6,
    exclude_names=COMMON_DONOR_EXCLUDES
    + (
        "Arrow: Right 20",
        "Arrow: Right 54",
        "Straight Connector 355",
        "Straight Connector 361",
        "Straight Connector 55",
        "Rectangle 124",
        "Rectangle 123",
    ),
    exclude_text_prefixes=(
        "Margin",
        "Market avg.",
        "Our target",
        "Our brand",
        "Competitors",
    ),
)

COLUMN_DONOR = DonorSlide(
    template_path=BAR_COLUMN_DONOR,
    slide_number=3,
    exclude_names=COMMON_DONOR_EXCLUDES
    + (
        "Straight Connector 113",
        "Straight Connector 114",
        "Straight Connector 115",
        "Oval 33",
        "Rectangle 19",
        "Rectangle 22",
        "Rectangle 2",
        "Rectangle 10",
    ),
)

COMBO_DONOR = DonorSlide(
    template_path=BAR_COLUMN_DONOR,
    slide_number=4,
    exclude_names=COMMON_DONOR_EXCLUDES,
)

MEKKO_DONOR_SPEC = DonorSlide(
    template_path=MEKKO_DONOR,
    slide_number=1,
    exclude_names=COMMON_DONOR_EXCLUDES,
)

WATERFALL_DONOR_SPEC = DonorSlide(
    template_path=WATERFALL_DONOR,
    slide_number=1,
    exclude_names=COMMON_DONOR_EXCLUDES,
)

CHART_INJECTIONS: tuple[ChartInjection, ...] = (
    ChartInjection(
        slide_number=4,
        chart_name="S04_PipeMovement",
        donor=WATERFALL_DONOR_SPEC,
        text_replacements=(
            ("Revenues, costs, totals [USD m]", "ARR (EUR)"),
            ("BU1", "Additions"),
            ("BU2", "Outflows"),
            ("Totals", "Total"),
        ),
    ),
    ChartInjection(
        slide_number=5,
        chart_name="S05_PipelineByStage",
        donor=BAR_DONOR,
    ),
    ChartInjection(
        slide_number=6,
        chart_name="S06_PipelineAging",
        donor=BAR_DONOR,
    ),
    ChartInjection(
        slide_number=13,
        chart_name="S13_ForecastCategory",
        donor=COLUMN_DONOR,
        text_replacements=(("User count [K]", "ARR (EUR)"),),
    ),
    ChartInjection(
        slide_number=15,
        chart_name="S15_ByOwner",
        donor=BAR_DONOR,
    ),
    ChartInjection(
        slide_number=16,
        chart_name="S16_StageByIndustry",
        donor=MEKKO_DONOR_SPEC,
        text_replacements=(
            ("Market size", "Stage share"),
            ("Revenue mix [USD m]", "Industry ARR mix"),
        ),
    ),
    ChartInjection(
        slide_number=17,
        chart_name="S17_TerritoryPerformance",
        donor=BAR_DONOR,
    ),
    ChartInjection(
        slide_number=18,
        chart_name="S18_WinsLossesQTD",
        donor=COLUMN_DONOR,
        text_replacements=(("User count [K]", "Value (EUR)"),),
    ),
    ChartInjection(
        slide_number=19,
        chart_name="S19_Velocity",
        donor=COMBO_DONOR,
        text_replacements=(
            ("Revenue [m]", "Median age (days)"),
            ("Revenue", "Median age (days)"),
            ("Units sold", "# Open opps"),
        ),
    ),
    ChartInjection(
        slide_number=21,
        chart_name="S21_ConcentrationRiskChart",
        donor=COLUMN_DONOR,
        text_replacements=(("User count [K]", "Share (%)"),),
    ),
    ChartInjection(
        slide_number=22,
        chart_name="S22_StaleActivity",
        donor=BAR_DONOR,
    ),
    ChartInjection(
        slide_number=25,
        chart_name="S25_PipelineCreationVelocity",
        donor=COMBO_DONOR,
        text_replacements=(
            ("Revenue [m]", "New ARR (EUR)"),
            ("Revenue", "New ARR (EUR)"),
            ("Units sold", "# New opps"),
        ),
    ),
)


def build_director_template(
    *,
    artifacts: Any,
    base_template_path: Path,
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
    model: Any,
    legacy: Any,
) -> Path:
    """Create the director-specific `.pptx` consumed by `.ppttc`."""

    out_path = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}-template.pptx"

    prs = Presentation(str(base_template_path))
    _replace_tokens_in_deck(
        prs,
        {
            "{director_name}": artifacts.name,
            "{period}": artifacts.period,
            "{scope_label}": artifacts.scope_label,
        },
    )

    _fill_exec_summary(prs.slides[1], trends=trends, brief_sections=brief_sections)
    _fill_legacy_table_slide(prs.slides[6], legacy, "Top_Deals_Land", "A1:H11", _named_deals_widths())
    _fill_legacy_table_slide(prs.slides[7], legacy, "Top_Deals_Expand", "A1:H11", _named_deals_widths())
    _fill_pending_approval_slide(prs.slides[8], legacy)
    _fill_renewal_pipeline_slide(prs.slides[10], legacy)
    _fill_grr_proxy_slide(prs.slides[11], model)
    _fill_concentration_slide(prs.slides[20], model)
    _fill_sales_velocity_slide(prs.slides[22], model)
    _fill_account_expansion_slide(prs.slides[23], model)
    _fill_action_items_slide(prs.slides[25], trends)
    _fill_risks_outlook_slide(prs.slides[26], trends=trends, brief_sections=brief_sections)

    prs.save(str(out_path))
    _inject_donor_charts(out_path)
    return out_path


def template_has_named_elements(template_path: Path) -> bool:
    """Detect generated templates by looking for non-empty think-cell OLE names."""

    return bool(template_named_elements(template_path))


def template_named_elements(template_path: Path) -> set[str]:
    """Return all automation names discoverable in a think-cell template."""

    binary_pattern = re.compile(rb"<m_strName>([^<]+)</m_strName>")
    escaped_xml_pattern = re.compile(r"&lt;m_strName&gt;([^<]+)&lt;/m_strName&gt;")

    names: set[str] = set()
    with ZipFile(template_path) as zf:
        for name in zf.namelist():
            if name.startswith("ppt/embeddings/") and name.endswith(".bin"):
                match = binary_pattern.search(zf.read(name))
                if match:
                    names.add(match.group(1).decode("utf-8"))
                continue
            if name.startswith("ppt/slides/") and name.endswith(".xml"):
                text = zf.read(name).decode("utf-8", "ignore")
                names.update(escaped_xml_pattern.findall(text))
    return names


def _replace_tokens_in_deck(prs: Presentation, tokens: dict[str, str]) -> None:
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text
            if not text:
                continue
            replaced = text
            for needle, value in tokens.items():
                replaced = replaced.replace(needle, value)
            if replaced != text:
                shape.text_frame.text = replaced


def _find_shape(slide: Any, name: str) -> Any | None:
    for shape in slide.shapes:
        if shape.name == name:
            return shape
    return None


def _remove_shape(shape: Any | None) -> None:
    if shape is None:
        return
    element = shape._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _content_bounds(slide: Any) -> tuple[Emu, Emu, Emu, Emu]:
    box = _find_shape(slide, "Rectangle 5")
    if box is not None:
        return box.left, box.top, box.width, box.height
    placeholder = _find_shape(slide, "Content Placeholder 1")
    if placeholder is None:
        raise RuntimeError(f"Slide {slide.slide_id} does not contain the expected content area")
    return placeholder.left, placeholder.top, placeholder.width, placeholder.height


def _clear_standard_placeholder(slide: Any) -> tuple[Emu, Emu, Emu, Emu]:
    bounds = _content_bounds(slide)
    _remove_shape(_find_shape(slide, "Content Placeholder 1"))
    _remove_shape(_find_shape(slide, "Rectangle 5"))
    return bounds


def _clear_exec_placeholder(slide: Any) -> None:
    _remove_shape(_find_shape(slide, "Rectangle 9"))


def _shape_text_frame(shape: Any) -> Any:
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    return tf


def _set_paragraph_text(
    paragraph: Any,
    text: str,
    *,
    font_size: Pt,
    bold: bool = False,
    color: RGBColor = COLOR_BODY_TEXT,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    italic: bool = False,
) -> None:
    paragraph.alignment = align
    paragraph.space_after = Pt(4)
    run = paragraph.add_run()
    run.text = text
    run.font.size = font_size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Aptos"


def _add_textbox(
    slide: Any,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    *,
    font_size: Pt,
    bold: bool = False,
    color: RGBColor = COLOR_BODY_TEXT,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    italic: bool = False,
) -> Any:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = _shape_text_frame(box)
    paragraph = tf.paragraphs[0]
    _set_paragraph_text(
        paragraph,
        text,
        font_size=font_size,
        bold=bold,
        color=color,
        align=align,
        italic=italic,
    )
    return box


def _add_rule(slide: Any, left: Emu, top: Emu, width: Emu, *, color: RGBColor = COLOR_RULE) -> None:
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Emu(12700))
    line.fill.solid()
    line.fill.fore_color.rgb = color
    line.line.fill.background()


def _format_currency(value: Any) -> str:
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return str(value or "")
    numeric = float(value)
    if not math.isfinite(numeric):
        return ""
    absolute = abs(numeric)
    if absolute >= 1_000_000:
        return f"EUR {numeric / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"EUR {numeric:,.0f}"
    return f"EUR {numeric:.0f}"


def _format_percentage(value: Any) -> str:
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return str(value or "")
    numeric = float(value)
    if not math.isfinite(numeric):
        return ""
    return f"{numeric * 100:.1f}%"


def _format_table_cell(header: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    header_lc = header.lower()
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            return ""
        if "%" in header or "proxy" in header_lc:
            return _format_percentage(numeric)
        if "arr" in header_lc or "acv" in header_lc or "eur" in header_lc or "value" == header_lc:
            return _format_currency(numeric)
        if header.strip() == "#" or "score" in header_lc or "motions" in header_lc or "days" in header_lc:
            return str(int(round(numeric)))
        return f"{numeric:,.1f}" if numeric % 1 else str(int(numeric))

    return str(value)


def _styled_table(
    slide: Any,
    *,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    headers: list[str],
    rows: list[list[str]],
    widths: tuple[float, ...],
    right_align_cols: tuple[int, ...] = (),
) -> None:
    n_rows = len(rows) + 1
    shape = slide.shapes.add_table(n_rows, len(headers), left, top, width, height)
    table = shape.table

    total = sum(widths)
    for idx, fraction in enumerate(widths):
        table.columns[idx].width = Emu(int(int(width) * fraction / total))

    row_height = Emu(int(int(height) / max(1, n_rows)))
    for row in table.rows:
        row.height = row_height

    body_font = Pt(10)
    if len(rows) >= 10:
        body_font = Pt(8.5)
    if len(rows) >= 14:
        body_font = Pt(7.5)
    header_font = Pt(max(8, body_font.pt + 1))

    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_HEADER_FILL
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.margin_left = Emu(38100)
        tf.margin_right = Emu(38100)
        tf.margin_top = Emu(19050)
        tf.margin_bottom = Emu(19050)
        tf.clear()
        _set_paragraph_text(
            tf.paragraphs[0],
            header,
            font_size=header_font,
            bold=True,
            color=COLOR_HEADER_TEXT,
            align=PP_ALIGN.RIGHT if col_idx in right_align_cols else PP_ALIGN.LEFT,
        )

    for row_idx, row_values in enumerate(rows, start=1):
        for col_idx, value in enumerate(row_values):
            cell = table.cell(row_idx, col_idx)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_ROW_ALT if row_idx % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF)
            tf = cell.text_frame
            tf.margin_left = Emu(38100)
            tf.margin_right = Emu(38100)
            tf.margin_top = Emu(19050)
            tf.margin_bottom = Emu(19050)
            tf.clear()
            _set_paragraph_text(
                tf.paragraphs[0],
                value,
                font_size=body_font,
                color=COLOR_BODY_TEXT,
                align=PP_ALIGN.RIGHT if col_idx in right_align_cols else PP_ALIGN.LEFT,
            )


def _trim_lines(lines: list[str]) -> list[str]:
    out = lines[:]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _strip_markdown_inline(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "").replace("_", "").strip()


def _extract_headline_bullets(brief_sections: dict[str, list[str]]) -> list[str]:
    bullets: list[str] = []
    for line in brief_sections.get("Headline", []):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(_strip_markdown_inline(stripped[2:].strip()))
    return bullets


def _extract_risk_claims(trends: dict[str, Any]) -> list[str]:
    claims: list[str] = []
    for risk in trends.get("risks", []):
        claim = str(risk.get("claim") or "").strip()
        if claim:
            claims.append(claim)
    return claims


def _extract_action_item_claims(trends: dict[str, Any], *, limit: int | None = None) -> list[str]:
    claims: list[str] = []
    for item in trends.get("action_items", []):
        claim = str(item.get("claim") or "").strip()
        if claim:
            claims.append(claim)
    return claims if limit is None else claims[:limit]


def _exec_summary_lists(
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    left_items = _extract_headline_bullets(brief_sections)
    if not left_items:
        left_items = _extract_action_item_claims(trends, limit=3)

    right_items = _extract_risk_claims(trends)
    if not right_items:
        right_items = _extract_action_item_claims(trends, limit=3)

    return left_items or ["No highlights generated."], right_items or ["No risks generated."]


def _risks_outlook_lines(trends: dict[str, Any], brief_sections: dict[str, list[str]]) -> list[str]:
    risks = _extract_risk_claims(trends)
    if not risks:
        risks = _extract_action_item_claims(trends, limit=4)
    headlines = _extract_headline_bullets(brief_sections)
    if headlines:
        risks.append(f"Outlook: {headlines[0]}")
    return risks or ["No risks or outlook generated."]


def _fill_exec_summary(slide: Any, *, trends: dict[str, Any], brief_sections: dict[str, list[str]]) -> None:
    _clear_exec_placeholder(slide)
    left_items, right_items = _exec_summary_lists(trends, brief_sections)
    left = _find_shape(slide, "Content Placeholder 1")
    right = _find_shape(slide, "Content Placeholder 3")
    if left is None or right is None:
        raise RuntimeError("Exec summary slide no longer matches the template contract")

    for shape, items in ((left, left_items), (right, right_items)):
        tf = _shape_text_frame(shape)
        for idx, item in enumerate(items):
            paragraph = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            _set_paragraph_text(paragraph, f"- {item}", font_size=Pt(17), color=COLOR_BODY_TEXT)


def _last_nonempty_row(
    workbook: Any,
    sheet_name: str,
    *,
    start_row: int,
    columns: list[str],
    max_row: int | None = None,
) -> int:
    ws = workbook.workbook[sheet_name]
    limit = max_row or ws.max_row
    last = start_row
    for row_idx in range(start_row, limit + 1):
        if any(workbook.cell_value(sheet_name, f"{column}{row_idx}") not in (None, "") for column in columns):
            last = row_idx
    return last


def _matrix_rows(workbook: Any, sheet_name: str, cell_range: str) -> list[list[Any]]:
    return workbook.matrix(sheet_name, cell_range)


def _formatted_rows(matrix: list[list[Any]]) -> list[list[str]]:
    headers = [str(cell or "") for cell in matrix[0]]
    rows: list[list[str]] = []
    for row in matrix[1:]:
        rows.append([_format_table_cell(header, value) for header, value in zip(headers, row)])
    return rows


def _named_deals_widths() -> tuple[float, ...]:
    return (0.05, 0.18, 0.30, 0.12, 0.10, 0.11, 0.06, 0.08)


def _fill_legacy_table_slide(
    slide: Any,
    legacy: Any,
    sheet_name: str,
    cell_range: str,
    widths: tuple[float, ...],
) -> None:
    left, top, width, height = _clear_standard_placeholder(slide)
    matrix = _matrix_rows(legacy, sheet_name, cell_range)
    headers = [str(cell or "") for cell in matrix[0]]
    rows = _formatted_rows(matrix)
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=height - Emu(127000),
        headers=headers,
        rows=[row for row in rows if any(cell for cell in row)],
        widths=widths,
        right_align_cols=(0, 6, 7),
    )


def _fill_pending_approval_slide(slide: Any, legacy: Any) -> None:
    last_row = _last_nonempty_row(
        legacy,
        "Pending_Commercial_Approval",
        start_row=3,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    left, top, width, height = _clear_standard_placeholder(slide)
    matrix = _matrix_rows(legacy, "Pending_Commercial_Approval", f"A3:H{last_row}")
    headers = [str(cell or "") for cell in matrix[0]]
    rows = _formatted_rows(matrix)
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=height - Emu(127000),
        headers=headers,
        rows=[row for row in rows if any(cell for cell in row)],
        widths=(0.05, 0.18, 0.30, 0.12, 0.10, 0.11, 0.07, 0.07),
        right_align_cols=(0, 7),
    )


def _fill_renewal_pipeline_slide(slide: Any, legacy: Any) -> None:
    last_row = _last_nonempty_row(
        legacy,
        "At_Risk_Renewals",
        start_row=1,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    left, top, width, height = _clear_standard_placeholder(slide)
    matrix = _matrix_rows(legacy, "At_Risk_Renewals", f"A1:H{last_row}")
    headers = [str(cell or "") for cell in matrix[0]]
    rows = _formatted_rows(matrix)
    filtered_rows = [row for row in rows if any(cell for cell in row)]
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=height - Emu(127000),
        headers=headers,
        rows=filtered_rows,
        widths=(0.05, 0.22, 0.14, 0.11, 0.12, 0.11, 0.14, 0.11),
        right_align_cols=(0, 5, 7),
    )
    if len(filtered_rows) == 1 and filtered_rows[0][0].startswith("(no Renewal"):
        _add_textbox(
            slide,
            left + Emu(127000),
            top + height - Emu(381000),
            width - Emu(254000),
            Emu(190500),
            "No Harvey-ball row was added because there are no in-scope high-risk renewals this period.",
            font_size=Pt(9),
            color=COLOR_MUTED_TEXT,
            italic=True,
        )


def _fill_grr_proxy_slide(slide: Any, model: Any) -> None:
    left, top, width, height = _clear_standard_placeholder(slide)
    matrix = _matrix_rows(model, "Retention", "A1:B5")
    headers = [str(matrix[0][0] or ""), str(matrix[0][1] or "")]
    rows = [
        [str(matrix[1][0] or ""), _format_currency(matrix[1][1])],
        [str(matrix[2][0] or ""), _format_currency(matrix[2][1])],
        [str(matrix[3][0] or ""), _format_percentage(matrix[3][1])],
    ]
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=Emu(1524000),
        headers=headers,
        rows=rows,
        widths=(0.66, 0.34),
        right_align_cols=(1,),
    )
    footnote = str(matrix[4][0] or "").strip()
    if footnote:
        _add_textbox(
            slide,
            left + Emu(63500),
            top + Emu(1714500),
            width - Emu(127000),
            height - Emu(1778000),
            footnote,
            font_size=Pt(10),
            color=COLOR_MUTED_TEXT,
            italic=True,
        )


def _fill_concentration_slide(slide: Any, model: Any) -> None:
    _remove_shape(_find_shape(slide, "Rectangle 5"))
    _remove_shape(_find_shape(slide, "Content Placeholder 1"))
    left = Emu(839787)
    top = Emu(1143000)
    width = Emu(10512788)
    metrics = [
        ("Largest account", str(model.cell_value("Concentration", "B5") or "")),
        ("Largest ARR", _format_currency(model.cell_value("Concentration", "B6"))),
        ("Pipeline share", _format_percentage(model.cell_value("Concentration", "B7"))),
        ("25% threshold", str(model.cell_value("Concentration", "B8") or "")),
    ]
    tile_width = Emu(2520000)
    for idx, (label, value) in enumerate(metrics):
        x = left + Emu(idx * 2520000)
        _add_textbox(slide, x, top, tile_width, Emu(180000), label, font_size=Pt(10), color=COLOR_MUTED_TEXT)
        _add_textbox(slide, x, top + Emu(185000), tile_width, Emu(320000), value, font_size=Pt(18), bold=True)
        if idx < len(metrics) - 1:
            _add_rule(slide, x + tile_width - Emu(80000), top + Emu(63500), Emu(12700), color=COLOR_RULE)


def _fill_sales_velocity_slide(slide: Any, model: Any) -> None:
    left, top, width, height = _clear_standard_placeholder(slide)
    metrics = [
        ("Open L+E opps", model.cell_value("Sales_Velocity", "B2"), model.cell_value("Sales_Velocity", "C2")),
        ("Win rate", _format_percentage(model.cell_value("Sales_Velocity", "B3")), model.cell_value("Sales_Velocity", "C3")),
        ("Avg deal size", _format_currency(model.cell_value("Sales_Velocity", "B4")), model.cell_value("Sales_Velocity", "C4")),
        ("Avg cycle days", f"{int(round(float(model.cell_value('Sales_Velocity', 'B5'))))} days", model.cell_value("Sales_Velocity", "C5")),
        ("Velocity", f"{_format_currency(model.cell_value('Sales_Velocity', 'B6'))} / day", model.cell_value("Sales_Velocity", "C6")),
    ]
    column_width = Emu(int(int(width) / 5))
    for idx, (label, value, note) in enumerate(metrics):
        x = left + Emu(idx * int(column_width))
        if idx > 0:
            _add_rule(slide, x - Emu(32000), top + Emu(127000), Emu(12700), color=COLOR_RULE)
        _add_textbox(slide, x, top + Emu(63500), column_width - Emu(63500), Emu(160000), label, font_size=Pt(10), color=COLOR_MUTED_TEXT)
        _add_textbox(slide, x, top + Emu(215000), column_width - Emu(63500), Emu(500000), str(value), font_size=Pt(20), bold=True)
        note_text = str(note or "")
        _add_textbox(
            slide,
            x,
            top + Emu(770000),
            column_width - Emu(63500),
            height - Emu(900000),
            note_text,
            font_size=Pt(9),
            color=COLOR_MUTED_TEXT,
        )


def _fill_account_expansion_slide(slide: Any, model: Any) -> None:
    left, top, width, height = _clear_standard_placeholder(slide)
    matrix = _matrix_rows(model, "Account_Expansion", "A1:F16")
    headers = [str(cell or "") for cell in matrix[0]]
    rows = _formatted_rows(matrix)
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=height - Emu(127000),
        headers=headers,
        rows=[row for row in rows if any(cell for cell in row)],
        widths=(0.05, 0.34, 0.14, 0.14, 0.18, 0.09),
        right_align_cols=(0, 2, 3, 4, 5),
    )


def _action_items_table(trends: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for idx, item in enumerate(trends.get("action_items", []), start=1):
        rows.append(
            [
                str(idx),
                str(item.get("priority") or "").upper(),
                str(item.get("rule_id") or ""),
                str(item.get("claim") or ""),
                str(item.get("suggested_action") or ""),
                str(item.get("due_date") or ""),
                str(item.get("owner") or ""),
            ]
        )
    return rows or [["", "", "", "(no action items generated)", "", "", ""]]


def _fill_action_items_slide(slide: Any, trends: dict[str, Any]) -> None:
    left, top, width, height = _clear_standard_placeholder(slide)
    headers = ["#", "Priority", "Rule", "Claim", "Suggested action", "Due date", "Owner"]
    _styled_table(
        slide,
        left=left + Emu(63500),
        top=top + Emu(63500),
        width=width - Emu(127000),
        height=height - Emu(127000),
        headers=headers,
        rows=_action_items_table(trends),
        widths=(0.04, 0.09, 0.10, 0.28, 0.25, 0.10, 0.14),
        right_align_cols=(0,),
    )


def _fill_risks_outlook_slide(
    slide: Any,
    *,
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
) -> None:
    _remove_shape(_find_shape(slide, "Rectangle 5"))
    content = _find_shape(slide, "Content Placeholder 1")
    if content is None:
        raise RuntimeError("Risks & outlook slide no longer matches the template contract")
    tf = _shape_text_frame(content)
    for idx, line in enumerate(_risks_outlook_lines(trends, brief_sections)):
        paragraph = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        _set_paragraph_text(paragraph, f"- {line}", font_size=Pt(16), color=COLOR_BODY_TEXT)


def _inject_donor_charts(pptx_path: Path) -> None:
    with ZipFile(pptx_path) as zf:
        target_entries = {name: zf.read(name) for name in zf.namelist()}

    ct_root = ET.fromstring(target_entries["[Content_Types].xml"])

    for injection in CHART_INJECTIONS:
        _inject_single_chart(
            target_entries=target_entries,
            ct_root=ct_root,
            injection=injection,
        )

    target_entries["[Content_Types].xml"] = ET.tostring(ct_root, encoding="utf-8", xml_declaration=True)

    tmp_path = pptx_path.with_suffix(".patched.pptx")
    with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED) as zf:
        for name, data in target_entries.items():
            zf.writestr(name, data)
    tmp_path.replace(pptx_path)


def _inject_single_chart(
    *,
    target_entries: dict[str, bytes],
    ct_root: ET.Element,
    injection: ChartInjection,
) -> None:
    slide_name = f"ppt/slides/slide{injection.slide_number}.xml"
    rels_name = _rels_part_name(slide_name)

    target_slide_root = ET.fromstring(target_entries[slide_name])
    target_rels_root = ET.fromstring(target_entries[rels_name])
    target_sp_tree = target_slide_root.find(f".//{{{P_NS}}}spTree")
    if target_sp_tree is None:
        raise RuntimeError(f"{slide_name} is missing spTree")

    _remove_target_placeholder_shapes(target_sp_tree)
    next_shape_id = _max_shape_id(target_sp_tree) + 1

    with ZipFile(injection.donor.template_path) as donor_zip:
        donor_ct_root = ET.fromstring(donor_zip.read("[Content_Types].xml"))
        donor_slide_name = f"ppt/slides/slide{injection.donor.slide_number}.xml"
        donor_rels_name = _rels_part_name(donor_slide_name)
        donor_slide_root = ET.fromstring(donor_zip.read(donor_slide_name))
        donor_rels_root = ET.fromstring(donor_zip.read(donor_rels_name))
        donor_rel_map = _relationship_map(donor_rels_root)
        copier = _PartCopier(
            target_entries=target_entries,
            ct_root=ct_root,
            donor_zip=donor_zip,
            donor_ct_root=donor_ct_root,
            chart_name=injection.chart_name,
        )

        donor_sp_tree = donor_slide_root.find(f".//{{{P_NS}}}spTree")
        if donor_sp_tree is None:
            raise RuntimeError(f"{donor_slide_name} is missing spTree")

        for donor_child in list(donor_sp_tree)[2:]:
            shape_name = _shape_name(donor_child)
            shape_text = _shape_text(donor_child)
            if _exclude_donor_shape(injection.donor, shape_name, shape_text):
                continue

            cloned = copy.deepcopy(donor_child)
            _replace_shape_text(cloned, dict(injection.text_replacements))
            _rewrite_relationships(
                cloned,
                target_slide_name=slide_name,
                target_rels_root=target_rels_root,
                donor_rel_map=donor_rel_map,
                copier=copier,
            )
            _set_shape_id(cloned, next_shape_id)
            next_shape_id += 1
            target_sp_tree.append(cloned)

    target_entries[slide_name] = ET.tostring(target_slide_root, encoding="utf-8", xml_declaration=True)
    target_entries[rels_name] = ET.tostring(target_rels_root, encoding="utf-8", xml_declaration=True)


def _remove_target_placeholder_shapes(sp_tree: ET.Element) -> None:
    for child in list(sp_tree):
        name = _shape_name(child)
        if name in {"Content Placeholder 1", "Rectangle 5"}:
            sp_tree.remove(child)


def _shape_name(element: ET.Element) -> str:
    c_nv_pr = element.find(f".//{{{P_NS}}}cNvPr")
    if c_nv_pr is None:
        c_nv_pr = element.find(f".//{{{A_NS}}}cNvPr")
    return "" if c_nv_pr is None else c_nv_pr.get("name", "")


def _shape_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(f".//{{{A_NS}}}t"))


def _exclude_donor_shape(donor: DonorSlide, shape_name: str, shape_text: str) -> bool:
    if shape_name in donor.exclude_names:
        return True
    return any(shape_text.startswith(prefix) for prefix in donor.exclude_text_prefixes)


def _replace_shape_text(element: ET.Element, replacements: dict[str, str]) -> None:
    for text_node in element.findall(f".//{{{A_NS}}}t"):
        text = text_node.text or ""
        if text in replacements:
            text_node.text = replacements[text]


def _max_shape_id(sp_tree: ET.Element) -> int:
    max_id = 0
    for c_nv_pr in sp_tree.findall(f".//{{{P_NS}}}cNvPr"):
        value = c_nv_pr.get("id")
        if value and value.isdigit():
            max_id = max(max_id, int(value))
    return max_id


def _set_shape_id(element: ET.Element, new_id: int) -> None:
    c_nv_pr = element.find(f".//{{{P_NS}}}cNvPr")
    if c_nv_pr is None:
        c_nv_pr = element.find(f".//{{{A_NS}}}cNvPr")
    if c_nv_pr is not None:
        c_nv_pr.set("id", str(new_id))


def _relationship_map(rels_root: ET.Element) -> dict[str, ET.Element]:
    rels: dict[str, ET.Element] = {}
    for rel in rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
        rel_id = rel.get("Id")
        if rel_id:
            rels[rel_id] = rel
    return rels


class _PartCopier:
    def __init__(
        self,
        *,
        target_entries: dict[str, bytes],
        ct_root: ET.Element,
        donor_zip: ZipFile,
        donor_ct_root: ET.Element,
        chart_name: str,
    ) -> None:
        self.target_entries = target_entries
        self.ct_root = ct_root
        self.donor_zip = donor_zip
        self.donor_ct_root = donor_ct_root
        self.chart_name = chart_name
        self.memo: dict[str, str] = {}

    def copy_part(self, donor_part_name: str) -> str:
        donor_part_name = donor_part_name.lstrip("/")
        if donor_part_name in self.memo:
            return self.memo[donor_part_name]

        target_part_name = _next_available_name(self.target_entries, donor_part_name)
        data = self.donor_zip.read(donor_part_name)
        if target_part_name.endswith(".bin"):
            data = _patch_ole_name(data, self.chart_name)
        self.target_entries[target_part_name] = data
        self.memo[donor_part_name] = target_part_name
        _copy_content_type(self.ct_root, self.donor_ct_root, donor_part_name, target_part_name)

        donor_rels_name = _rels_part_name(donor_part_name)
        if donor_rels_name in self.donor_zip.namelist():
            donor_rels_root = ET.fromstring(self.donor_zip.read(donor_rels_name))
            for rel in donor_rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
                if rel.get("TargetMode") == "External":
                    continue
                donor_child = _resolve_target(donor_part_name, rel.get("Target", ""))
                target_child = self.copy_part(donor_child)
                rel.set("Target", _relative_target(target_part_name, target_child))
            self.target_entries[_rels_part_name(target_part_name)] = ET.tostring(
                donor_rels_root,
                encoding="utf-8",
                xml_declaration=True,
            )
        return target_part_name


def _rewrite_relationships(
    element: ET.Element,
    *,
    target_slide_name: str,
    target_rels_root: ET.Element,
    donor_rel_map: dict[str, ET.Element],
    copier: _PartCopier,
) -> None:
    rewritten_rids: dict[str, str] = {}
    for node in element.iter():
        for attr_name in (f"{{{R_NS}}}id", f"{{{R_NS}}}embed", f"{{{R_NS}}}link"):
            old_rid = node.get(attr_name)
            if not old_rid or old_rid not in donor_rel_map:
                continue
            if old_rid in rewritten_rids:
                node.set(attr_name, rewritten_rids[old_rid])
                continue
            donor_rel = donor_rel_map[old_rid]
            target_mode = donor_rel.get("TargetMode")
            rel_type = donor_rel.get("Type")
            if not rel_type:
                continue
            new_rid = _next_relationship_id(target_rels_root)
            new_rel = ET.SubElement(target_rels_root, f"{{{PKG_REL_NS}}}Relationship")
            new_rel.set("Id", new_rid)
            new_rel.set("Type", rel_type)
            if target_mode == "External":
                new_rel.set("TargetMode", "External")
                new_rel.set("Target", donor_rel.get("Target", ""))
            else:
                donor_target = _resolve_target(target_slide_name, donor_rel.get("Target", ""))
                copied_target = copier.copy_part(donor_target)
                new_rel.set("Target", _relative_target(target_slide_name, copied_target))
            rewritten_rids[old_rid] = new_rid
            node.set(attr_name, new_rid)


def _patch_ole_name(data: bytes, chart_name: str) -> bytes:
    return re.sub(
        rb"<m_strName>.*?</m_strName>",
        f"<m_strName>{chart_name}</m_strName>".encode("utf-8"),
        data,
        count=1,
        flags=re.DOTALL,
    )


def _rels_part_name(part_name: str) -> str:
    directory, filename = posixpath.split(part_name)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolve_target(base_part_name: str, target: str) -> str:
    base_dir = posixpath.dirname("/" + base_part_name)
    resolved = posixpath.normpath(posixpath.join(base_dir, target))
    return resolved.lstrip("/")


def _relative_target(from_part_name: str, to_part_name: str) -> str:
    from_dir = posixpath.dirname("/" + from_part_name)
    return posixpath.relpath("/" + to_part_name, from_dir)


def _next_available_name(entries: dict[str, bytes], donor_part_name: str) -> str:
    donor_part_name = donor_part_name.lstrip("/")
    if donor_part_name not in entries:
        return donor_part_name

    directory, filename = posixpath.split(donor_part_name)
    stem, suffix = _split_filename(filename)
    match = re.match(r"^(.*?)(\d+)$", stem)
    prefix = stem
    counter = 1
    if match:
        prefix = match.group(1)
        counter = int(match.group(2))
    while True:
        counter += 1
        candidate = posixpath.join(directory, f"{prefix}{counter}{suffix}")
        if candidate not in entries:
            return candidate


def _split_filename(filename: str) -> tuple[str, str]:
    if "." not in filename:
        return filename, ""
    stem, suffix = filename.rsplit(".", 1)
    return stem, f".{suffix}"


def _copy_content_type(
    target_ct_root: ET.Element,
    donor_ct_root: ET.Element,
    donor_part_name: str,
    target_part_name: str,
) -> None:
    donor_override = donor_ct_root.find(
        f".//{{{CT_NS}}}Override[@PartName='/{donor_part_name}']"
    )
    if donor_override is not None:
        existing = target_ct_root.find(f".//{{{CT_NS}}}Override[@PartName='/{target_part_name}']")
        if existing is None:
            override = ET.SubElement(target_ct_root, f"{{{CT_NS}}}Override")
            override.set("PartName", f"/{target_part_name}")
            override.set("ContentType", donor_override.get("ContentType", ""))
        return

    extension = target_part_name.rsplit(".", 1)[-1]
    existing_default = target_ct_root.find(f".//{{{CT_NS}}}Default[@Extension='{extension}']")
    if existing_default is not None:
        return
    donor_default = donor_ct_root.find(f".//{{{CT_NS}}}Default[@Extension='{extension}']")
    if donor_default is None:
        return
    default = ET.SubElement(target_ct_root, f"{{{CT_NS}}}Default")
    default.set("Extension", extension)
    default.set("ContentType", donor_default.get("ContentType", ""))


def _next_relationship_id(rels_root: ET.Element) -> str:
    max_id = 0
    for rel in rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
        rel_id = rel.get("Id", "")
        match = re.fullmatch(r"rId(\d+)", rel_id)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"rId{max_id + 1}"
