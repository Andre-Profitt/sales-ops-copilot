"""Shared page header/navigation chrome for generated RW Power BI pages."""

from __future__ import annotations

import json

from scripts.sales._pbir_helpers import build_shape_visual, build_textbox_visual

PAGE_ORDER = (
    "VP Ops Scorecard",
    "What Changed",
    "Forecast",
    "Stage Hygiene",
    "Renewals",
    "Product Retention",
    "Growth Mix",
    "RW KPI Explorer",
)
CHROME_VISUAL_COUNT = 7
OLD_CONTENT_START_Y = 84
CHROME_HEIGHT = 104
CONTENT_SHIFT_Y = CHROME_HEIGHT - OLD_CONTENT_START_Y

PAGE_TITLES = {
    "VP Ops Scorecard": "VP Ops Control Room",
}

PAGE_SUBTITLES = {
    "VP Ops Scorecard": "Exceptions first; ARR, renewal ACV, weighted rates, and counts stay explicit.",
    "What Changed": "Seven-day movement ledger for exception status, stage moves, new, won, and lost.",
    "Forecast": "Quarter outlook, open value, forecast discipline, and late-stage commit risk.",
    "Stage Hygiene": "Stage conversion, reversal, approval-gate pressure, and bottleneck detail.",
    "Renewals": "Renewal ACV pipeline and active-base ARR risk remain separate measure families.",
    "Product Retention": "Active-base ARR by product, region, segment, and account-product risk.",
    "Growth Mix": "Land and Expand ARR mix, partner contribution, acquired business, SaaS, and PS attach.",
    "RW KPI Explorer": "Governed slice-and-dice surface with visible ARR, ACV, rate, and count bases.",
}

ACTION_TRAILS = {
    "VP Ops Scorecard": "Action: exceptions -> What Changed",
    "What Changed": "Action: movement queue -> Forecast / Stage Hygiene",
    "Forecast": "Action: commit risk -> owner and account detail",
    "Stage Hygiene": "Action: bottleneck -> Stage 4 detail",
    "Renewals": "Action: risk -> Product Retention",
    "Product Retention": "Action: product risk -> account-product ledger",
    "Growth Mix": "Action: mix gap -> Explorer",
    "RW KPI Explorer": "Action: validate slice -> source page",
}

NAV_TRAIL = "  |  ".join(
    [
        "01 Scorecard",
        "02 Changed",
        "03 Forecast",
        "04 Stages",
        "05 Renewals",
        "06 Product",
        "07 Growth",
        "08 Explorer",
    ]
)


def _visual_type(vc: dict) -> str:
    return str(json.loads(vc.get("config") or "{}").get("singleVisual", {}).get("visualType") or "")


def _is_legacy_top_header(vc: dict) -> bool:
    """Identify composer-local page titles that shared chrome replaces."""
    if _visual_type(vc) != "textbox":
        return False
    return float(vc.get("y") or 0) <= 64 and float(vc.get("x") or 0) <= 700


def page_chrome_visuals(page: str) -> list[dict]:
    title = PAGE_TITLES.get(page, page)
    subtitle = PAGE_SUBTITLES.get(page, "")
    action = ACTION_TRAILS.get(page, "")
    page_number = PAGE_ORDER.index(page) + 1 if page in PAGE_ORDER else 0
    title_text = f"{page_number:02d} / {len(PAGE_ORDER):02d}  {title}" if page_number else title
    return [
        build_shape_visual(x=0, y=0, w=1280, h=CHROME_HEIGHT, fill="#FFFFFF", line="#FFFFFF", z=4),
        build_shape_visual(x=0, y=0, w=1, h=CHROME_HEIGHT, fill="#D8DEE8", line="#D8DEE8", z=5),
        build_textbox_visual(title_text, x=24, y=8, w=500, h=34, font_size_pt=17, color="#1A1D31"),
        build_textbox_visual(action, x=540, y=10, w=300, h=28, font_size_pt=8, color="#5C6670"),
        build_textbox_visual(subtitle, x=24, y=44, w=790, h=26, font_size_pt=8, color="#5C6670", bold=False),
        build_textbox_visual(NAV_TRAIL, x=24, y=74, w=790, h=22, font_size_pt=7, color="#5C6670", bold=False),
        build_shape_visual(x=24, y=102, w=1232, h=1, fill="#D8DEE8", line="#D8DEE8", z=6),
    ]


def _shift_content_below_chrome(vc: dict) -> dict:
    if _visual_type(vc) == "slicer" or float(vc.get("y") or 0) < OLD_CONTENT_START_Y:
        return vc
    shifted = dict(vc)
    shifted["y"] = float(shifted.get("y") or 0) + CONTENT_SHIFT_Y
    cfg = json.loads(shifted.get("config") or "{}")
    for layout in cfg.get("layouts") or []:
        position = layout.get("position") or {}
        if "y" in position:
            position["y"] = float(position.get("y") or 0) + CONTENT_SHIFT_Y
    shifted["config"] = json.dumps(cfg)
    return shifted


def apply_page_chrome(section: dict, *, page: str) -> None:
    section["visualContainers"] = page_chrome_visuals(page) + [
        _shift_content_below_chrome(vc)
        for vc in section.get("visualContainers", [])
        if not _is_legacy_top_header(vc)
    ]
