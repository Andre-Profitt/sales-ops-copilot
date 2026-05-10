"""Automated visual QA gate for RW Power BI report.json/PBIP lab output.

The gate is intentionally heuristic: it audits PBIR-Legacy visualContainers for
layout and styling patterns that are deterministic in JSON before a human opens
Power BI Desktop. It catches the repeat offenders from Desktop review: clipped
labels, undersized KPI cards, card walls, weak hierarchy, native/plain visual
debt, IBCS/Zebra styling drift, and ARR/ACV guardrail leaks.

Usage:
    python3 -m scripts.sales.rw_dashboard_visual_qa \
      --report-json ~/Downloads/rw-pbi-format-lab/.../report.json \
      --fail-on high
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS

DEFAULT_REPORT_JSON = (
    Path.home()
    / "Downloads"
    / "rw-pbi-format-lab"
    / "rpt_vp_ops_scorecard_zebra_lab_20260509_pbip"
    / "rpt_vp_ops_scorecard.Report"
    / "report.json"
)
DEFAULT_OUT_DIR = Path("output") / "rw_dashboard_harness"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_DASHBOARD_VISUAL_QA.md"
CANVAS_W = 1280.0
CANVAS_H = 720.0
GRID = 4.0
GRID_TOLERANCE = 2.0
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
CARD_TYPES = {"card"}
TABLE_TYPES = {"tableEx", "pivotTable"}
TEXT_TYPES = {"textbox"}
ZEBRA_TYPES = {"ZebraBITables98F88148E5424E949E69864664EE1860"}
NATIVE_VISUAL_TYPES = CARD_TYPES | TABLE_TYPES | TEXT_TYPES | {"basicShape", "clusteredBarChart", "slicer"}
ACCENT_COLORS = {"#2B5C8A", "#3B8A3E", "#C33A32", "#D98A00", "#083EA7", "#CC3333", "#DD8800", "#339933"}
RENEWAL_BASE_ARR_MEASURES = {
    "Existing ARR Run Rate",
    "Existing ARR Expiring In Period",
    "Business At Risk ARR",
    "Business At Risk Pct",
    "Active Asset Line Count",
}
NEUTRAL_COLORS = {"#D8DEE8", "#E3E7EE", "#EEF2F6", "#FFFFFF", "#F4F7FB"}
PASTEL_STATUS_FILLS = {"#FFEEEE", "#FFF8E6", "#EEF9EE"}
ACCENT_COLORS = {color.upper() for color in ACCENT_COLORS}
NEUTRAL_COLORS = {color.upper() for color in NEUTRAL_COLORS}
PASTEL_STATUS_FILLS = {color.upper() for color in PASTEL_STATUS_FILLS}


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("_")[:80] or "visual_qa"


def decode_config(vc: dict) -> dict:
    raw = vc.get("config", {})
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def single_visual(vc: dict) -> dict:
    return decode_config(vc).get("singleVisual", {})


def visual_type(vc: dict) -> str:
    return str(single_visual(vc).get("visualType", ""))


def visual_name(vc: dict) -> str:
    return str(decode_config(vc).get("name") or "")


def _literal_value(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    value = node.get("expr", {}).get("Literal", {}).get("Value")
    if value is None:
        return node
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("'") and text.endswith("'"):
            return text[1:-1]
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        text = re.sub(r"[DL]$", "", text)
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return value
    return value


def _find_property(obj: Any, property_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == property_name:
                found.append(_literal_value(value))
            found.extend(_find_property(value, property_name))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_property(item, property_name))
    return found


def _find_colors(obj: Any) -> set[str]:
    colors: set[str] = set()
    if isinstance(obj, dict):
        color_node = obj.get("color")
        if isinstance(color_node, dict):
            literal = _literal_value(color_node)
            if isinstance(literal, str) and literal.startswith("#"):
                colors.add(literal.upper())
        for value in obj.values():
            colors.update(_find_colors(value))
    elif isinstance(obj, list):
        for item in obj:
            colors.update(_find_colors(item))
    return colors


def _font_size_from_textbox(vc: dict) -> float:
    sizes = _find_property(single_visual(vc), "fontSize")
    parsed: list[float] = []
    for size in sizes:
        text = str(size).replace("pt", "")
        try:
            parsed.append(float(text))
        except ValueError:
            continue
    return max(parsed) if parsed else 10.0


def _card_value_font_size(vc: dict) -> float:
    labels = (single_visual(vc).get("objects") or {}).get("labels", [])
    sizes = _find_property(labels, "fontSize")
    for size in sizes:
        try:
            return float(str(size).replace("pt", ""))
        except ValueError:
            continue
    return 22.0


def _card_label_font_size(vc: dict) -> float:
    labels = (single_visual(vc).get("objects") or {}).get("categoryLabels", [])
    sizes = _find_property(labels, "fontSize")
    for size in sizes:
        try:
            return float(str(size).replace("pt", ""))
        except ValueError:
            continue
    return 10.0


def display_titles(vc: dict) -> list[str]:
    props = single_visual(vc).get("columnProperties", {})
    titles = [
        str(value.get("displayName"))
        for value in props.values()
        if isinstance(value, dict) and value.get("displayName")
    ]
    title_texts = _find_property(single_visual(vc).get("vcObjects", {}).get("title", []), "text")
    titles.extend(str(text) for text in title_texts if text)
    return titles


def textbox_text(vc: dict) -> str:
    paragraphs = _find_property(single_visual(vc), "paragraphs")
    if not paragraphs:
        return ""
    chunks: list[str] = []
    for paragraphs_value in paragraphs:
        if not isinstance(paragraphs_value, list):
            continue
        for para in paragraphs_value:
            for run in para.get("textRuns", []):
                chunks.append(str(run.get("value") or ""))
    return "".join(chunks)


def field_measure_names(vc: dict) -> list[str]:
    names: list[str] = []
    for selected in single_visual(vc).get("prototypeQuery", {}).get("Select", []):
        if "Measure" in selected:
            names.append(str(selected["Measure"].get("Property") or ""))
    return [name for name in names if name]


def visual_label(vc: dict) -> str:
    title = " | ".join(display_titles(vc)) or textbox_text(vc)
    return title[:96]


def visual_ref(page: str, vc: dict) -> str:
    name = visual_name(vc) or "unnamed"
    return f"{page}/{name} ({visual_type(vc) or 'unknown'})"


def bbox(vc: dict) -> tuple[float, float, float, float]:
    return (
        float(vc.get("x") or 0),
        float(vc.get("y") or 0),
        float(vc.get("width") or 0),
        float(vc.get("height") or 0),
    )


def finding(
    *,
    code: str,
    severity: str,
    page: str,
    visual: dict | None,
    message: str,
    evidence: dict | None = None,
    recommendation: str = "",
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "page": page,
        "visual_name": visual_name(visual or {}) if visual else "",
        "visual_type": visual_type(visual or {}) if visual else "",
        "visual_label": visual_label(visual or {}) if visual else "",
        "x": (visual or {}).get("x"),
        "y": (visual or {}).get("y"),
        "width": (visual or {}).get("width"),
        "height": (visual or {}).get("height"),
        "message": message,
        "evidence": evidence or {},
        "recommendation": recommendation,
    }


def audit_text_clipping(page: str, vc: dict) -> list[dict]:
    vt = visual_type(vc)
    x, y, w, h = bbox(vc)
    issues: list[dict] = []
    if vt == "textbox":
        text = textbox_text(vc)
        font_size = _font_size_from_textbox(vc)
        lines = max(1, math.ceil((len(text) * font_size * 0.52) / max(w - 8, 1)))
        required_h = lines * font_size * 1.35 + 2
        if text and (required_h > h + 2 or len(text) * font_size * 0.52 > max(w - 8, 1) * lines):
            issues.append(
                finding(
                    code="likely_text_clipping",
                    severity="high" if y < 80 else "medium",
                    page=page,
                    visual=vc,
                    message="Textbox label likely clips or wraps beyond its bounding box.",
                    evidence={
                        "text_length": len(text),
                        "font_size_pt": font_size,
                        "estimated_lines": lines,
                        "required_height": round(required_h, 1),
                        "actual_height": h,
                    },
                    recommendation="Increase the textbox width/height or shorten the label.",
                )
            )
    elif vt == "card":
        title = " ".join(display_titles(vc))
        label_size = _card_label_font_size(vc)
        value_size = _card_value_font_size(vc)
        required_w = max(150.0, len(title) * label_size * 0.48 + 24)
        required_h = value_size * 1.45 + label_size * 1.6 + 20
        if title and (w + 4 < required_w or h + 4 < required_h):
            issues.append(
                finding(
                    code="card_too_small",
                    severity="high" if h < 64 or w < 150 else "medium",
                    page=page,
                    visual=vc,
                    message="KPI card is too small for its label/value treatment.",
                    evidence={
                        "title": title,
                        "label_font_size": label_size,
                        "value_font_size": value_size,
                        "required_width": round(required_w, 1),
                        "required_height": round(required_h, 1),
                        "actual_width": w,
                        "actual_height": h,
                    },
                    recommendation="Use 180x70 minimum for micro-cards and 260x90+ for executive cards.",
                )
            )
    return issues


def audit_styling(page: str, vc: dict) -> list[dict]:
    vt = visual_type(vc)
    sv = single_visual(vc)
    objects = sv.get("objects") or {}
    issues: list[dict] = []
    if vt == "card":
        required = {"background", "border", "labels", "categoryLabels"}
        missing = sorted(required - set(objects))
        if missing:
            issues.append(
                finding(
                    code="unstyled_card",
                    severity="high",
                    page=page,
                    visual=vc,
                    message="Native card is missing the RW/Zebra-style formatting objects block.",
                    evidence={"missing_object_keys": missing, "object_keys": sorted(objects)},
                    recommendation="Build KPI cards with build_rag_card_visual rather than plain build_card_visual.",
                )
            )
        colors = _find_colors(objects)
        if not colors.intersection(ACCENT_COLORS):
            issues.append(
                finding(
                    code="missing_rag_accent",
                    severity="medium",
                    page=page,
                    visual=vc,
                    message="KPI card lacks a recognized RAG/accent color treatment.",
                    evidence={"colors": sorted(colors)},
                    recommendation="Apply blue/green/amber/red accent and matching tint by KPI polarity.",
                )
            )
        pastel_backgrounds = _find_colors(objects.get("background", [])).intersection(PASTEL_STATUS_FILLS)
        if pastel_backgrounds:
            issues.append(
                finding(
                    code="pastel_status_card_surface",
                    severity="medium",
                    page=page,
                    visual=vc,
                    message="KPI card uses a pastel RAG tile background instead of a Zebra-style neutral surface.",
                    evidence={"background_colors": sorted(pastel_backgrounds)},
                    recommendation="Use white/near-white card surfaces with status color limited to a narrow accent or label.",
                )
            )
    elif vt in TABLE_TYPES:
        if not objects:
            issues.append(
                finding(
                    code="unstyled_table",
                    severity="high",
                    page=page,
                    visual=vc,
                    message="Native table/matrix has no renderer-authored or helper styling objects.",
                    evidence={},
                    recommendation="Apply build_table_style_objects or build_matrix_style_objects.",
                )
            )
        elif vt == "tableEx" and not {"columnHeaders", "values"}.intersection(objects):
            issues.append(
                finding(
                    code="weak_table_styling",
                    severity="medium",
                    page=page,
                    visual=vc,
                    message="Table has objects but does not expose expected header/value styling keys.",
                    evidence={"object_keys": sorted(objects)},
                    recommendation="Use the shared RW table style object builder.",
                )
            )
    elif vt == "basicShape":
        fill_colors = _find_colors(objects.get("fill", [])).intersection(PASTEL_STATUS_FILLS)
        area = float(vc.get("width") or 0) * float(vc.get("height") or 0)
        if fill_colors and area >= 2000:
            issues.append(
                finding(
                    code="pastel_status_panel_surface",
                    severity="medium",
                    page=page,
                    visual=vc,
                    message="Large panel uses a pastel RAG fill that reads as template/AI-generated.",
                    evidence={"fill_colors": sorted(fill_colors), "area": round(area, 1)},
                    recommendation="Use a neutral panel fill and reserve status color for a thin accent strip.",
                )
            )
    elif vt and vt not in NATIVE_VISUAL_TYPES and vt not in ZEBRA_TYPES:
        issues.append(
            finding(
                code="unknown_visual_type",
                severity="medium",
                page=page,
                visual=vc,
                message="Visual type is neither native RW-approved nor the tracked Zebra BI Tables proof visual.",
                evidence={"visual_type": vt},
                recommendation="Either document this visual in the QA allowlist or replace with a native/Zebra-approved visual.",
            )
        )
    return issues


def audit_grid(page: str, vc: dict) -> list[dict]:
    x, y, w, h = bbox(vc)
    issues: list[dict] = []
    right = x + w
    bottom = y + h
    if right > CANVAS_W + 0.5 or bottom > CANVAS_H + 0.5:
        issues.append(
            finding(
                code="canvas_overflow",
                severity="critical",
                page=page,
                visual=vc,
                message="Visual extends beyond the 1280x720 canvas.",
                evidence={"right": right, "bottom": bottom},
                recommendation="Move or resize the visual inside the canvas.",
            )
        )
    off_grid = {
        key: value
        for key, value in {"x": x, "y": y, "width": w, "height": h}.items()
        if abs(value - round(value / GRID) * GRID) > GRID_TOLERANCE
    }
    if off_grid:
        issues.append(
            finding(
                code="grid_misalignment",
                severity="low",
                page=page,
                visual=vc,
                message="Visual is outside the 4px grid alignment tolerance.",
                evidence={"off_grid": off_grid, "grid": GRID, "tolerance": GRID_TOLERANCE},
                recommendation="Snap x/y/width/height to the 4px layout grid.",
            )
        )
    return issues


def audit_page_hierarchy(page: str, visuals: list[dict]) -> list[dict]:
    textboxes = [vc for vc in visuals if visual_type(vc) == "textbox"]
    header_count = sum(1 for vc in textboxes if _font_size_from_textbox(vc) >= 13 and bbox(vc)[1] <= 120)
    text_section_headers = sum(1 for vc in textboxes if _font_size_from_textbox(vc) >= 11)
    object_title_headers = sum(
        1
        for vc in visuals
        if visual_type(vc) != "textbox"
        and visual_type(vc) != "card"
        and any(display_titles(vc))
    )
    section_header_count = text_section_headers + object_title_headers
    card_count = sum(1 for vc in visuals if visual_type(vc) == "card")
    table_chart_count = sum(1 for vc in visuals if visual_type(vc) in TABLE_TYPES | {"clusteredBarChart"} | ZEBRA_TYPES)
    issues: list[dict] = []
    weak_for_contract = header_count < 1 or (
        section_header_count < 2 and (card_count >= 1 or table_chart_count >= 2)
    )
    if page in PAGE_KPI_CONTRACTS and weak_for_contract:
        issues.append(
            finding(
                code="weak_section_hierarchy",
                severity="medium",
                page=page,
                visual=None,
                message="KPI contract page has weak visible hierarchy for headers/sections.",
                evidence={
                    "header_count": header_count,
                    "section_header_count": section_header_count,
                    "text_section_headers": text_section_headers,
                    "object_title_headers": object_title_headers,
                    "card_count": card_count,
                    "table_chart_count": table_chart_count,
                },
                recommendation="Add a strong page header and section labels, or promote panel titles into visible textboxes.",
            )
        )
    if card_count >= 8:
        card_area = sum(bbox(vc)[2] * bbox(vc)[3] for vc in visuals if visual_type(vc) == "card")
        if card_area > CANVAS_W * CANVAS_H * 0.22 or card_count >= 9:
            severity = "high" if card_count >= 12 or card_area > CANVAS_W * CANVAS_H * 0.30 else "medium"
            issues.append(
                finding(
                    code="wall_of_cards",
                    severity=severity,
                    page=page,
                    visual=None,
                    message="Page has an excessive KPI-card density and risks reading as a wall of cards.",
                    evidence={"card_count": card_count, "card_area_pct": round(card_area / (CANVAS_W * CANVAS_H), 3)},
                    recommendation="Reduce card count, group micro-KPIs, and replace lists of cards with a table/matrix or chart.",
                )
            )
    return issues


def audit_card_strips(page: str, visuals: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = defaultdict(list)
    for vc in visuals:
        if visual_type(vc) == "card":
            groups[round(float(vc.get("y") or 0) / 8)].append(vc)
    issues: list[dict] = []
    for cards in groups.values():
        if len(cards) < 3:
            continue
        widths = [bbox(vc)[2] for vc in cards]
        heights = [bbox(vc)[3] for vc in cards]
        if max(widths) - min(widths) > 16 or max(heights) - min(heights) > 8:
            issues.append(
                finding(
                    code="card_strip_dimension_drift",
                    severity="medium",
                    page=page,
                    visual=None,
                    message="Cards in the same KPI strip use inconsistent dimensions.",
                    evidence={
                        "y_band": sorted({bbox(vc)[1] for vc in cards}),
                        "widths": widths,
                        "heights": heights,
                    },
                    recommendation="Normalize KPI strip card width/height and align x positions to a shared grid.",
                )
            )
    return issues


def audit_arr_acv_guardrails(page: str, vc: dict) -> list[dict]:
    measures = field_measure_names(vc)
    if not measures:
        return []
    joined = " | ".join(measures + display_titles(vc))
    has_arr = bool(re.search(r"\bARR\b", joined, re.IGNORECASE))
    has_renewal_acv = bool(re.search(r"Renewal\s+ACV", joined, re.IGNORECASE))
    issues: list[dict] = []
    if page == "Renewals" and has_arr:
        illegal_arr = [
            measure
            for measure in measures
            if re.search(r"\bARR\b", measure, re.IGNORECASE)
            and measure not in RENEWAL_BASE_ARR_MEASURES
        ]
        if not illegal_arr and set(measures).intersection(RENEWAL_BASE_ARR_MEASURES):
            return issues
        issues.append(
            finding(
                code="arr_acv_guardrail",
                severity="critical",
                page=page,
                visual=vc,
                message="Renewals page references non-active-base ARR. Renewal ACV must remain Renewal-only.",
                evidence={"measures": measures, "illegal": illegal_arr},
                recommendation="Use only Renewal ACV measures or the explicitly allowed active-base ARR measures on Renewals.",
            )
        )
    if page in {"Growth Mix", "Stage Hygiene", "What Changed", "VP Ops Scorecard"} and has_renewal_acv:
        # VP Ops allows renewal retention percentage but not Renewal ACV value blending.
        issues.append(
            finding(
                code="arr_acv_guardrail",
                severity="critical",
                page=page,
                visual=vc,
                message="Land/Expand KPI page references Renewal ACV value.",
                evidence={"measures": measures},
                recommendation="Keep Renewal ACV on Renewals, or use only explicitly labeled cross-motion Total Open Pipeline Value.",
            )
        )
    if page == "Forecast":
        illegal_cross_motion = [
            m
            for m in measures
            if "Renewal ACV" in m or ("ARR" in m and m != "Total Closed Won ARR")
        ]
        if illegal_cross_motion and "Total Open Pipeline Value" not in measures:
            issues.append(
                finding(
                    code="arr_acv_guardrail",
                    severity="critical",
                    page=page,
                    visual=vc,
                    message="Forecast page has a cross-motion value that is not the explicitly labeled Total Open Pipeline Value.",
                    evidence={"measures": measures, "illegal": illegal_cross_motion},
                    recommendation="Use Total Open Pipeline Value for cross-motion open value; keep ARR/ACV otherwise separated.",
                )
            )
    return issues


def audit_report(report: dict) -> dict:
    findings: list[dict] = []
    pages = report.get("sections", [])
    for section in pages:
        page = section.get("displayName") or section.get("name") or "Untitled"
        visuals = section.get("visualContainers", [])
        if not visuals:
            findings.append(
                finding(
                    code="empty_page",
                    severity="high",
                    page=page,
                    visual=None,
                    message="Page has no visuals.",
                    recommendation="Compose or remove the page before Desktop review.",
                )
            )
            continue
        findings.extend(audit_page_hierarchy(page, visuals))
        findings.extend(audit_card_strips(page, visuals))
        for vc in visuals:
            findings.extend(audit_grid(page, vc))
            findings.extend(audit_text_clipping(page, vc))
            findings.extend(audit_styling(page, vc))
            findings.extend(audit_arr_acv_guardrails(page, vc))
    severity_counts = Counter(f["severity"] for f in findings)
    code_counts = Counter(f["code"] for f in findings)
    pages_with_findings = Counter(f["page"] for f in findings)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "summary": {
            "page_count": len(pages),
            "visual_count": sum(len(s.get("visualContainers", [])) for s in pages),
            "total_findings": len(findings),
            "severity_counts": {severity: severity_counts.get(severity, 0) for severity in SEVERITY_ORDER},
            "code_counts": dict(sorted(code_counts.items())),
            "pages_with_findings": dict(sorted(pages_with_findings.items())),
        },
        "findings": sorted(
            findings,
            key=lambda f: (
                -SEVERITY_ORDER.get(f["severity"], 0),
                f["page"],
                f["code"],
                f.get("y") if f.get("y") is not None else -1,
                f.get("x") if f.get("x") is not None else -1,
            ),
        ),
    }


def render_markdown(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# RW Dashboard Visual QA",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Pages audited: {summary['page_count']}",
        f"- Visuals audited: {summary['visual_count']}",
        f"- Findings: {summary['total_findings']}",
        "- Severity counts: "
        + ", ".join(f"{k}={v}" for k, v in summary["severity_counts"].items()),
        "",
        "## Finding mix",
        "",
    ]
    if summary["code_counts"]:
        for code, count in summary["code_counts"].items():
            lines.append(f"- `{code}`: {count}")
    else:
        lines.append("- No findings.")
    lines.extend(["", "## Findings", ""])
    if not result["findings"]:
        lines.append("No visual QA findings above the current heuristic thresholds.")
    for idx, item in enumerate(result["findings"], start=1):
        visual = item.get("visual_name") or "page"
        label = item.get("visual_label") or item.get("visual_type") or ""
        lines.extend(
            [
                f"### {idx}. [{item['severity']}] {item['code']} — {item['page']} / {visual}",
                "",
                item["message"],
                "",
                f"- Visual type: `{item.get('visual_type') or 'n/a'}`",
                f"- Label: `{label}`",
                f"- BBox: x={item.get('x')} y={item.get('y')} w={item.get('width')} h={item.get('height')}",
                f"- Evidence: `{json.dumps(item.get('evidence') or {}, ensure_ascii=False, sort_keys=True)}`",
                f"- Recommendation: {item.get('recommendation') or 'Review in Desktop.'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrails encoded",
            "",
            "- ARR = Land + Expand only.",
            "- Renewal ACV = Renewal only.",
            "- Do not blend ARR and Renewal ACV except the explicitly labeled `Total Open Pipeline Value`.",
            "- Native cards should carry RAG/accent formatting; tables/matrices should use shared RW/Zebra/IBCS object styles.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    result: dict,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    markdown_path: Path = DEFAULT_MARKDOWN,
    label: str | None = None,
) -> tuple[Path, Path]:
    label = slug(label or f"visual_qa_{timestamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{label}.visual_qa.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def load_report(path: Path) -> dict:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def exit_code_for(result: dict, fail_on: str) -> int:
    threshold = SEVERITY_ORDER[fail_on]
    return 1 if any(SEVERITY_ORDER[f["severity"]] >= threshold for f in result["findings"]) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--label", help="Output file label")
    parser.add_argument(
        "--fail-on",
        choices=tuple(SEVERITY_ORDER),
        default="critical",
        help="Exit non-zero when a finding at this severity or higher is present.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = audit_report(load_report(args.report_json))
    json_path, md_path = write_outputs(
        result,
        out_dir=args.out_dir,
        markdown_path=args.markdown,
        label=args.label,
    )
    print(f"visual qa json: {json_path}")
    print(f"visual qa markdown: {md_path}")
    counts = result["summary"]["severity_counts"]
    print(
        "findings="
        f"{result['summary']['total_findings']} "
        + " ".join(f"{severity}={counts[severity]}" for severity in SEVERITY_ORDER)
    )
    raise SystemExit(exit_code_for(result, args.fail_on))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
