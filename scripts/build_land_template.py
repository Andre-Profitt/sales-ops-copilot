"""Build the SimCorp-branded LAND-review template (.pptx).

One-time generator. Output: `assets/LAND_template.pptx` — a 28-slide
template using the official SimCorp_PPT_Template.pptx layouts. Each
analytical slide carries a placeholder rectangle indicating exactly
which think-cell chart type to insert and which xlsx range to bind to.

Outline aligned with the canonical 20-slide LAND structure (locked,
schema_version=2 — see brand-deck-agent-py/agent/land_system_prompt.py)
plus three Tier-A insight slides (Sales Velocity, Account Expansion,
Pipeline Creation Velocity).

Per-month workflow once think-cell is installed:
  1. Open assets/LAND_template.pptx in PowerPoint
  2. Save-as for the target director
  3. For each slide with a "[think-cell chart...]" placeholder, follow
     docs/THINKCELL_SETUP.md — replace the placeholder with a think-cell
     chart datalinked to the named range
  4. Subsequent months: open the per-director PPTX, click "Update
     charts now" — datalinks pull fresh numbers from land.model.xlsx

Run: python3 scripts/build_land_template.py
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SOURCE_TEMPLATE = Path.home() / "projects/brand-deck-agent-py/assets/SimCorp_PPT_Template.pptx"
OUTPUT = ROOT / "assets/LAND_template.pptx"

# SimCorp 2024 brand palette (verbatim from simcorp-2024.json)
BRAND_PRIMARY = RGBColor(0x08, 0x3E, 0xA7)  # SimCorp blue
BRAND_SECONDARY = RGBColor(0x1A, 0x1D, 0x31)  # near-black
BRAND_GRAY = RGBColor(0x66, 0x66, 0x66)
BRAND_LIGHT_GRAY = RGBColor(0xE3, 0xE3, 0xE3)
BRAND_CORAL = RGBColor(0xEF, 0x3E, 0x4A)
BRAND_ORANGE = RGBColor(0xFB, 0x9B, 0x2A)


# Slide spec: (layout_idx, title, subtitle_or_body, chart_placeholder_caption)
# chart_placeholder_caption == "" means no placeholder (text-only slide).
# Otherwise it shows a SimCorp-blue dashed rectangle with this caption inside —
# tells the user exactly which think-cell chart + xlsx range to wire.
LAYOUT_TITLE = 0  # Title 1 (cover)
LAYOUT_DIVIDER_1 = 2  # Divider 1 (section break, text-only)
LAYOUT_TITLE_CONTENT = 6  # Title and Content
LAYOUT_TWO_CONTENT = 7  # 2 x content
LAYOUT_TWO_CONTENT_GRAD = 10  # 2 x content w/ gradient line (exec summary)
LAYOUT_BLANK = 24
LAYOUT_END_DISCLAIMER = 31

SLIDES: list[dict] = [
    # 1. Cover
    {
        "layout": LAYOUT_TITLE,
        "title": "{director_name}",
        "subtitle": "{period} LAND review · {scope_label}",
        "placeholder": "",
    },
    # 2. Exec Summary (NEW — 2-up content, gradient line)
    {
        "layout": LAYOUT_TWO_CONTENT_GRAD,
        "title": "Exec summary",
        "subtitle": "Highlights and risks — {period}",
        "placeholder": (
            "[Exec summary — manual paste for Phase 1]\n"
            "Source: state/<period>/<director>/trends.json\n"
            "  highlights[] (each: claim + rule_id)\n"
            "  risks[]      (each: claim + rule_id)\n"
            "Phase 1: copy/paste from state/<period>/<director>/brief.md\n"
            "  '## Highlights' bullets into the LEFT content column\n"
            "  '## Risks' bullets into the RIGHT content column.\n"
            "Phase 2: build a HighlightsSummary sheet in model.xlsx that\n"
            "materializes the envelope arrays into bindable cells, then\n"
            "wire two think-cell 'Text Linked to Excel' bindings here\n"
            "(one per column) pointing at HighlightsSummary!A:A and\n"
            "HighlightsSummary!B:B."
        ),
    },
    # 3. Section divider — Pipeline (NEW)
    {
        "layout": LAYOUT_DIVIDER_1,
        "title": "Pipeline",
        "subtitle": "Open Land+Expand ARR · stage / aging / movement",
        "placeholder": "",
    },
    # 4. Pipe-movement bridge (was 3)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Pipe-movement bridge",
        "subtitle": "What moved this quarter — opening + new − won − lost = closing",
        "placeholder": (
            "[think-cell WATERFALL chart — datalinked]\n"
            "Range: Pipe_Movement!A2:B6\n"
            "  Categories  = Bucket label (col A)\n"
            "  Values      = ARR EUR (col B)\n"
            "Use 'e' (subtotal) on Closing pipe row. Connectors on by default.\n"
            "New+Advanced is currently a residual bucket — Phase 2 will\n"
            "decompose via OpportunityFieldHistory."
        ),
    },
    # 5. Pipeline by stage (was 4)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Pipeline by stage",
        "subtitle": "8-stage SimCorp sales process — open Land+Expand ARR, {period}",
        "placeholder": (
            "[think-cell BAR or COLUMN chart]\n"
            "Range: Pipeline_By_Stage!A2:B9\n"
            "  X-axis = Stage label  (col A)\n"
            "  Y-axis = ARR (EUR)    (col B)\n"
            "Optional 2nd series: # Opps from Pipeline_By_Stage!D2:D9"
        ),
    },
    # 6. Pipeline aging (was 5)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Pipeline aging",
        "subtitle": "Open Land+Expand ARR by days since CreatedDate",
        "placeholder": (
            "[think-cell STACKED BAR or 100% chart]\n"
            "Range: Pipeline_Aging!A2:E7\n"
            "  Categories  = Age bucket (col A)\n"
            "  Series      = ARR EUR (col D), # Opps (col E)\n"
            "Highlight zombie (>730d) bar in coral (#EF3E4A)"
        ),
    },
    # 7. Top deals — Land (was 6)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Top deals — Land",
        "subtitle": "Top-10 open Land deals by ARR (named accounts, owners, ages)",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: Top_Deals_Land!A1:H11\n"
            "  Columns: # / Account / Opportunity / Owner / Stage /\n"
            "           Close Date / Age (days) / ARR (EUR)\n"
            "Highlight Stage 5+ rows in pale green; flag Age > 365d in coral."
        ),
    },
    # 8. Top deals — Expand (was 7)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Top deals — Expand",
        "subtitle": "Top-10 open Expand deals by ARR (existing accounts being grown)",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: Top_Deals_Expand!A1:H11\n"
            "Same columns as Top deals — Land slide."
        ),
    },
    # 9. Pending Commercial Approval (was 8)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Pending Commercial Approval",
        "subtitle": "Stage 3+ Land/Expand deals missing the SimCorp Commercial Approval gate",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: Pending_Commercial_Approval!A3:H<last>\n"
            "  Columns: # / Account / Opportunity / Owner / Stage /\n"
            "           Close Date / Type / ARR (EUR)\n"
            "Per Commercial Handbook: Land = ALL deals require approval,\n"
            "Expand triggers at AER >= EUR 500k. Flag any rows here for the\n"
            "next Commercial Approval committee."
        ),
    },
    # 10. Section divider — Retention (NEW)
    {
        "layout": LAYOUT_DIVIDER_1,
        "title": "Retention",
        "subtitle": "Renewal book · NRR / GRR · forecast category",
        "placeholder": "",
    },
    # 11. Renewal Pipeline (was 9)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Renewal Pipeline",
        "subtitle": "Open Renewal opps in scope — risk-of-termination flagged",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING + HARVEY BALLS]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: At_Risk_Renewals!A1:H<last>\n"
            "  Columns: # / Account / Owner / Stage / Close Date / ACV /\n"
            "           Risk / Risk score (0-4)\n"
            "Insert a think-cell HARVEY BALL (Insert > think-cell > Elements >\n"
            "Harvey ball) in a new column to the right of Risk score. Bind the\n"
            "ball value to the Risk score column (0=empty, 4=full)."
        ),
    },
    # 12. GRR proxy (NEW) — actual sheet is GRR-proxy-only, NOT full NRR/churn/expansion
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "GRR proxy",
        "subtitle": "{period} renewal save rate — proxy from closed Renewal opps last 12mo",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Retention!A1:B4\n"
            "  Cols: Metric / Value\n"
            "  Rows: Won Renewal ACV (last 12mo), Lost Renewal ACV (last 12mo),\n"
            "        GRR proxy %\n"
            "Bind cell A5 separately as a footnote text element to surface\n"
            "the PROXY caveat (auto-renewals excluded, etc.).\n"
            "CAVEAT: this is GRR-proxy-only today. True NRR + churn ACV +\n"
            "expansion ACV require Pipeline_Snapshot__c history — Phase 2."
        ),
    },
    # 13. Forecast Category breakdown (was 10)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Forecast Category breakdown",
        "subtitle": "CFQ Land+Expand pipeline by SF ForecastCategoryName",
        "placeholder": (
            "[think-cell COLUMN chart or table — datalinked]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: Forecast_Category!A4:C<last>\n"
            "  Columns: Category / # Opps / ARR (EUR)\n"
            "Categories: Pipeline / Best Case / Commit / Closed / Omitted.\n"
            "Stakeholder framing: Commit is the floor; Best Case + Pipeline\n"
            "is the upside."
        ),
    },
    # 14. Section divider — Territory (NEW)
    {
        "layout": LAYOUT_DIVIDER_1,
        "title": "Territory",
        "subtitle": "Owner / industry / geography mix",
        "placeholder": "",
    },
    # 15. By owner (was 11)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "By owner",
        "subtitle": "Open Land+Expand ARR by rep within director scope",
        "placeholder": (
            "[think-cell horizontal BAR chart]\n"
            "Range: By_Owner!A2:B<last>\n"
            "  Y-axis  = Owner name (col A)\n"
            "  X-axis  = ARR (col B)"
        ),
    },
    # 16. Stage × Industry (was 12)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Stage × Industry",
        "subtitle": "Where the pipeline lives — cross-tab heat map",
        "placeholder": (
            "[think-cell MEKKO chart — variable-width 100%-stacked]\n"
            "Range: Pivots — find 'Stage × Industry' block on the Pivots sheet\n"
            "  Bar width  = total ARR per industry (column totals)\n"
            "  Bar height = stage mix % within each industry\n"
            "Mekko encodes ARR weight in bar width — heavier-pipe industries\n"
            "appear visually larger, replacing the heat-map workaround."
        ),
    },
    # 17. Per-territory pipeline mix (NEW)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Per-territory pipeline mix",
        "subtitle": "Open ARR by Account.BillingCountry within director scope",
        "placeholder": (
            "[think-cell BAR chart — datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Territory_Performance!A1:D<last>\n"
            "  Cols: # / Country / # Opps / Open ARR (EUR)\n"
            "  Pre-sorted descending by ARR (Top-N seed)\n"
            "X-axis = Country (col B), Y-axis = ARR (col D). Optional 2nd\n"
            "series: # Opps (col C) on a secondary axis. % of book is NOT\n"
            "in this sheet today — compute it as a deck-side derived field\n"
            "(=ARR / Pipeline_Total!B2+B3) if needed."
        ),
    },
    # 18. QTD Wins + Losses (NEW)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "QTD wins and losses",
        "subtitle": "Closed-won and closed-lost ARR — quarter-to-date",
        "placeholder": (
            "[think-cell GROUPED COLUMN chart or table — datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Wins_Losses_QTD!A1:D3\n"
            "  Cols: Outcome / # / ARR (Land+Expand, EUR) / ACV (Renewal, EUR)\n"
            "  Rows: Won, Lost\n"
            "Render as 2-row table OR grouped column (Won vs Lost). Highlight\n"
            "Won row in brand-blue (#083EA7); Lost row in coral (#EF3E4A).\n"
            "Cycle days is on the Sales_Velocity slide, not here."
        ),
    },
    # 19. Velocity (was 13)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Velocity",
        "subtitle": "Stage age (proxy via CreatedDate) — caveat in cell F1",
        "placeholder": (
            "[think-cell COMBO chart — bar + line]\n"
            "Range: Velocity!A3:E10\n"
            "  Bars (left axis)  = # Open opps (col B)\n"
            "  Line (right axis) = Avg age days (col C)\n"
            "  Annotate stages where >180d count (col E) > 0"
        ),
    },
    # 20. Section divider — Risks (NEW)
    {
        "layout": LAYOUT_DIVIDER_1,
        "title": "Risks",
        "subtitle": "Concentration · stale activity · velocity · expansion",
        "placeholder": "",
    },
    # 21. Concentration risk (was 14)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Concentration risk",
        "subtitle": "Top-N share of total open pipeline + single-deal flag",
        "placeholder": (
            "[think-cell text + 100%-stacked column]\n"
            "Cell binds:\n"
            "  Concentration!B5  →  largest deal account\n"
            "  Concentration!B6  →  largest deal ARR\n"
            "  Concentration!B7  →  share of total pipeline (%)\n"
            "  Concentration!B8  →  '25% threshold tripped?' flag\n"
            "Top-N column: Concentration!A12:C15 (Top 1/3/5/10 account share)"
        ),
    },
    # 22. Stage 3+ stale-activity (NEW)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Stage 3+ stale activity (CreatedDate proxy)",
        "subtitle": "Open late-stage opps older than 60 days by CreatedDate",
        "placeholder": (
            "[think-cell BAR chart — datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Stale_Activity!A1:C5\n"
            "  Cols: Stage / # Stale opps / ARR (EUR)\n"
            "  Rows: Stage 3 / Stage 4 / Stage 5 / Stage 6 (header in row 1)\n"
            "Bars: X-axis = Stage, Y-axis = ARR. Highlight bars where\n"
            "# stale opps > 5 in coral (#EF3E4A).\n"
            "CAVEAT: 'stale' is currently a CreatedDate-age proxy (>60d).\n"
            "True LastActivityDate-based staleness needs Account.\n"
            "LastActivityDate in tblData — Phase 3. Bind cell A7 separately\n"
            "as a footnote to surface this caveat."
        ),
    },
    # 23. Sales Velocity (NEW Tier-A)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Sales velocity",
        "subtitle": "(# opps × win rate × avg deal) ÷ cycle days — {period}",
        "placeholder": (
            "[think-cell text + single-cell bindings]\n"
            "Source: model.xlsx\n"
            "Range: Sales_Velocity!A1:C6\n"
            "  Single-cell text bindings, in formula order:\n"
            "    Sales_Velocity!B2  →  # Open L+E opps\n"
            "    Sales_Velocity!B3  →  Win rate (CFQ Land+Expand closed)\n"
            "    Sales_Velocity!B4  →  Avg deal size (won, last 6mo, EUR)\n"
            "    Sales_Velocity!B5  →  Avg cycle days (won, last 6mo)\n"
            "    Sales_Velocity!B6  →  Velocity (EUR / day)\n"
            "Render 4 component KPI tiles across the slide; B6 (velocity)\n"
            "sits center-large. The 'Note' column on each row (col C) is the\n"
            "stakeholder-facing methodology — bind as italic-gray footnote.\n"
            "No Δ-vs-prior cell exists today; QoQ delta is a Phase 2 ask."
        ),
    },
    # 24. Account Expansion (NEW Tier-A)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Account expansion",
        "subtitle": "Top-15 accounts × motions (Land / Expand / Renewal)",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Account_Expansion!A1:F16\n"
            "  Cols: # / Account / Land ARR / Expand ARR / Renewal ACV / # Motions\n"
            "  Rows: Top-15 accounts by total open pipeline\n"
            "Highlight rows where # Motions (col F) = 3 in pale aqua (#DCEEF5) —\n"
            "these are full-stack expansion candidates. Conditional fill on\n"
            "ARR cells (cols C/D/E): zero = light gray, > EUR 500k = brand-blue tint."
        ),
    },
    # 25. Pipeline Creation Velocity (NEW Tier-A)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Pipeline creation velocity",
        "subtitle": "12-week rolling — # new opps and ARR added",
        "placeholder": (
            "[think-cell COMBO chart — bar + line, datalinked]\n"
            "Source: model.xlsx\n"
            "Range: Pipeline_Creation_Velocity!A1:C13\n"
            "  Cols: Week-ending / # new opps / ARR added (EUR)\n"
            "  Rows: 12 weekly buckets, oldest first\n"
            "Bars (left axis)  = # new opps (col B)\n"
            "Line (right axis) = ARR added (col C)\n"
            "Annotate weeks where # new opps = 0 (creation drought) and\n"
            "weeks where ARR added is in the top quartile of the window."
        ),
    },
    # 26. Action items (was 15)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Action items",
        "subtitle": "{period} ranked actions for the director",
        "placeholder": (
            "[think-cell TABLE — datalinked]\n"
            "Range: Action_Items!A1:G<last>  (in legacy land.xlsx, NOT model)\n"
            "  Cols: # / Priority / Rule / Claim / Suggested action / Due / Owner\n"
            "Conditional fill on Priority col (HIGH=coral, MEDIUM=orange, LOW=gray)"
        ),
    },
    # 27. Risks & outlook (was 16)
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Risks & outlook",
        "subtitle": "Narrative — pulled from brief.md",
        "placeholder": (
            "[plain text — paste from brief.md '## Risks' section]\n"
            "No think-cell binding here; this slide stays narrative.\n"
            "Replace per director by copying brief.md ## Risks bullets."
        ),
    },
    # 28. Closing (was 17)
    {
        "layout": LAYOUT_END_DISCLAIMER,
        "title": "Thank you",
        "subtitle": (
            "Aggregate-only per SimCorp AI Code of Conduct §8. "
            "All figures FX-converted to EUR via SF convertCurrency() at the per-record "
            "level. Proxy / derived metrics flagged in their respective sheets and "
            "documented in the Notes appendix of the companion xlsx."
        ),
        "placeholder": "",
    },
]


def _add_placeholder_box(slide, caption: str) -> None:
    """Add a SimCorp-blue dashed rectangle with caption text inside.

    Marks where think-cell chart goes + tells the user exactly which range
    to bind. Positioned in the lower 2/3 of the slide (below the title).
    """
    if not caption:
        return
    left = Inches(0.5)
    top = Inches(2.0)
    width = Inches(12.33)
    height = Inches(4.8)
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    # Dashed blue outline + light-gray fill so it reads as a placeholder
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xF5, 0xF8, 0xFD)
    box.line.color.rgb = BRAND_PRIMARY
    box.line.width = Pt(1.5)
    # python-pptx exposes line.dash_style via lxml only; skip dashing for portability.
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.4)
    tf.margin_right = Inches(0.4)
    tf.margin_top = Inches(0.3)
    tf.margin_bottom = Inches(0.3)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    for i, line in enumerate(caption.split("\n")):
        run = (p if i == 0 else tf.add_paragraph()).add_run()
        run.text = line
        run.font.name = "Arial"
        run.font.size = Pt(14)
        # First line bold (chart-type heading), rest body color
        run.font.color.rgb = BRAND_PRIMARY if i == 0 else BRAND_SECONDARY
        run.font.bold = i == 0
        if i > 0:
            run.font.size = Pt(11)


def _set_slide_text(slide, title: str, subtitle: str) -> None:
    """Populate the title + subtitle/body placeholders on a slide.

    The SimCorp template uses non-standard placeholder indices per layout
    (no idx=0 TITLE; instead bespoke BODY placeholders). We match the
    correct placeholder by inspecting the layout's DEFAULT placeholder
    text — "Click to add title" / "Presentation title here" / etc.
    """
    title_text_markers = (
        "click to add title",
        "presentation title here",
        "title here",
    )
    subtitle_text_markers = (
        "click to add subtitle",
        "subheading",
        "date/location",
        "click to add text",
    )
    title_set = False
    subtitle_set = False
    # Pair each slide placeholder with its layout placeholder (same idx) so
    # we can read the layout's default text.
    layout = slide.slide_layout
    layout_text_by_idx: dict[int, str] = {}
    for lph in layout.placeholders:
        if lph.has_text_frame and lph.placeholder_format is not None:
            layout_text_by_idx[lph.placeholder_format.idx] = lph.text_frame.text.lower()

    for shape in slide.placeholders:
        if not shape.has_text_frame or shape.placeholder_format is None:
            continue
        idx = shape.placeholder_format.idx
        default = layout_text_by_idx.get(idx, "")
        if not title_set and any(m in default for m in title_text_markers):
            shape.text_frame.text = title
            title_set = True
        elif not subtitle_set and any(m in default for m in subtitle_text_markers):
            shape.text_frame.text = subtitle
            subtitle_set = True
    # Fallback: if no markers matched (e.g., layout 31 with idx=28 only),
    # just stuff title into the first text placeholder.
    if not title_set:
        for shape in slide.placeholders:
            if shape.has_text_frame:
                shape.text_frame.text = title
                break


def _strip_existing_slides(prs: Presentation) -> None:
    """Remove all slides the SimCorp template ships with — we add our own."""
    sldIdLst = prs.slides._sldIdLst  # noqa: SLF001
    for sldId in list(sldIdLst):
        rId = sldId.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        prs.part.drop_rel(rId)
        sldIdLst.remove(sldId)


def main() -> None:
    if not SOURCE_TEMPLATE.exists():
        raise SystemExit(f"Source template missing: {SOURCE_TEMPLATE}")
    prs = Presentation(str(SOURCE_TEMPLATE))
    _strip_existing_slides(prs)

    layouts = list(prs.slide_layouts)
    for spec in SLIDES:
        layout = layouts[spec["layout"]] if spec["layout"] < len(layouts) else layouts[0]
        slide = prs.slides.add_slide(layout)
        _set_slide_text(slide, spec["title"], spec["subtitle"])
        _add_placeholder_box(slide, spec["placeholder"])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUTPUT))
    print(f"wrote: {OUTPUT}")
    print(f"slides: {len(prs.slides)}")


if __name__ == "__main__":
    main()
