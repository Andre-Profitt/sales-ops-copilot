#!/usr/bin/env python3
"""Build one fast SimCorp-branded KPI mockup slide."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state/2026-Q2/Jesper-Tyrer/factory/design-mockups/jesper_apac_kpi_strip_test.pptx"

FONT = "Microsoft Sans Serif"
BLACK = RGBColor(0x00, 0x00, 0x00)
NAVY = RGBColor(0x1A, 0x1D, 0x31)
BLUE = RGBColor(0x08, 0x3E, 0xA7)
PURPLE = RGBColor(0x4B, 0x17, 0xB6)
RED = RGBColor(0xEF, 0x3E, 0x4A)
GREY = RGBColor(0x66, 0x66, 0x66)
RULE = RGBColor(0xD9, 0xDD, 0xE6)


def inch(v: float) -> Emu:
    return Emu(int(v * 914400))


def delete_all_slides(prs: Presentation) -> None:
    ids = prs.slides._sldIdLst  # noqa: SLF001
    for i in range(len(prs.slides) - 1, -1, -1):
        prs.part.drop_rel(ids[i].rId)
        del ids[i]


def set_text(shape: Any, text: str) -> None:
    if shape is not None and shape.has_text_frame:
        shape.text_frame.text = text


def find(slide: Any, name: str) -> Any | None:
    return next((s for s in slide.shapes if s.name == name), None)


def remove(shape: Any | None) -> None:
    if shape is not None:
        shape._element.getparent().remove(shape._element)  # noqa: SLF001


def set_template_header(slide: Any) -> None:
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if shape.top < inch(0.9) and shape.width > inch(8):
            set_text(shape, "May forecast quality")
        elif inch(1.0) < shape.top < inch(1.55) and shape.width > inch(8):
            set_text(shape, "APAC LAND territory review · Salesforce snapshot 2026-04-30 · May 1 kickoff")


def tx(slide: Any, x: Emu, y: Emu, w: Emu, h: Emu, text: str, size: float, *, bold: bool = False, color: RGBColor = NAVY) -> Any:
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.clear()
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    p.space_after = Pt(0)
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    return box


def rule(slide: Any, x: Emu, y: Emu, w: Emu, color: RGBColor = NAVY, height: float = 0.012) -> None:
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, inch(height))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()


def build() -> Path:
    prs = Presentation(ROOT / "assets/LAND_template.pptx")
    delete_all_slides(prs)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_template_header(slide)
    remove(find(slide, "Text Placeholder 6"))
    remove(find(slide, "Content Placeholder 7"))

    left, top, width = inch(0.92), inch(2.12), inch(11.32)
    tx(slide, left, top, width, inch(0.28), "Q2 closeable pipe is concentrated in named deals; Best Case has no cushion.", 14.2, bold=True, color=BLACK)
    tx(slide, left, top + inch(0.38), width, inch(0.18), "EUR 5.1M closeable Land+Expand ARR splits between Commit and Pipeline; May actions should focus on close-date evidence and approval gaps.", 8.9, color=GREY)

    y = top + inch(0.92)
    rule(slide, left, y, width, NAVY, 0.015)
    headers = ["Forecast category", "Unweighted ARR", "Opps", "May operating read"]
    xs = [0.0, 3.25, 5.35, 6.35, 11.32]
    for i, h in enumerate(headers):
        tx(slide, left + inch(xs[i]), y + inch(0.15), inch(xs[i + 1] - xs[i] - 0.12), inch(0.12), h.upper(), 6.8, bold=True, color=GREY)
    rule(slide, left, y + inch(0.36), width, RULE, 0.006)

    rows = [
        ("Closeable Q2 pipe", "EUR 5.1M", "26", "CFQ numerator; inspect deal-level proof."),
        ("Commit", "EUR 2.8M", "11", "Hold close dates; clear current-quarter approvals."),
        ("Pipeline", "EUR 2.3M", "8", "Convert only where next steps are evidenced."),
        ("Best Case", "EUR 0.0M", "-", "No material cushion; do not underwrite upside."),
    ]
    for r_i, row in enumerate(rows):
        ry = y + inch(0.50 + r_i * 0.44)
        color = RED if row[0] == "Best Case" else NAVY
        tx(slide, left, ry, inch(3.0), inch(0.16), row[0], 8.9, bold=True, color=NAVY)
        tx(slide, left + inch(3.25), ry - inch(0.015), inch(1.8), inch(0.18), row[1], 11.8, bold=True, color=color)
        tx(slide, left + inch(5.35), ry, inch(0.8), inch(0.16), row[2], 8.8, color=GREY)
        tx(slide, left + inch(6.35), ry, inch(4.95), inch(0.16), row[3], 8.6, color=NAVY)
        rule(slide, left, ry + inch(0.29), width, RGBColor(0xEA, 0xEC, 0xF0), 0.004)

    tx(slide, left, inch(6.72), width, inch(0.14), "Metric basis: Land+Expand ARR is unweighted unless explicitly labeled weighted; Renewal ACV is separate.", 6.8, color=GREY)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(OUT)
    return OUT


if __name__ == "__main__":
    build()
