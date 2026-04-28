#!/usr/bin/env python3
"""
sales-ops-copilot — Daily PowerPoint deck builder.

Renders today's brief data into a 7-slide board-pack PowerPoint using the
SimCorp PPT template as the master. Pulls fresh from Salesforce (same data
helpers as brief.py) and optionally generates a "recommended actions" block
via apro-openai.

Slide structure:
    1. Title slide
    2. Executive summary (4 bullets)
    3. Multi-quarter weighted forecast (table + bar chart)
    4. Top critical alerts (table)
    5. Account concentration (top 10)
    6. Owner concentration (top 10)
    7. Recommended actions for the week

Usage:
    python3 scripts/deck.py [--out PATH] [--no-llm] [--onedrive-publish]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shutil
import sys
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

# Make scripts/ importable for local helpers
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# --- Config -----------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

SIMCORP_TEMPLATE = pathlib.Path(
    "/Users/test/projects/brand-deck-agent-py/assets/SimCorp_PPT_Template.pptx"
)

# Layout indices verified against the SimCorp template (34 layouts total):
#   33 = '1_Title only'    -> has a real TITLE placeholder; used for title slide
#   24 = 'Blank'           -> used for content slides; we add textboxes
LAYOUT_TITLE = 33
LAYOUT_BLANK = 24

# SimCorp brand-ish neutral palette for table accents (kept subtle so we don't
# fight the template's master). Light grey row shading + dark text.
COLOR_HEADER_FILL = RGBColor(0x0B, 0x1F, 0x3A)  # deep navy
COLOR_HEADER_TEXT = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_ROW_ALT = RGBColor(0xF2, 0xF4, 0xF7)
COLOR_BODY_TEXT = RGBColor(0x1F, 0x2A, 0x44)

FOOTER_FONT_SIZE = Pt(9)
FOOTER_COLOR = RGBColor(0x6B, 0x72, 0x80)


# --- Helpers ----------------------------------------------------------------


def _fmt_money(v: float) -> str:
    return f"${v:,.0f}"


def _fmt_money_short(v: float) -> str:
    """Format dollars in M/K for compact tables."""
    if v >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:,.0f}K"
    return f"${v:,.0f}"


def _add_textbox(
    slide: Any,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    font_size: Pt,
    *,
    bold: bool = False,
    color: RGBColor = COLOR_BODY_TEXT,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> Any:
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Arial"
    return tb


def _add_title(slide: Any, title: str) -> None:
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(0.3),
        Inches(12.33),
        Inches(0.8),
        title,
        Pt(28),
        bold=True,
        color=RGBColor(0x0B, 0x1F, 0x3A),
    )


def _add_footer(slide: Any, page_num: int, total_pages: int, run_date: str) -> None:
    footer_text = (
        f"Sales Ops Brief — {run_date} · Internal · Advisory only · {page_num} / {total_pages}"
    )
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(7.0),
        Inches(12.33),
        Inches(0.3),
        footer_text,
        FOOTER_FONT_SIZE,
        color=FOOTER_COLOR,
        align=PP_ALIGN.LEFT,
    )


def _add_bullets(
    slide: Any,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    bullets: list[str],
    *,
    font_size: Pt = Pt(16),
) -> None:
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, bullet in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(8)
        run = p.add_run()
        run.text = f"•  {bullet}"
        run.font.size = font_size
        run.font.color.rgb = COLOR_BODY_TEXT
        run.font.name = "Arial"


def _add_table(
    slide: Any,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    headers: list[str],
    rows: list[list[str]],
    *,
    right_align_cols: set[int] | None = None,
) -> Any:
    """Native python-pptx table: bold header, alternating row shade,
    right-align selected columns."""
    right_align_cols = right_align_cols or set()
    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = tbl_shape.table

    # Header row
    for c, header in enumerate(headers):
        cell = tbl.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_HEADER_FILL
        tf = cell.text_frame
        tf.margin_left = Inches(0.05)
        tf.margin_right = Inches(0.05)
        tf.text = header
        para = tf.paragraphs[0]
        para.alignment = PP_ALIGN.RIGHT if c in right_align_cols else PP_ALIGN.LEFT
        for run in para.runs:
            run.font.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = COLOR_HEADER_TEXT
            run.font.name = "Arial"

    # Body rows
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = COLOR_ROW_ALT
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            tf = cell.text_frame
            tf.margin_left = Inches(0.05)
            tf.margin_right = Inches(0.05)
            tf.text = val
            para = tf.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if c in right_align_cols else PP_ALIGN.LEFT
            for run in para.runs:
                run.font.size = Pt(10)
                run.font.color.rgb = COLOR_BODY_TEXT
                run.font.name = "Arial"
    return tbl_shape


# --- LLM (recommended actions) ----------------------------------------------


def llm_recommended_actions(
    sf: dict,
    alerts: list,
    owners: list,
    accounts: list,
    *,
    model: str = "gpt53chat",
    weekly: bool = False,
) -> list[str]:
    """Generate 3-5 recommended actions via apro-openai. Falls back to deterministic
    bullets if the call fails."""
    try:
        from azure.identity import AzureCliCredential
        from openai import AzureOpenAI
    except Exception:
        return _fallback_actions(sf, alerts, owners, accounts)

    try:
        cred = AzureCliCredential()

        def _token() -> str:
            return cred.get_token("https://cognitiveservices.azure.com/.default").token

        client = AzureOpenAI(
            azure_endpoint="https://apro-openai.openai.azure.com/",
            azure_ad_token_provider=_token,
            api_version="2025-04-01-preview",
        )
        cadence = "weekly" if weekly else "this week"
        system = (
            "You are a Sales Operations Copilot for SimCorp. "
            "Land+Expand → ARR; Renewal → ACV; never blend. "
            f"Produce 3-5 SHORT bullet recommendations for what a Sales Director should act on {cadence}. "
            "Each bullet ≤ 25 words, action-first ('Submit Commercial Approval...'), "
            "cite specific deal/owner/account names + dollar amounts from the data. "
            "No preamble, no headers, no markdown. Return one bullet per line, no leading dashes."
        )
        import json as _json

        payload = {
            "totals": sf.get("totals", {}),
            "quarters": sf.get("quarters", []),
            "top_alerts": [
                {
                    "name": a.get("name"),
                    "severity": a.get("severity"),
                    "count": a.get("count"),
                    "total_arr": a.get("total_arr"),
                    "samples": (a.get("samples") or [])[:3],
                }
                for a in (alerts or [])
                if a.get("severity") == "critical"
            ][:5],
            "top_owners": owners[:5],
            "top_accounts": accounts[:5],
        }
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _json.dumps(payload, default=str, indent=2)},
            ],
            max_completion_tokens=400,
        )
        text = (resp.choices[0].message.content or "").strip()
        bullets = [
            ln.lstrip("-•* ").strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        bullets = [b for b in bullets if len(b) > 5]
        return bullets[:5] or _fallback_actions(sf, alerts, owners, accounts)
    except Exception:
        return _fallback_actions(sf, alerts, owners, accounts)


def _fallback_actions(sf: dict, alerts: list, owners: list, accounts: list) -> list[str]:
    """Deterministic recommendations when LLM is unavailable."""
    out: list[str] = []
    crit = [a for a in (alerts or []) if a.get("severity") == "critical"]
    if crit:
        top = max(crit, key=lambda a: float(a.get("total_arr") or 0))
        out.append(
            f"Resolve top critical alert: {top.get('name')} — "
            f"{top.get('count')} opps, {_fmt_money(float(top.get('total_arr') or 0))} ARR."
        )
    if accounts:
        a0 = accounts[0]
        out.append(
            f"Drill {a0.get('account')} ({a0.get('deal_count')} flagged deals, "
            f"{_fmt_money(float(a0.get('total_arr') or 0))} ARR) for governance debt."
        )
    if owners:
        o0 = owners[0]
        out.append(
            f"Brief {o0.get('owner')} on flagged book "
            f"({_fmt_money(float(o0.get('total_arr') or 0))} ARR across "
            f"{o0.get('deal_count')} deals)."
        )
    quarters = sf.get("quarters") or []
    if len(quarters) >= 2:
        q1 = quarters[1]
        out.append(
            f"Validate {q1.get('label')} forecast: "
            f"{_fmt_money(q1.get('weighted_new_business_arr') or 0)} weighted ARR."
        )
    out.append("Confirm Commercial Approval status on all Land Stage 3+ deals before week-end.")
    return out[:5]


# --- Slide builders ---------------------------------------------------------


def _strip_template_demo_slides(prs: Presentation) -> None:
    """The SimCorp template ships with ~14 demo slides. Drop them so our
    7 generated slides are the only ones in the output deck. Preserves
    masters/layouts/theme — just removes the body slides."""
    sldIdLst = prs.slides._sldIdLst  # noqa: SLF001 — python-pptx public-ish
    # Iterate a copy because we mutate
    for sldId in list(sldIdLst):
        rId = sldId.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        # Drop the relationship + the sldId entry
        try:
            prs.part.drop_rel(rId)
        except Exception:
            pass
        sldIdLst.remove(sldId)


def _build_title_slide(prs: Presentation, today: dt.date) -> Any:
    layout = prs.slide_layouts[LAYOUT_TITLE]
    slide = prs.slides.add_slide(layout)
    long_date = today.strftime("%A, %B %-d, %Y")
    # Use the layout's TITLE placeholder where present
    if slide.shapes.title is not None:
        slide.shapes.title.text = "Sales Operations Daily Brief"
    else:
        _add_title(slide, "Sales Operations Daily Brief")
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(2.4),
        Inches(12.33),
        Inches(0.6),
        long_date,
        Pt(20),
        color=COLOR_BODY_TEXT,
    )
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(3.2),
        Inches(12.33),
        Inches(0.5),
        "Prepared for: Sales Operations leadership",
        Pt(14),
        color=COLOR_BODY_TEXT,
    )
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(3.7),
        Inches(12.33),
        Inches(0.5),
        "Source: Salesforce + apro-openai (Microsoft Agent Framework)",
        Pt(12),
        color=FOOTER_COLOR,
    )
    return slide


def _exec_summary_bullets(sf: dict, alerts: list, owners: list, accounts: list) -> list[str]:
    totals = sf.get("totals", {}) or {}
    open_arr = float(totals.get("new_business_arr_open_this_quarter") or 0)
    weighted_arr = float(totals.get("weighted_new_business_arr") or 0)
    bullets: list[str] = []
    bullets.append(
        f"Current Q open new-business ARR: {_fmt_money(open_arr)} "
        f"(weighted: {_fmt_money(weighted_arr)})."
    )
    if accounts:
        a0 = accounts[0]
        total = sum(a.get("total_arr") or 0 for a in accounts) or 1
        pct = (float(a0.get("total_arr") or 0) / total) * 100
        bullets.append(
            f"#1 account concentration: {a0.get('account')} — "
            f"{_fmt_money(float(a0.get('total_arr') or 0))} ARR across "
            f"{a0.get('deal_count')} deals ({pct:.0f}% of top-15 flagged ARR)."
        )
    crit = [a for a in (alerts or []) if a.get("severity") == "critical"]
    if crit:
        top = max(crit, key=lambda a: float(a.get("total_arr") or 0))
        bullets.append(
            f"#1 critical alert: {top.get('name')} — "
            f"{top.get('count')} opps, "
            f"{_fmt_money(float(top.get('total_arr') or 0))} ARR."
        )
    if owners:
        o0 = owners[0]
        total_o = sum(o.get("total_arr") or 0 for o in owners) or 1
        pct_o = (float(o0.get("total_arr") or 0) / total_o) * 100
        bullets.append(
            f"#1 owner concentration: {o0.get('owner')} — "
            f"{_fmt_money(float(o0.get('total_arr') or 0))} ARR ({pct_o:.0f}% of top-10)."
        )
    return bullets


def _build_exec_summary_slide(
    prs: Presentation, sf: dict, alerts: list, owners: list, accounts: list
) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Executive summary — what to know in 30 seconds")
    bullets = _exec_summary_bullets(sf, alerts, owners, accounts)
    _add_bullets(
        slide,
        Inches(0.6),
        Inches(1.5),
        Inches(12.13),
        Inches(5.0),
        bullets,
        font_size=Pt(18),
    )
    return slide


def _build_forecast_slide(prs: Presentation, sf: dict) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Multi-quarter weighted forecast")

    quarters = sf.get("quarters") or []
    headers = ["Quarter", "Open ARR", "Weighted ARR", "Open ACV", "Weighted ACV"]
    rows: list[list[str]] = []
    cats: list[str] = []
    open_arr_series: list[float] = []
    weighted_arr_series: list[float] = []
    for q in quarters:
        label = q.get("label") or "—"
        open_arr = float(q.get("open_new_business_arr") or 0)
        w_arr = float(q.get("weighted_new_business_arr") or 0)
        open_acv = float(q.get("open_renewal_acv") or 0)
        w_acv = float(q.get("weighted_renewal_acv") or 0)
        rows.append(
            [
                label,
                _fmt_money_short(open_arr),
                _fmt_money_short(w_arr),
                _fmt_money_short(open_acv),
                _fmt_money_short(w_acv),
            ]
        )
        cats.append(label)
        open_arr_series.append(open_arr)
        weighted_arr_series.append(w_arr)

    _add_table(
        slide,
        Inches(0.5),
        Inches(1.4),
        Inches(6.0),
        Inches(2.0),
        headers,
        rows,
        right_align_cols={1, 2, 3, 4},
    )

    # Bar chart on the right: open ARR vs weighted ARR per quarter
    if cats:
        chart_data = CategoryChartData()
        chart_data.categories = cats
        chart_data.add_series("Open ARR", open_arr_series)
        chart_data.add_series("Weighted ARR", weighted_arr_series)
        chart_shape = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(7.0),
            Inches(1.4),
            Inches(5.8),
            Inches(4.5),
            chart_data,
        )
        chart = chart_shape.chart
        chart.has_title = True
        chart.chart_title.text_frame.text = "New-business ARR by quarter"
        for run in chart.chart_title.text_frame.paragraphs[0].runs:
            run.font.size = Pt(12)
            run.font.bold = True
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False

    _add_textbox(
        slide,
        Inches(0.5),
        Inches(6.2),
        Inches(12.33),
        Inches(0.4),
        "Land+Expand reported in ARR. Renewals reported in ACV. Never blended.",
        Pt(10),
        color=FOOTER_COLOR,
    )
    return slide


def _build_alerts_slide(prs: Presentation, alerts: list) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Top critical alerts")

    crit = [a for a in (alerts or []) if a.get("severity") == "critical"]
    crit.sort(key=lambda a: float(a.get("total_arr") or 0), reverse=True)
    headers = ["Alert", "# Opps", "Total ARR"]
    rows: list[list[str]] = []
    for a in crit[:5]:
        name = str(a.get("name") or "—")
        if len(name) > 70:
            name = name[:67] + "..."
        rows.append(
            [
                name,
                str(a.get("count") or 0),
                _fmt_money(float(a.get("total_arr") or 0)),
            ]
        )
    if not rows:
        rows = [["No critical alerts active", "—", "—"]]

    _add_table(
        slide,
        Inches(0.5),
        Inches(1.4),
        Inches(12.33),
        Inches(4.5),
        headers,
        rows,
        right_align_cols={1, 2},
    )
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(6.2),
        Inches(12.33),
        Inches(0.4),
        "Critical = Commercial Approval, KYC, or Stage-20 governance breach. Land deals require "
        "approval at all stages; Expand ≥€500k AER does too.",
        Pt(10),
        color=FOOTER_COLOR,
    )
    return slide


def _build_account_concentration_slide(prs: Presentation, accounts: list) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Account concentration on flagged ARR")

    headers = ["#", "Account", "# Deals", "ARR", "% of top-15"]
    total = sum(a.get("total_arr") or 0 for a in (accounts or [])) or 1
    rows: list[list[str]] = []
    for i, a in enumerate((accounts or [])[:10], 1):
        arr = float(a.get("total_arr") or 0)
        pct = (arr / total) * 100
        name = str(a.get("account") or "—")
        if len(name) > 50:
            name = name[:47] + "..."
        rows.append(
            [
                str(i),
                name,
                str(a.get("deal_count") or 0),
                _fmt_money(arr),
                f"{pct:.0f}%",
            ]
        )
    if not rows:
        rows = [["—", "No flagged accounts", "—", "—", "—"]]

    _add_table(
        slide,
        Inches(0.5),
        Inches(1.4),
        Inches(12.33),
        Inches(5.0),
        headers,
        rows,
        right_align_cols={0, 2, 3, 4},
    )
    return slide


def _build_owner_concentration_slide(prs: Presentation, owners: list) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Owner concentration on flagged ARR")

    headers = ["#", "Owner", "# Deals", "ARR", "% of top-10"]
    total = sum(o.get("total_arr") or 0 for o in (owners or [])) or 1
    rows: list[list[str]] = []
    for i, o in enumerate((owners or [])[:10], 1):
        arr = float(o.get("total_arr") or 0)
        pct = (arr / total) * 100
        rows.append(
            [
                str(i),
                str(o.get("owner") or "—"),
                str(o.get("deal_count") or 0),
                _fmt_money(arr),
                f"{pct:.0f}%",
            ]
        )
    if not rows:
        rows = [["—", "No flagged owners", "—", "—", "—"]]

    _add_table(
        slide,
        Inches(0.5),
        Inches(1.4),
        Inches(12.33),
        Inches(5.0),
        headers,
        rows,
        right_align_cols={0, 2, 3, 4},
    )
    return slide


def _build_actions_slide(prs: Presentation, bullets: list[str]) -> Any:
    layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(layout)
    _add_title(slide, "Recommended actions for the week")
    _add_bullets(
        slide,
        Inches(0.6),
        Inches(1.5),
        Inches(12.13),
        Inches(5.0),
        bullets,
        font_size=Pt(16),
    )
    return slide


# --- Orchestration ----------------------------------------------------------


def build_daily_deck(out_path: pathlib.Path, *, use_llm: bool = True) -> pathlib.Path:
    if not SIMCORP_TEMPLATE.exists():
        raise FileNotFoundError(f"SimCorp template not found at {SIMCORP_TEMPLATE}")

    today = dt.date.today()

    print("→ Pulling Salesforce snapshot...")
    from brief import pull_salesforce_snapshot  # type: ignore[import-not-found]

    sf = pull_salesforce_snapshot()

    print("→ Pulling alerts + concentration...")
    from alerts import (  # type: ignore[import-not-found]
        pull_account_concentration,
        pull_all_alerts,
        pull_owner_concentration,
    )

    alerts = pull_all_alerts()
    owners = pull_owner_concentration(top_n=10)
    accounts = pull_account_concentration(top_n=15)

    print(f"→ Generating recommended actions ({'LLM' if use_llm else 'fallback'})...")
    if use_llm:
        actions = llm_recommended_actions(sf, alerts, owners, accounts, weekly=False)
    else:
        actions = _fallback_actions(sf, alerts, owners, accounts)

    print("→ Building deck from SimCorp template...")
    prs = Presentation(str(SIMCORP_TEMPLATE))
    _strip_template_demo_slides(prs)

    _build_title_slide(prs, today)
    _build_exec_summary_slide(prs, sf, alerts, owners, accounts)
    _build_forecast_slide(prs, sf)
    _build_alerts_slide(prs, alerts)
    _build_account_concentration_slide(prs, accounts)
    _build_owner_concentration_slide(prs, owners)
    _build_actions_slide(prs, actions)

    # Footer on all 7 new slides we appended (the template ships with no
    # pre-existing slides; if it ever does, this still only stamps ours).
    new_slides = list(prs.slides)[-7:]
    total_new = len(new_slides)
    run_date = today.isoformat()
    for i, s in enumerate(new_slides, 1):
        _add_footer(s, i, total_new, run_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    print(f"✓ Wrote {out_path}")
    return out_path


def publish_onedrive(deck_path: pathlib.Path) -> pathlib.Path:
    target_dir = (
        pathlib.Path.home() / "Library" / "CloudStorage" / "OneDrive-SimCorp" / "Sales Ops Briefs"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / deck_path.name
    tmp = target.with_suffix(target.suffix + ".tmp")
    shutil.copyfile(deck_path, tmp)
    os.replace(tmp, target)
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        help="Output .pptx path; defaults to reports/deck-<today>.pptx",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip apro-openai recommended-actions generation; use fallback bullets.",
    )
    ap.add_argument(
        "--onedrive-publish",
        action="store_true",
        help="Atomic-write to OneDrive-SimCorp/Sales Ops Briefs/ for Power Automate pickup.",
    )
    args = ap.parse_args()

    today = dt.date.today()
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = (
        pathlib.Path(args.out) if args.out else REPORTS_DIR / f"deck-{today.isoformat()}.pptx"
    )

    deck_path = build_daily_deck(out_path, use_llm=not args.no_llm)

    if args.onedrive_publish:
        try:
            target = publish_onedrive(deck_path)
            print(f"✓ Published to OneDrive: {target}")
        except Exception as e:
            print(f"  ⚠ OneDrive publish failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
