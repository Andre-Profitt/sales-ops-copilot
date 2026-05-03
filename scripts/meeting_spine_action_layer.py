#!/usr/bin/env python3
"""Programmatic linked action layer for regional meeting-spine decks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DATE = dt.date(2026, 4, 30)
SF_BASE = "https://simcorp.my.salesforce.com/lightning/r"
REPORT_LINKS = {
    "zombie_arr": "https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008nijFMAQ/view",
    "coverage_gap": "https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008nirJMAQ/view",
    "activity_drought": "https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008TZgvMAG/view",
    "approval_gap": "https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008mvx3MAA/view",
    "approval_candidates": "https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008ekp7MAA/view",
}

NAVY = RGBColor(0x1A, 0x1D, 0x31)
MUTED = RGBColor(0x62, 0x68, 0x72)
RULE = RGBColor(0xD8, 0xDE, 0xEA)
PANEL = RGBColor(0xF7, 0xF8, 0xFB)
PANEL_BLUE = RGBColor(0xF2, 0xF6, 0xFC)
PANEL_TEAL = RGBColor(0xEE, 0xF7, 0xF7)
PANEL_AMBER = RGBColor(0xFB, 0xF4, 0xE8)
PANEL_RED = RGBColor(0xFE, 0xF0, 0xF4)
PURPLE = RGBColor(0x3B, 0x00, 0xA5)
TEAL = RGBColor(0x00, 0x8D, 0x8D)
RED = RGBColor(0xE8, 0x00, 0x46)
AMBER = RGBColor(0xD9, 0x89, 0x00)
BLUE = RGBColor(0x08, 0x3E, 0xA7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PALE_GRID = RGBColor(0xEA, 0xED, 0xF2)
BRAND_FONT_NAME = "Aptos"
BRAND_FONT_SIZES = (
    5.5,
    6.0,
    6.5,
    7.0,
    8.0,
    8.5,
    9.0,
    9.5,
    10.0,
    10.5,
    11.5,
    12.0,
    14.0,
    15.0,
    16.0,
    18.0,
    24.0,
)


@dataclass
class Deal:
    id: str
    account: str
    opportunity: str
    owner: str
    stage: str
    close_date: dt.date
    arr_eur: float
    forecast: str
    probability: float
    push: int
    readiness: str
    next_step: str

    @property
    def arr_meur(self) -> float:
        return self.arr_eur / 1_000_000

    @property
    def days_to_close(self) -> int:
        return (self.close_date - SNAPSHOT_DATE).days

    @property
    def risk(self) -> str:
        text = f"{self.readiness} {self.next_step}".casefold()
        if "commercial approval gap" in text or "silent 90d" in text or self.days_to_close <= 0:
            return "high"
        if "no next step" in text or "no activity" in text or self.push >= 3:
            return "watch"
        return "ok"


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _trends_path(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug / "trends.json"


def _workbook_path(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug / "factory" / "connected" / "connected_factory.xlsx"


def _load_trends(period: str, slug: str) -> dict[str, Any]:
    return json.loads(_trends_path(period, slug).read_text(encoding="utf-8"))


def _kpi(trends: dict[str, Any], name: str) -> float:
    for item in trends.get("kpis", []):
        if item.get("name") == name:
            return float(item.get("value") or 0.0)
    return 0.0


def _parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _stage_num(stage: Any) -> int:
    try:
        return int(str(stage or "").split()[0])
    except (ValueError, IndexError):
        return -1


def _meur(value: float, decimals: int = 1) -> str:
    return f"EUR {value / 1_000_000:.{decimals}f}M"


def _pct(value: float) -> str:
    return f"{round(value * 100):.0f}%"


def _brand_font_size(size: float) -> float:
    return min(BRAND_FONT_SIZES, key=lambda allowed: (abs(allowed - size), allowed))


def _normalize_deck_text_style(prs: Presentation) -> None:
    for slide in prs.slides:
        for shape in slide.shapes:
            text_frames = []
            if getattr(shape, "has_text_frame", False):
                text_frames.append(shape.text_frame)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        text_frames.append(cell.text_frame)
            for frame in text_frames:
                for paragraph in frame.paragraphs:
                    for run in paragraph.runs:
                        if not run.text.strip():
                            continue
                        run.font.name = BRAND_FONT_NAME
                        if run.font.size is not None:
                            run.font.size = Pt(_brand_font_size(run.font.size.pt))


def _short(text: Any, limit: int = 46) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def _short_account(account: str, opportunity: str = "") -> str:
    cleaned = account.split("(")[0].strip()
    if len(cleaned) <= 17:
        return cleaned
    words = cleaned.replace(",", "").split()
    if not words:
        return _short(opportunity or account, 15)
    if words[0] in {"PT", "SC", "The"} and len(words) > 1:
        return " ".join(words[:2])
    if len(words[0]) <= 3 and len(words) > 1:
        return " ".join(words[:2])
    return words[0]


def _original_intel(period: str, slug: str) -> dict[str, Any]:
    path = _workbook_path(period, slug)
    if not path.exists():
        return {}
    wb = load_workbook(path, read_only=True, data_only=True)
    if "Raw_Original_Intel" not in wb.sheetnames:
        return {}
    ws = wb["Raw_Original_Intel"]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    headers = [str(value or "").strip() for value in rows[0]]
    output: dict[str, Any] = {}
    for row in rows[1:]:
        record = {headers[idx]: row[idx] if idx < len(row) else None for idx in range(len(headers))}
        key = str(record.get("Key") or "").strip()
        if key:
            output[key] = record.get("Value")
    return output


def _raw_rows(period: str, slug: str, sheet: str) -> list[dict[str, Any]]:
    path = _workbook_path(period, slug)
    if not path.exists():
        return []
    wb = load_workbook(path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        return []
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(value or "").strip() for value in rows[0]]
    output = []
    for row in rows[1:]:
        record = {headers[idx]: row[idx] if idx < len(row) else None for idx in range(len(headers))}
        if any(value not in (None, "") for value in record.values()):
            output.append(record)
    return output


def _deals(trends: dict[str, Any]) -> list[Deal]:
    id_by_name = {
        str(item.get("name") or ""): str(item.get("id") or "")
        for item in trends.get("top_deals_named", [])
    }
    output: list[Deal] = []
    for record in trends.get("q2_deal_readiness", []):
        close_date = _parse_date(record.get("close_date"))
        if not close_date:
            continue
        name = str(record.get("name") or "")
        output.append(
            Deal(
                id=id_by_name.get(name, ""),
                account=str(record.get("account") or ""),
                opportunity=name,
                owner=str(record.get("owner") or ""),
                stage=str(record.get("stage") or ""),
                close_date=close_date,
                arr_eur=float(record.get("arr_eur") or 0),
                forecast=str(record.get("forecast_category") or ""),
                probability=float(record.get("probability") or 0),
                push=int(float(record.get("push_count") or 0)),
                readiness=str(record.get("readiness") or ""),
                next_step=str(record.get("next_step") or ""),
            )
        )
    return output


def _selected_deals(deals: list[Deal], limit: int = 6) -> list[Deal]:
    material = [deal for deal in deals if deal.forecast != "Omitted"]
    material.sort(key=lambda deal: deal.arr_eur, reverse=True)
    return material[:limit]


def _forecast_summary(period: str, slug: str) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for row in _raw_rows(period, slug, "Raw_Current_Model_Data"):
        close_date = _parse_date(row.get("CloseDate"))
        deal_type = str(row.get("Type") or "")
        if deal_type not in {"Land", "Expand"}:
            continue
        if not close_date or not (dt.date(2026, 4, 1) <= close_date <= dt.date(2026, 6, 30)):
            continue
        category = str(row.get("ForecastCategoryName") or "Uncategorized")
        bucket = summary.setdefault(category, {"count": 0.0, "arr_eur": 0.0})
        bucket["count"] += 1
        bucket["arr_eur"] += float(row.get("ARR_EUR") or 0)
    return summary


def _opportunity_url(deal: Deal) -> str | None:
    return f"{SF_BASE}/Opportunity/{deal.id}/view" if deal.id else None


def _remove_all_shapes(slide: Any) -> None:
    for shape in list(slide.shapes):
        shape.element.getparent().remove(shape.element)


def _text(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    size: float,
    *,
    bold: bool = False,
    color: RGBColor = NAVY,
    align: PP_ALIGN | None = None,
) -> Any:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    para = frame.paragraphs[0]
    para.text = text
    if align is not None:
        para.alignment = align
    run = para.runs[0] if para.runs else para.add_run()
    run.font.name = BRAND_FONT_NAME
    run.font.size = Pt(_brand_font_size(size))
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _link_text(
    slide: Any, left: float, top: float, width: float, height: float, text: str, url: str
) -> Any:
    box = _text(slide, left, top, width, height, text, 5.8, bold=True, color=BLUE)
    run = box.text_frame.paragraphs[0].runs[0]
    run.hyperlink.address = url
    return box


def _line(
    slide: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: RGBColor = RULE,
    width: float = 0.75,
) -> Any:
    shape = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    shape.line.color.rgb = color
    shape.line.width = Pt(width)
    return shape


def _panel(slide: Any, left: float, top: float, width: float, height: float) -> Any:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = PANEL
    shape.line.color.rgb = RULE
    shape.line.width = Pt(0.6)
    return shape


def _soft_panel(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    fill: RGBColor = PANEL,
    line: RGBColor = RULE,
) -> Any:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(0.5)
    return shape


def _tile(
    slide: Any,
    left: float,
    top: float,
    width: float,
    title: str,
    value: str,
    note: str,
    accent: RGBColor,
    *,
    value_size: float = 16.0,
) -> None:
    _panel(slide, left, top, width, 0.98)
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.035)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent
    bar.line.fill.background()
    _text(slide, left + 0.16, top + 0.15, width - 0.32, 0.18, title, 6.9, bold=True, color=MUTED)
    _text(
        slide, left + 0.16, top + 0.39, width - 0.32, 0.32, value, value_size, bold=True, color=NAVY
    )
    _text(slide, left + 0.16, top + 0.75, width - 0.32, 0.16, note, 6.3, color=MUTED)


def _metric_tile(
    slide: Any,
    left: float,
    top: float,
    width: float,
    title: str,
    value: str,
    note: str,
    accent: RGBColor,
    *,
    fill: RGBColor = PANEL,
) -> None:
    _soft_panel(slide, left, top, width, 0.88, fill=fill)
    stripe = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(0.055), Inches(0.88)
    )
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = accent
    stripe.line.fill.background()
    _text(slide, left + 0.18, top + 0.12, width - 0.32, 0.16, title, 6.5, bold=True, color=MUTED)
    _text(slide, left + 0.18, top + 0.34, width - 0.32, 0.27, value, 15.0, bold=True, color=NAVY)
    _text(slide, left + 0.18, top + 0.67, width - 0.32, 0.14, note, 5.8, color=MUTED)


def _status_pill(slide: Any, left: float, top: float, text: str, color: RGBColor) -> None:
    width = max(0.54, min(1.25, 0.18 + len(text) * 0.055))
    pill = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.18)
    )
    pill.fill.solid()
    pill.fill.fore_color.rgb = color
    pill.fill.transparency = 15
    pill.line.fill.background()
    _text(
        slide,
        left + 0.07,
        top + 0.035,
        width - 0.14,
        0.10,
        text,
        5.6,
        bold=True,
        color=WHITE,
        align=PP_ALIGN.CENTER,
    )


def _value_bar(
    slide: Any,
    left: float,
    top: float,
    width: float,
    label: str,
    value: float,
    max_value: float,
    color: RGBColor,
    *,
    value_label: str | None = None,
) -> None:
    _text(slide, left, top, 1.45, 0.16, label, 6.3, bold=True, color=NAVY)
    track = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(left + 1.55),
        Inches(top + 0.035),
        Inches(width - 2.25),
        Inches(0.10),
    )
    track.fill.solid()
    track.fill.fore_color.rgb = RGBColor(0xE8, 0xEC, 0xF3)
    track.line.fill.background()
    filled = max(0.02, min(width - 2.25, (width - 2.25) * (value / max(max_value, 1.0))))
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left + 1.55), Inches(top + 0.035), Inches(filled), Inches(0.10)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    _text(
        slide,
        left + width - 0.56,
        top - 0.005,
        0.56,
        0.16,
        value_label or _meur(value),
        6.1,
        bold=True,
        color=NAVY,
        align=PP_ALIGN.RIGHT,
    )


def _set_cell(
    cell: Any,
    text: str,
    *,
    header: bool = False,
    fill: RGBColor | None = None,
    size: float = 6.2,
    bold: bool = False,
    url: str | None = None,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    cell.text = text
    if fill:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
    para = cell.text_frame.paragraphs[0]
    para.alignment = align
    para.space_after = Pt(0)
    run = para.runs[0] if para.runs else para.add_run()
    run.font.name = BRAND_FONT_NAME
    run.font.size = Pt(_brand_font_size(size))
    run.font.bold = header or bold
    run.font.color.rgb = WHITE if header else NAVY
    if url:
        run.hyperlink.address = url


def _source_strip(
    slide: Any, source: str, *, action_label: str | None = None, action_url: str | None = None
) -> None:
    _line(slide, 0.58, 6.17, 11.75, 6.17, RULE, 0.5)
    _text(slide, 0.58, 6.23, 7.6, 0.18, source, 5.6, color=MUTED)
    if action_label and action_url:
        _link_text(slide, 9.10, 6.23, 2.6, 0.18, action_label, action_url)


def _risk_color(risk: str) -> RGBColor:
    return {"high": RED, "watch": AMBER, "ok": TEAL}.get(risk, BLUE)


def _may_ask(deal: Deal) -> str:
    text = f"{deal.readiness} {deal.next_step}".casefold()
    if "commercial approval gap" in text:
        return "Submit/confirm approval gate."
    if deal.days_to_close <= 0:
        return "Reset overdue close date."
    if "no next step" in text:
        return "Attach dated next step."
    if "silent 90d" in text or "no activity" in text:
        return "Log activity + customer proof."
    if deal.push >= 3:
        return "Validate close date / push risk."
    return "Confirm close evidence."


def _draw_map(
    slide: Any, deals: list[Deal], left: float, top: float, width: float, height: float
) -> None:
    _soft_panel(slide, left, top, width, height, fill=WHITE)
    _text(
        slide,
        left + 0.18,
        top + 0.15,
        width - 0.36,
        0.20,
        "Q2 close inspection map",
        10.4,
        bold=True,
    )
    _text(
        slide,
        left + 0.18,
        top + 0.40,
        width - 0.36,
        0.21,
        "X = days to close; Y = unweighted ARR; color = readiness risk.",
        6.4,
        color=MUTED,
    )
    plot_l = left + 0.50
    plot_t = top + 0.88
    plot_w = width - 0.80
    plot_h = height - 1.35
    axis_bottom = plot_t + plot_h
    max_days = max([65] + [max(1, deal.days_to_close) for deal in deals])
    max_arr = max([1.0] + [deal.arr_meur for deal in deals])
    max_arr = max(1.0, min(5.0, max_arr * 1.12))

    window_w = plot_w * min(30, max_days) / max_days
    decision_window = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(plot_l), Inches(plot_t), Inches(window_w), Inches(plot_h)
    )
    decision_window.fill.solid()
    decision_window.fill.fore_color.rgb = PANEL_AMBER
    decision_window.fill.transparency = 35
    decision_window.line.fill.background()
    high_value_y = axis_bottom - plot_h * (min(max_arr, 1.0) / max_arr)
    _line(
        slide, plot_l, high_value_y, plot_l + plot_w, high_value_y, RGBColor(0xD5, 0xAF, 0x52), 0.55
    )
    _text(
        slide,
        plot_l + plot_w - 1.08,
        high_value_y - 0.15,
        1.0,
        0.12,
        "EUR 1M line",
        5.5,
        color=AMBER,
        align=PP_ALIGN.RIGHT,
    )

    _line(slide, plot_l, axis_bottom, plot_l + plot_w, axis_bottom, RGBColor(0xA8, 0xB0, 0xC0), 0.8)
    _line(slide, plot_l, plot_t, plot_l, axis_bottom, RGBColor(0xA8, 0xB0, 0xC0), 0.8)
    for tick in [0, 15, 30, 45, 60]:
        x = plot_l + plot_w * (tick / max_days)
        _line(slide, x, axis_bottom, x, axis_bottom + 0.04, RGBColor(0xA8, 0xB0, 0xC0), 0.5)
        _text(
            slide,
            x - 0.12,
            axis_bottom + 0.08,
            0.32,
            0.12,
            str(tick),
            5.8,
            color=MUTED,
            align=PP_ALIGN.CENTER,
        )
        if tick in {30, 60}:
            _line(slide, x, plot_t, x, axis_bottom, PALE_GRID, 0.45)
    for frac in [0.25, 0.50, 0.75, 1.00]:
        value = max_arr * frac
        y = axis_bottom - plot_h * frac
        _line(slide, plot_l - 0.04, y, plot_l, y, RGBColor(0xA8, 0xB0, 0xC0), 0.5)
        _text(
            slide,
            plot_l - 0.44,
            y - 0.06,
            0.34,
            0.12,
            f"{value:.1f}",
            5.8,
            color=MUTED,
            align=PP_ALIGN.RIGHT,
        )
        _line(slide, plot_l, y, plot_l + plot_w, y, PALE_GRID, 0.35)
    _text(
        slide,
        plot_l + plot_w * 0.34,
        axis_bottom + 0.31,
        1.6,
        0.14,
        "days to close",
        6.2,
        color=MUTED,
        align=PP_ALIGN.CENTER,
    )
    _text(slide, plot_l - 0.46, plot_t - 0.22, 0.6, 0.14, "ARR mEUR", 6.2, color=MUTED)
    used_labels: dict[str, int] = {}
    for deal in deals:
        x = plot_l + plot_w * (max(0, min(max_days, deal.days_to_close)) / max_days)
        y = axis_bottom - plot_h * (max(0.0, min(max_arr, deal.arr_meur)) / max_arr)
        diameter = 0.13 + min(0.18, max(0.02, deal.arr_meur * 0.045))
        bubble = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x - diameter / 2),
            Inches(y - diameter / 2),
            Inches(diameter),
            Inches(diameter),
        )
        bubble.fill.solid()
        bubble.fill.fore_color.rgb = _risk_color(deal.risk)
        bubble.line.color.rgb = WHITE
        bubble.line.width = Pt(0.8)
        label = _short_account(deal.account, deal.opportunity)
        repeat = used_labels.get(label, 0)
        used_labels[label] = repeat + 1
        _text(
            slide, x + 0.05, y - 0.16 + repeat * 0.12, 0.85, 0.13, label, 5.7, bold=True, color=NAVY
        )
    legend_y = top + height - 0.29
    for idx, (label, color) in enumerate([("High", RED), ("Watch", AMBER), ("OK", TEAL)]):
        lx = left + 0.20 + idx * 0.78
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(lx), Inches(legend_y), Inches(0.08), Inches(0.08)
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = color
        dot.line.fill.background()
        _text(slide, lx + 0.11, legend_y - 0.01, 0.45, 0.11, label, 5.9, color=MUTED)


def _draw_forecast_composition(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    buckets: dict[str, dict[str, float]],
) -> None:
    values = [
        ("Commit", float(buckets.get("Commit", {}).get("arr_eur") or 0), TEAL),
        ("Pipeline", float(buckets.get("Pipeline", {}).get("arr_eur") or 0), PURPLE),
        ("Best Case", float(buckets.get("Best Case", {}).get("arr_eur") or 0), RED),
    ]
    total = sum(value for _, value, _ in values)
    _soft_panel(slide, left, top, width, height, fill=WHITE)
    _text(
        slide, left + 0.16, top + 0.14, width - 0.32, 0.18, "Forecast composition", 9.2, bold=True
    )
    _text(
        slide,
        left + 0.16,
        top + 0.38,
        width - 0.32,
        0.16,
        "Current-quarter Land+Expand ARR only.",
        6.1,
        color=MUTED,
    )
    x = left + 0.18
    bar_y = top + 0.74
    bar_w = width - 0.36
    if total <= 0:
        track = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(bar_y), Inches(bar_w), Inches(0.22)
        )
        track.fill.solid()
        track.fill.fore_color.rgb = RGBColor(0xE8, 0xEC, 0xF3)
        track.line.fill.background()
        _text(
            slide,
            x + 0.10,
            bar_y + 0.055,
            bar_w - 0.20,
            0.08,
            "No current-quarter forecast ARR",
            5.5,
            color=MUTED,
            align=PP_ALIGN.CENTER,
        )
    else:
        for label, value, color in values:
            if value <= 0:
                continue
            seg_w = max(0.10, bar_w * value / total)
            segment = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(x), Inches(bar_y), Inches(seg_w), Inches(0.22)
            )
            segment.fill.solid()
            segment.fill.fore_color.rgb = color
            segment.line.fill.background()
            x += seg_w
    for idx, (label, value, color) in enumerate(values):
        lx = left + 0.18 + idx * 1.55
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(lx), Inches(top + 1.13), Inches(0.08), Inches(0.08)
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = color
        dot.line.fill.background()
        _text(slide, lx + 0.11, top + 1.10, 0.78, 0.12, label, 5.8, color=MUTED)
        _text(
            slide,
            lx + 0.92,
            top + 1.10,
            0.48,
            0.12,
            _meur(value),
            5.8,
            bold=True,
            color=NAVY,
            align=PP_ALIGN.RIGHT,
        )


def _draw_renewal_timeline(
    slide: Any, renewals: list[dict[str, Any]], left: float, top: float, width: float, height: float
) -> None:
    dated = [(row, _parse_date(row.get("close_date"))) for row in renewals]
    dated = [(row, date) for row, date in dated if date is not None]
    if len({date for _, date in dated}) < 2:
        _soft_panel(slide, left, top, width, height, fill=WHITE)
        _text(
            slide,
            left + 0.16,
            top + 0.16,
            width - 0.32,
            0.18,
            "Renewal timing proof",
            9.2,
            bold=True,
        )
        _text(
            slide,
            left + 0.16,
            top + 0.43,
            width - 0.32,
            0.18,
            "Timeline suppressed: renewal dates are missing or not distinct enough for a timing chart.",
            6.2,
            color=MUTED,
        )
        return
    min_date = min(date for _, date in dated)
    max_date = max(date for _, date in dated)
    span = max(1, (max_date - min_date).days)
    max_acv = max([1.0] + [float(row.get("acv_eur") or 0) for row, _ in dated])
    _soft_panel(slide, left, top, width, height, fill=WHITE)
    _text(
        slide, left + 0.16, top + 0.12, width - 0.32, 0.18, "Renewal timing proof", 9.2, bold=True
    )
    _text(
        slide,
        left + 0.16,
        top + 0.34,
        width - 0.32,
        0.16,
        "Dots scale by ACV; Renewal ACV stays separate from ARR.",
        5.9,
        color=MUTED,
    )
    axis_l = left + 0.54
    axis_r = left + width - 0.52
    axis_y = top + 0.86
    _line(slide, axis_l, axis_y, axis_r, axis_y, RGBColor(0xA8, 0xB0, 0xC0), 0.85)
    for date in [min_date, max_date]:
        x = axis_l + (axis_r - axis_l) * ((date - min_date).days / span)
        _line(slide, x, axis_y - 0.05, x, axis_y + 0.05, RGBColor(0xA8, 0xB0, 0xC0), 0.55)
        _text(
            slide,
            x - 0.35,
            axis_y + 0.16,
            0.70,
            0.12,
            f"{date:%b} {date.day}",
            5.6,
            color=MUTED,
            align=PP_ALIGN.CENTER,
        )
    for row, date in dated[:6]:
        x = axis_l + (axis_r - axis_l) * ((date - min_date).days / span)
        acv = float(row.get("acv_eur") or 0)
        diameter = 0.12 + min(0.22, acv / max_acv * 0.22)
        risk = str(row.get("risk_level") or "").casefold()
        color = RED if "high" in risk else AMBER if "medium" in risk else TEAL
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x - diameter / 2),
            Inches(axis_y - diameter / 2),
            Inches(diameter),
            Inches(diameter),
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = color
        dot.line.color.rgb = WHITE
        dot.line.width = Pt(0.8)
        label = _short_account(str(row.get("account") or ""), str(row.get("name") or ""))
        _text(
            slide,
            x - 0.52,
            axis_y - 0.50,
            1.04,
            0.12,
            label,
            5.4,
            bold=True,
            color=NAVY,
            align=PP_ALIGN.CENTER,
        )


def _action_item_metric(trends: dict[str, Any], rule_id: str, metric: str) -> float:
    for item in trends.get("action_items", []):
        if item.get("rule_id") != rule_id:
            continue
        for evidence in item.get("evidence", []) or []:
            text = str(evidence)
            if text.startswith(f"{metric}="):
                try:
                    return float(text.split("=", 1)[1])
                except ValueError:
                    return 0.0
    return 0.0


def _director_scope_label(slug: str) -> str:
    """Return the human-readable scope label for a director slug.

    Falls back to the slug if the director is not in the canonical roster.
    """
    from _directors import canonical_directors  # local import keeps top of file lean

    for director in canonical_directors():
        if str(director.get("name", "")).replace(" ", "-") == slug:
            return str(director.get("scope_label") or slug)
    return slug.replace("-", " ")


def _top_alert_deal(trends: dict[str, Any], deals: list[Deal]) -> tuple[str, float]:
    """Pick the highest-ARR deal at risk for cover-slide prominence.

    Prefers `pending_commercial_approval_named` (Stage 3+ ≥EUR 500k missing
    Commercial Approval — the cardinal SimCorp gate). Falls back to the
    largest 'high' or 'watch' deal from the selected book.
    """
    pending = trends.get("pending_commercial_approval_named") or []
    if pending:
        sorted_pending = sorted(pending, key=lambda r: float(r.get("arr_eur") or 0), reverse=True)
        top = sorted_pending[0]
        account = str(top.get("account_name") or top.get("account") or "Unnamed deal")
        arr = float(top.get("arr_eur") or 0)
        return account, arr
    risky = sorted(
        [d for d in deals if d.risk in {"high", "watch"}],
        key=lambda d: d.arr_meur,
        reverse=True,
    )
    if risky:
        return _short_account(risky[0].account, risky[0].opportunity), risky[0].arr_meur * 1_000_000
    return "No flagged deals", 0.0


def _build_cover_slide(
    prs: Presentation,
    period: str,
    slug: str,
    trends: dict[str, Any],
    deals: list[Deal],
) -> None:
    """Render slide 1 as a director-specific operating-review cover.

    Replaces the generic `May 2026 LAND territory review · {region}` shell
    with: NAVY brand strip, dominant title block, and three headline KPIs
    (Open ARR Land+Expand · Renewal ACV · top alert deal). Stays
    `editorial_native` (0 tables, 0 pictures, 0 charts, 0 OLE) so the
    meeting-spine audit gate still classifies it correctly.

    KPI sourcing follows the cardinal SimCorp ARR/ACV rule: ARR is from
    Land+Expand pipeline only (`total_pipeline_arr` and
    `pipeline_arr_beyond_cfq`), Renewal ACV is from Renewal pipeline only
    (`total_renewal_acv`). Never blend.
    """
    slide = prs.slides[0]
    _remove_all_shapes(slide)

    director_name = slug.replace("-", " ")
    region = _director_scope_label(slug)

    closeable_arr = _kpi(trends, "total_pipeline_arr")
    open_beyond_cfq = _kpi(trends, "pipeline_arr_beyond_cfq")
    total_open_arr = closeable_arr + open_beyond_cfq
    renewal_acv = _kpi(trends, "total_renewal_acv")
    alert_account, alert_arr = _top_alert_deal(trends, deals)

    # NAVY brand strip across the top.
    strip = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.33), Inches(0.42)
    )
    strip.fill.solid()
    strip.fill.fore_color.rgb = NAVY
    strip.line.fill.background()
    _text(
        slide,
        0.58,
        0.10,
        8.0,
        0.20,
        "SimCorp · Sales Operating Review",
        7.0,
        bold=True,
        color=WHITE,
    )
    _text(slide, 9.40, 0.10, 3.40, 0.20, period, 7.0, color=WHITE, align=PP_ALIGN.RIGHT)

    # Title block — dominant, NAVY.
    _text(slide, 0.58, 1.08, 9.0, 0.20, "May 2026", 9.0, bold=True, color=MUTED)
    _text(slide, 0.58, 1.40, 11.0, 0.62, "LAND territory review", 24.0, bold=True, color=NAVY)
    _text(slide, 0.58, 2.10, 11.0, 0.30, f"{region} · {director_name}", 12.0, color=BLUE)

    # Hairline rule under the title.
    _line(slide, 0.58, 2.60, 12.75, 2.60, RULE, 0.8)

    # Section header for the headline KPIs.
    _text(
        slide,
        0.58,
        2.86,
        8.0,
        0.22,
        "Operating intelligence at a glance",
        10.0,
        bold=True,
        color=NAVY,
    )
    _text(
        slide,
        0.58,
        3.16,
        11.5,
        0.22,
        "Land+Expand ARR and Renewal ACV are reported separately. Multi-currency org totals are FX-converted to EUR by Salesforce.",
        6.0,
        color=MUTED,
    )

    # Three mega-tiles. NAVY/BLUE dominant; AMBER reserved for the alert.
    tile_top = 3.62
    tile_height = 1.74
    tile_width = 4.00

    _metric_tile(
        slide,
        0.58,
        tile_top,
        tile_width,
        "Total open Land+Expand ARR",
        _meur(total_open_arr),
        f"Closeable {_meur(closeable_arr)} · beyond CFQ {_meur(open_beyond_cfq)}.",
        BLUE,
        fill=PANEL_BLUE,
    )
    _metric_tile(
        slide,
        4.78,
        tile_top,
        tile_width,
        "Current-quarter Renewal ACV",
        _meur(renewal_acv),
        "Renewal ACV — separate from ARR. Never blended.",
        TEAL,
        fill=PANEL_TEAL,
    )
    _metric_tile(
        slide,
        8.98,
        tile_top,
        tile_width,
        "Top deal needing attention",
        _short(alert_account, 22),
        f"{_meur(alert_arr)} · Stage 3+ Commercial Approval lane."
        if alert_arr > 0
        else "No deals currently flagged.",
        AMBER,
        fill=PANEL_AMBER,
    )

    # Soft footer with kickoff + snapshot dates.
    _line(slide, 0.58, 6.05, 12.75, 6.05, RULE, 0.5)
    snapshot = trends.get("period_end") or trends.get("period") or period
    from period_context import context_for_period

    kickoff_long = context_for_period(period).kickoff_date_long
    _text(
        slide,
        0.58,
        6.16,
        7.8,
        0.18,
        f"Review kickoff: {kickoff_long} · Snapshot: {snapshot} · MD-1 territory book",
        5.6,
        color=MUTED,
    )
    _text(
        slide,
        9.10,
        6.16,
        3.65,
        0.18,
        "Source: Salesforce — Sales Director Monthly cadence",
        5.6,
        color=MUTED,
        align=PP_ALIGN.RIGHT,
    )


def _build_exec_summary_slide(
    prs: Presentation, period: str, slug: str, trends: dict[str, Any], original: dict[str, Any]
) -> None:
    slide = prs.slides[1]
    _remove_all_shapes(slide)
    deals = _deals(trends)
    selected = _selected_deals(deals)
    forecast = _forecast_summary(period, slug)
    commit_arr = float(forecast.get("Commit", {}).get("arr_eur") or 0)
    pipeline_arr = float(forecast.get("Pipeline", {}).get("arr_eur") or 0)
    approval_arr = _action_item_metric(trends, "approval_gap", "arr_eur")
    stale_arr = _action_item_metric(trends, "zombie_arr", "arr_eur")
    renewal_acv = _kpi(trends, "total_renewal_acv")
    high_watch = sum(1 for deal in selected if deal.risk in {"high", "watch"})

    _text(slide, 0.58, 0.38, 8.8, 0.42, "May operating summary", 24, bold=True)
    _text(
        slide,
        0.58,
        0.95,
        10.9,
        0.23,
        "Sales Director operating review. Focus the meeting on close evidence, governance gaps, and renewal ACV basis.",
        8.3,
        color=MUTED,
    )
    _line(slide, 0.58, 1.26, 11.75, 1.26, RULE, 0.8)

    _metric_tile(
        slide,
        0.58,
        1.47,
        2.58,
        "Q2 closeable L+E ARR",
        _meur(_kpi(trends, "total_pipeline_arr")),
        "Unweighted ARR.",
        BLUE,
        fill=PANEL_BLUE,
    )
    _metric_tile(
        slide,
        3.34,
        1.47,
        2.58,
        "Commit proof",
        _meur(commit_arr),
        "Needs dated evidence.",
        TEAL,
        fill=PANEL_TEAL,
    )
    _metric_tile(
        slide, 6.10, 1.47, 2.58, "Pipeline upside", _meur(pipeline_arr), "Conversion risk.", PURPLE
    )
    _metric_tile(
        slide,
        8.86,
        1.47,
        2.58,
        "Renewal ACV",
        _meur(renewal_acv),
        "ACV separate.",
        AMBER,
        fill=PANEL_AMBER,
    )

    _soft_panel(slide, 0.58, 2.70, 5.32, 2.52, fill=WHITE)
    _text(slide, 0.78, 2.90, 4.90, 0.20, "Where leadership attention goes", 10.4, bold=True)
    _text(
        slide,
        0.78,
        3.18,
        4.72,
        0.26,
        "This deck is an operating review, so the best visuals are proof objects tied to decisions, not decorative chart variety.",
        6.7,
        color=MUTED,
    )
    max_bar = max(approval_arr, stale_arr, _kpi(trends, "total_pipeline_arr"), 1.0)
    _value_bar(
        slide, 0.78, 3.70, 4.72, "Closeable ARR", _kpi(trends, "total_pipeline_arr"), max_bar, BLUE
    )
    _value_bar(slide, 0.78, 4.08, 4.72, "Approval exposure", approval_arr, max_bar, RED)
    _value_bar(slide, 0.78, 4.46, 4.72, "Stale ARR", stale_arr, max_bar, AMBER)
    _text(
        slide,
        0.78,
        4.86,
        4.76,
        0.16,
        f"{high_watch} named Q2 deals need high/watch treatment before forecast sign-off.",
        6.4,
        bold=True,
        color=NAVY,
    )

    _soft_panel(slide, 6.25, 2.70, 5.38, 2.52, fill=PANEL_BLUE)
    _text(slide, 6.45, 2.90, 4.96, 0.20, "Monthly decision path", 10.4, bold=True)
    steps = [
        ("1", "Close evidence", "Commit rows must show customer proof and dated next step.", BLUE),
        ("2", "Governance", "Commercial approval gaps are blockers, not commentary.", RED),
        ("3", "Renewal basis", "Renewal ACV stays separate from Land+Expand ARR.", AMBER),
        ("4", "Actions", "Every output has owner, due date, and Salesforce link.", TEAL),
    ]
    for idx, (num, title, body, color) in enumerate(steps):
        y = 3.28 + idx * 0.42
        marker = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(6.45), Inches(y), Inches(0.22), Inches(0.22)
        )
        marker.fill.solid()
        marker.fill.fore_color.rgb = color
        marker.line.fill.background()
        _text(
            slide,
            6.505,
            y + 0.035,
            0.11,
            0.08,
            num,
            5.4,
            bold=True,
            color=WHITE,
            align=PP_ALIGN.CENTER,
        )
        _text(slide, 6.78, y - 0.01, 1.25, 0.14, title, 6.8, bold=True)
        _text(slide, 8.06, y - 0.01, 3.27, 0.14, body, 6.2, color=MUTED)

    _source_strip(
        slide,
        "Source: trends.json::kpis/action_items/q2_deal_readiness + connected_factory.xlsx. "
        "Land+Expand ARR is unweighted unless explicitly labeled weighted; Renewal values = ACV.",
    )


def _build_q1_slide(prs: Presentation, trends: dict[str, Any], original: dict[str, Any]) -> None:
    slide = prs.slides[2]
    _remove_all_shapes(slide)
    is_apac = str(original.get("territory") or "") == "APAC"
    q1_opened = float(
        original.get("q1_promised_opened_arr_eur") or original.get("open_land_arr_eur_sidecar") or 0
    )
    q1_won = int(float(original.get("q1_land_wins") or 0))
    q1_won_arr = float(original.get("q1_land_wins_arr_eur") or 0)
    q1_lost = int(float(original.get("q1_land_lost") or 0))
    q1_lost_arr = float(original.get("q1_land_lost_arr_eur") or 0)
    q1_slips = int(float(original.get("q1_slipped_deals") or 0))
    q1_slip_arr = float(original.get("q1_slipped_arr_eur") or 0)
    _text(slide, 0.58, 0.42, 9.2, 0.48, "Q1 accountability and May reset", 24, bold=True)
    _text(
        slide,
        0.58,
        1.02,
        10.9,
        0.24,
        "Separate historical Land accountability from the current May Q2 ARR call.",
        8.4,
        color=MUTED,
    )
    _line(slide, 0.58, 1.36, 11.75, 1.36, RULE, 0.8)
    _tile(
        slide,
        0.58,
        1.62,
        2.55,
        "Q1 opened baseline",
        _meur(q1_opened),
        "Original/current baseline.",
        BLUE,
    )
    _tile(
        slide,
        3.40,
        1.62,
        2.55,
        "Q1 Land won",
        f"{q1_won} / {_meur(q1_won_arr)}",
        "Land ARR only.",
        TEAL,
        value_size=14.0,
    )
    _tile(
        slide,
        6.22,
        1.62,
        2.55,
        "Q1 lost",
        f"{q1_lost} / {_meur(q1_lost_arr)}",
        "Loss accountability.",
        RED,
        value_size=14.0,
    )
    _tile(
        slide,
        9.04,
        1.62,
        2.55,
        "Q1 slips",
        f"{q1_slips} / {_meur(q1_slip_arr)}",
        "Use as coaching lens.",
        AMBER,
        value_size=14.0,
    )
    if is_apac:
        rows = [
            (
                "Current Q2 closeable",
                _meur(_kpi(trends, "total_pipeline_arr")),
                "Land+Expand unweighted ARR; Renewal ACV excluded.",
            ),
            (
                "QTD L+E result",
                "Won/Lost shown later",
                "Keep Land+Expand result separate from Renewal ACV.",
            ),
            (
                "Since-last-review delta",
                "open Land 6 -> 12; approved-2026 deals moved 1 -> 2",
                "Use original APAC pack as the accountability baseline.",
            ),
            (
                "Original Q2 baseline",
                "6 deals / EUR 5.0M; zero recent activity",
                "Every Q2 deal needs dated next step and owner evidence.",
            ),
        ]
    else:
        rows = [
            (
                "Current Q2 closeable",
                _meur(_kpi(trends, "total_pipeline_arr")),
                "Land+Expand unweighted ARR; Renewal ACV excluded.",
            ),
            (
                "QTD L+E result",
                "Won/Lost shown later",
                "Keep Land+Expand result separate from Renewal ACV.",
            ),
            (
                "Original/current Q2 baseline",
                f"{int(float(original.get('q2_original_deals') or 0))} deals / {_meur(float(original.get('q2_original_arr_eur') or 0))}",
                "Use as directional context when available.",
            ),
            (
                "May review use",
                "Confirm, reset, or remove",
                "Every Q2 deal needs dated next step and owner evidence.",
            ),
        ]
    _simple_table(
        slide,
        rows,
        ["Lens", "Current fact", "May implication"],
        0.58,
        3.05,
        11.2,
        2.22,
        [2.15, 2.60, 6.45],
    )
    _source_strip(
        slide,
        "Source: connected_factory.xlsx::Raw_Original_Intel + trends.json. ARR = Land+Expand; Renewal ACV separate.",
    )


def _simple_table(
    slide: Any,
    rows: list[tuple[str, ...]],
    headers: list[str],
    left: float,
    top: float,
    width: float,
    height: float,
    col_widths: list[float],
    *,
    header_color: RGBColor = BLUE,
    font_size: float = 6.6,
) -> Any:
    table_shape = slide.shapes.add_table(
        len(rows) + 1, len(headers), Inches(left), Inches(top), Inches(width), Inches(height)
    )
    table = table_shape.table
    for idx, col_width in enumerate(col_widths):
        table.columns[idx].width = Inches(col_width)
    for idx, header in enumerate(headers):
        _set_cell(table.cell(0, idx), header, header=True, fill=header_color, size=7.0)
    for row_idx, row in enumerate(rows, 1):
        for col_idx, value in enumerate(row):
            _set_cell(
                table.cell(row_idx, col_idx),
                str(value),
                fill=RGBColor(0xF4, 0xF6, 0xFA) if row_idx % 2 == 0 else WHITE,
                size=font_size,
                bold=col_idx == 0,
            )
    return table_shape


def _build_forecast_slide(
    prs: Presentation,
    period: str,
    slug: str,
    trends: dict[str, Any],
    deals: list[Deal],
    selected: list[Deal],
    original: dict[str, Any],
) -> None:
    slide = prs.slides[3]
    _remove_all_shapes(slide)
    active = [deal for deal in deals if deal.forecast != "Omitted"]
    commit = [deal for deal in active if deal.forecast == "Commit"]
    pipeline = [deal for deal in active if deal.forecast == "Pipeline"]
    forecast = _forecast_summary(period, slug)
    commit_bucket = forecast.get(
        "Commit", {"count": float(len(commit)), "arr_eur": sum(d.arr_eur for d in commit)}
    )
    pipeline_bucket = forecast.get(
        "Pipeline", {"count": float(len(pipeline)), "arr_eur": sum(d.arr_eur for d in pipeline)}
    )
    best_case_bucket = forecast.get("Best Case", {"count": 0.0, "arr_eur": 0.0})
    _text(slide, 0.58, 0.42, 8.2, 0.48, "May forecast quality", 24, bold=True)
    _text(
        slide,
        0.58,
        1.02,
        10.9,
        0.24,
        "Snapshot as of 2026-04-30. Omitted and out-of-quarter pipeline are context, not coverage.",
        8.4,
        color=MUTED,
    )
    _line(slide, 0.58, 1.36, 11.75, 1.36, RULE, 0.8)
    _tile(
        slide,
        0.58,
        1.58,
        2.62,
        "Closeable L+E ARR",
        _meur(_kpi(trends, "total_pipeline_arr")),
        "Unweighted current-quarter ARR.",
        BLUE,
    )
    _tile(
        slide,
        3.48,
        1.58,
        2.62,
        "Commit ARR",
        _meur(commit_bucket["arr_eur"]),
        f"{int(commit_bucket['count'])} opps; {sum(1 for d in selected if d.forecast == 'Commit')} material named.",
        TEAL,
    )
    _tile(
        slide,
        6.38,
        1.58,
        2.62,
        "Pipeline ARR",
        _meur(pipeline_bucket["arr_eur"]),
        f"{int(pipeline_bucket['count'])} opps; {sum(1 for d in selected if d.forecast == 'Pipeline')} material named.",
        PURPLE,
    )
    _tile(
        slide,
        9.28,
        1.58,
        2.62,
        "Best Case ARR",
        _meur(best_case_bucket["arr_eur"]),
        "No material cushion."
        if best_case_bucket["arr_eur"] < 100_000
        else f"{int(best_case_bucket['count'])} opps.",
        RED,
    )
    _draw_forecast_composition(slide, 7.48, 2.72, 4.42, 1.52, forecast)
    original_forecast_fact = (
        "EUR 5.6M; 12 open Pipeline Inspection deals; Commit = EUR 2.7M; 48%"
        if str(original.get("territory") or "") == "APAC"
        else f"{int(float(original.get('forecast_mix_deals') or len(active)))} PI deals / {_meur(float(original.get('forecast_mix_weighted_arr_eur') or 0))}"
    )
    rows = [
        (
            "Commit proof",
            _short(
                ", ".join(_short_account(d.account, d.opportunity) for d in commit[:5])
                or "No material Commit rows",
                58,
            ),
            "Attach dated next step / decision evidence.",
        ),
        (
            "Pipeline upside",
            _short(
                ", ".join(_short_account(d.account, d.opportunity) for d in pipeline[:5])
                or "No material Pipeline rows",
                58,
            ),
            "Confirm conversion evidence or reset forecast category.",
        ),
        ("Original forecast spine", original_forecast_fact, "Keep weighted/unweighted labeled."),
        (
            "Risk to call",
            "No Best Case cushion"
            if best_case_bucket["arr_eur"] < 100_000
            else "Best Case exists but needs proof",
            "Use deal inspection, not forecast optimism.",
        ),
    ]
    _simple_table(
        slide,
        rows,
        ["Issue", "Named evidence", "May action"],
        0.58,
        3.06,
        6.62,
        2.18,
        [1.55, 2.42, 2.65],
        font_size=6.15,
    )
    _source_strip(
        slide,
        "Source: trends.json::kpis + q2_deal_readiness; original PI context from Raw_Original_Intel.",
        action_label="Open no-activity CFQ report",
        action_url=REPORT_LINKS["activity_drought"],
    )


def _build_q2_slide(prs: Presentation, deals: list[Deal], selected: list[Deal]) -> None:
    slide = prs.slides[4]
    _remove_all_shapes(slide)
    _text(slide, 0.58, 0.34, 8.8, 0.44, "Q2 forward look: May deal inspection", 24, bold=True)
    _text(
        slide,
        0.58,
        0.94,
        10.9,
        0.25,
        "Salesforce snapshot as of 2026-04-30. Land+Expand unweighted ARR only; Renewal ACV remains separate.",
        8.4,
        color=MUTED,
    )
    _line(slide, 0.58, 1.30, 11.75, 1.30, RULE, 0.8)
    commit_names = (
        ", ".join(
            _short_account(d.account, d.opportunity) for d in selected if d.forecast == "Commit"
        )
        or "named Commit rows"
    )
    pipe_names = (
        ", ".join(
            _short_account(d.account, d.opportunity) for d in selected if d.forecast == "Pipeline"
        )
        or "named Pipeline rows"
    )
    _text(slide, 0.58, 1.49, 3.0, 0.22, "Operating read", 10.2, bold=True)
    _text(
        slide,
        0.58,
        1.78,
        4.45,
        0.86,
        f"Q2 close call is not a summary-chart problem: Commit proof depends on {_short(commit_names, 70)}; Pipeline upside depends on {_short(pipe_names, 56)}.",
        9.0,
        color=NAVY,
    )
    _text(
        slide,
        0.58,
        2.73,
        4.45,
        0.72,
        "Current May review should force dated next steps, activity proof, approval status, and close-date realism for each named row.",
        8.1,
        color=MUTED,
    )
    _draw_map(slide, selected, 5.03, 1.43, 6.45, 3.16)
    _text(slide, 0.58, 3.84, 4.2, 0.22, "Named deal actions", 10.2, bold=True)
    _deal_table(slide, selected, 0.58, 4.14, 10.75, 1.54)
    _text(
        slide,
        0.58,
        5.74,
        10.6,
        0.30,
        "Click deal names for Salesforce records. Guardrails: overdue-close rows require reset; "
        "LTH August decision risk remains explicit.",
        6.0,
        color=MUTED,
    )
    _source_strip(
        slide,
        "Source: trends.json::q2_deal_readiness + connected_factory.xlsx::Raw_Current_Q2_Readiness.",
        action_label="Open no-activity CFQ report",
        action_url=REPORT_LINKS["activity_drought"],
    )


def _deal_table(
    slide: Any, deals: list[Deal], left: float, top: float, width: float, height: float
) -> None:
    rows = len(deals) + 1
    cols = 6
    table_shape = slide.shapes.add_table(
        rows, cols, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    table = table_shape.table
    for idx, col_width in enumerate([1.22, 1.07, 0.72, 0.70, 0.76, 2.22]):
        table.columns[idx].width = Inches(col_width)
    for col, header in enumerate(["Deal", "Owner", "ARR", "Close", "Fcst", "May ask"]):
        _set_cell(table.cell(0, col), header, header=True, fill=PURPLE, size=6.5)
    for row_idx, deal in enumerate(deals, start=1):
        values = [
            _short_account(deal.account, deal.opportunity),
            (deal.owner.split() or [""])[0],
            f"{deal.arr_meur:.1f}",
            f"{deal.close_date:%b} {deal.close_date.day}",
            deal.forecast[:4],
            _may_ask(deal),
        ]
        for col_idx, value in enumerate(values):
            _set_cell(
                table.cell(row_idx, col_idx),
                value,
                fill=RGBColor(0xF2, 0xF4, 0xF8) if row_idx % 2 == 0 else WHITE,
                size=6.0 if col_idx == 5 else 6.3,
                bold=col_idx == 0,
                url=_opportunity_url(deal) if col_idx == 0 else None,
            )


def _build_renewal_slide(
    prs: Presentation, trends: dict[str, Any], original: dict[str, Any]
) -> None:
    slide = prs.slides[6]
    _remove_all_shapes(slide)
    renewals = trends.get("fy26_renewals", [])[:5]
    all_renewals = trends.get("fy26_renewals", [])
    current_total = sum(float(row.get("acv_eur") or 0) for row in all_renewals)
    q2_total = sum(
        float(row.get("acv_eur") or 0)
        for row in all_renewals
        if str(row.get("close_date") or "") <= "2026-06-30"
    )
    original_total = float(
        original.get("fy26_renewals_acv_eur_original") or original.get("q2_renewals_acv_eur") or 0
    )
    _text(slide, 0.58, 0.42, 8.2, 0.48, "FY26 renewal watchlist", 24, bold=True)
    _text(
        slide,
        0.58,
        1.02,
        10.9,
        0.24,
        "ACV only. Land+Expand ARR is intentionally excluded from this slide.",
        8.4,
        color=MUTED,
    )
    _line(slide, 0.58, 1.36, 11.75, 1.36, RULE, 0.8)
    _tile(
        slide,
        0.58,
        1.58,
        2.75,
        "Original/baseline ACV",
        _meur(original_total),
        "Prior pack/source context.",
        TEAL,
    )
    _tile(
        slide,
        3.60,
        1.58,
        2.75,
        "Current state workbook",
        _meur(current_total),
        f"{len(all_renewals)} FY26 renewals; open ACV.",
        BLUE,
    )
    _tile(
        slide,
        6.62,
        1.58,
        2.75,
        "Current Q2 ACV",
        _meur(q2_total),
        "Current-quarter renewal ACV.",
        AMBER,
    )
    _tile(
        slide,
        9.64,
        1.58,
        2.18,
        "Basis status",
        "Reconcile",
        "Do not blend baselines.",
        RED,
        value_size=14.0,
    )
    _draw_renewal_timeline(slide, all_renewals, 0.58, 2.82, 11.2, 1.30)
    table_shape = slide.shapes.add_table(
        len(renewals) + 1, 8, Inches(0.58), Inches(4.30), Inches(11.2), Inches(1.18)
    )
    table = table_shape.table
    for idx, width in enumerate([0.45, 1.02, 2.25, 2.36, 1.42, 1.20, 1.00, 1.50]):
        table.columns[idx].width = Inches(width)
    for idx, header in enumerate(
        ["#", "Close", "Account", "Opportunity", "Owner", "Stage", "ACV", "Risk"]
    ):
        _set_cell(table.cell(0, idx), header, header=True, fill=BLUE, size=6.7)
    for row_idx, row in enumerate(renewals, 1):
        values = [
            str(row_idx),
            str(row.get("close_date") or ""),
            _short(row.get("account"), 34),
            _short(row.get("name"), 36),
            _short(row.get("owner"), 20),
            str(row.get("stage") or ""),
            _meur(float(row.get("acv_eur") or 0)),
            str(row.get("risk_level") or ""),
        ]
        for col_idx, value in enumerate(values):
            _set_cell(
                table.cell(row_idx, col_idx),
                value,
                fill=RGBColor(0xF4, 0xF6, 0xFA) if row_idx % 2 == 0 else WHITE,
                size=5.65 if col_idx in {2, 3} else 5.9,
                bold=col_idx == 2,
            )
    _text(
        slide,
        0.58,
        5.64,
        10.8,
        0.20,
        "Monthly review use: keep ACV separate from ARR, name the current-quarter renewal owner, and hold external FY26 ACV quotes until basis differences are reconciled.",
        6.6,
        color=NAVY,
    )
    _source_strip(
        slide,
        "Source: trends.json::fy26_renewals + connected_factory.xlsx::Raw_Current_FY26_Renewals. Renewal values are ACV.",
    )


def _evidence_names(period: str, slug: str) -> dict[str, str]:
    rows = _raw_rows(period, slug, "Raw_Pipeline_Open")

    def arr(row: dict[str, Any]) -> float:
        return float(row.get("ARR Unweighted (EUR)") or 0)

    def q2(row: dict[str, Any]) -> bool:
        close_date = _parse_date(row.get("Close Date"))
        return bool(close_date and dt.date(2026, 4, 1) <= close_date <= dt.date(2026, 6, 30))

    def stale_activity(row: dict[str, Any], days: int) -> bool:
        last = _parse_date(row.get("Last Activity"))
        return not last or (SNAPSHOT_DATE - last).days > days

    def created_old(row: dict[str, Any], days: int) -> bool:
        created = _parse_date(row.get("Created"))
        return bool(created and (SNAPSHOT_DATE - created).days > days)

    def is_le(row: dict[str, Any]) -> bool:
        return str(row.get("Type") or "") in {"Land", "Expand"}

    activity = [r for r in rows if is_le(r) and q2(r) and stale_activity(r, 30)]
    approval = [
        r
        for r in rows
        if is_le(r)
        and _stage_num(r.get("Stage")) >= 3
        and arr(r) >= 500_000
        and str(r.get("Approved") or "") != "Yes"
    ]
    zombie = [r for r in rows if is_le(r) and created_old(r, 730) and stale_activity(r, 60)]
    samples: dict[str, str] = {}
    for key, selected in [
        ("activity_drought", activity),
        ("approval_gap", approval),
        ("zombie_arr", zombie),
    ]:
        selected.sort(key=arr, reverse=True)
        samples[key] = _short(
            ", ".join(
                _short_account(str(r.get("Account") or ""), str(r.get("Opportunity") or ""))
                for r in selected[:6]
            )
            or "Open Salesforce report",
            72,
        )
    return samples


def _build_action_slide(prs: Presentation, period: str, slug: str, trends: dict[str, Any]) -> None:
    slide = prs.slides[13]
    _remove_all_shapes(slide)
    action_items = {item.get("rule_id"): item for item in trends.get("action_items", [])}
    samples = _evidence_names(period, slug)
    coverage_item = action_items.get("coverage_gap", {})
    coverage_sample = ""
    for evidence in coverage_item.get("evidence", []) or []:
        if str(evidence).startswith("sample="):
            coverage_sample = str(evidence).replace("sample=", "").replace(",", "; ")
            break
    rows = [
        (
            "Q2 activity drought",
            samples.get("activity_drought", "Open report"),
            action_items.get("activity_drought", {}).get("claim", "Q2 activity refresh needed"),
            "Owners log next step/task before forecast review.",
            "CFQ no-activity report",
            REPORT_LINKS["activity_drought"],
        ),
        (
            "Commercial approval",
            samples.get("approval_gap", "Open report"),
            action_items.get("approval_gap", {}).get("claim", "Approval gap review needed"),
            "Submit/confirm Stage 3 approval gate.",
            "Pending approval report",
            REPORT_LINKS["approval_gap"],
        ),
        (
            "Zombie pipeline",
            samples.get("zombie_arr", "Open report"),
            action_items.get("zombie_arr", {}).get("claim", "Stale pipeline cleanup needed"),
            "Rep-by-rep close/disqualify review by EOM.",
            "Zombie report",
            REPORT_LINKS["zombie_arr"],
        ),
        (
            "Tier-1 coverage",
            _short(coverage_sample or "Open report", 72),
            coverage_item.get("claim", "Coverage-gap review needed"),
            "Assign opener ownership and coverage plan.",
            "Coverage gap report",
            REPORT_LINKS["coverage_gap"],
        ),
    ]
    _text(slide, 0.58, 0.42, 8.8, 0.48, "May action register", 24, bold=True)
    _text(
        slide,
        0.58,
        1.02,
        10.9,
        0.24,
        "Named operating queues with direct Salesforce action links.",
        8.4,
        color=MUTED,
    )
    _line(slide, 0.58, 1.36, 11.75, 1.36, RULE, 0.8)
    table_shape = slide.shapes.add_table(
        len(rows) + 1, 5, Inches(0.58), Inches(1.66), Inches(11.2), Inches(3.92)
    )
    table = table_shape.table
    for idx, width in enumerate([1.55, 3.15, 3.00, 2.35, 1.15]):
        table.columns[idx].width = Inches(width)
    table.rows[0].height = Inches(0.38)
    for row_idx in range(1, len(rows) + 1):
        table.rows[row_idx].height = Inches(0.78)
    for idx, header in enumerate(["Queue", "Named evidence", "Fact", "May output", "Action"]):
        _set_cell(table.cell(0, idx), header, header=True, fill=BLUE, size=6.9)
    for row_idx, row in enumerate(rows, 1):
        for col_idx, value in enumerate(row[:5]):
            _set_cell(
                table.cell(row_idx, col_idx),
                value,
                fill=RGBColor(0xF4, 0xF6, 0xFA) if row_idx % 2 == 0 else WHITE,
                size=6.0 if col_idx in {1, 2, 3} else 6.15,
                bold=col_idx == 0,
                url=row[5] if col_idx == 4 else None,
            )
    _source_strip(
        slide,
        "Source: trends.json::action_items + Raw_Pipeline_Open samples + verified Salesforce reports. Counts remain horizon-labeled.",
        action_label="Open action reports",
        action_url=REPORT_LINKS["activity_drought"],
    )


def enhance_meeting_spine_deck(period: str, slug: str, deck_path: Path) -> dict[str, Any]:
    trends = _load_trends(period, slug)
    original = _original_intel(period, slug)
    deals = _deals(trends)
    selected = _selected_deals(deals)
    prs = Presentation(deck_path)
    if len(prs.slides) < 14:
        raise ValueError(
            f"deck has {len(prs.slides)} slides; expected meeting spine with at least 14"
        )
    _build_cover_slide(prs, period, slug, trends, deals)
    _build_exec_summary_slide(prs, period, slug, trends, original)
    _build_q1_slide(prs, trends, original)
    _build_forecast_slide(prs, period, slug, trends, deals, selected, original)
    _build_q2_slide(prs, deals, selected)
    _build_renewal_slide(prs, trends, original)
    _build_action_slide(prs, period, slug, trends)
    _normalize_deck_text_style(prs)
    prs.save(deck_path)
    return {
        "schema": "meeting-spine-action-layer/v1",
        "presentation_profile": "gtm_operating_review",
        "polish_principle": "decision-proof visuals only; no decorative chart variety",
        "rebuilt_slides": [1, 2, 3, 4, 5, 7, 14],
        "selected_deals": [asdict(deal) for deal in selected],
        "report_links": REPORT_LINKS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--director-slug", required=True)
    args = parser.parse_args()
    result = enhance_meeting_spine_deck(args.period, args.director_slug, args.deck)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
