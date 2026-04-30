"""Build the SimCorp-branded LAND-review template (.pptx).

One-time generator. Output: `assets/LAND_template.pptx` — a 12-slide
template using the official SimCorp_PPT_Template.pptx layouts. Each
analytical slide carries a placeholder rectangle indicating exactly
which think-cell chart type to insert and which xlsx range to bind to.

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
LAYOUT_TITLE_CONTENT = 6  # Title and Content
LAYOUT_TWO_CONTENT = 7  # 2 x content
LAYOUT_BLANK = 24
LAYOUT_END_DISCLAIMER = 31

SLIDES: list[dict] = [
    {
        "layout": LAYOUT_TITLE,
        "title": "{director_name}",
        "subtitle": "{period} LAND review · {scope_label}",
        "placeholder": "",
    },
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Headline",
        "subtitle": "{period} closeable / beyond / renewal — three numbers, one slide",
        "placeholder": (
            "[think-cell text or 3 single-cell charts]\n"
            "Bind to:\n"
            "  Pipeline_Total!B2  →  closeable Land+Expand ARR\n"
            "  Pipeline_Total!B3  →  open beyond {period}\n"
            "  Pipeline_Total!B4  →  renewal ACV"
        ),
    },
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
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Renewal Pipeline",
        "subtitle": "Open Renewal opps in scope — risk-of-termination flagged",
        "placeholder": (
            "[think-cell TABLE WITH FORMATTING — datalinked]\n"
            "Source: legacy land.xlsx (NOT model.xlsx)\n"
            "Range: At_Risk_Renewals!A1:G<last>\n"
            "  Columns: # / Account / Owner / Stage / Close Date / ACV / Risk\n"
            "Empty if no Renewal opps with High/Very-High risk in scope."
        ),
    },
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
    {
        "layout": LAYOUT_TITLE_CONTENT,
        "title": "Stage × Industry",
        "subtitle": "Where the pipeline lives — cross-tab heat map",
        "placeholder": (
            "[think-cell HEAT MAP or 100%-stacked]\n"
            "Range: Pivots — find 'Stage × Industry' block\n"
            "  Rows  = Stages 1-8\n"
            "  Cols  = Industries (Asset Mgmt, Insurance, Bank, ...)\n"
            "Use color intensity to encode ARR magnitude"
        ),
    },
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
