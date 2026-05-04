"""Tests for tcrender.polish_pass.

Coverage (one test per fix + composite + idempotency):
    * donor-strip: shapes carrying donor instruction patterns are removed
      from a synthetic slide; a tcfield_*-named shape is preserved.
    * axis-fmt: a chart with title 'Pipe movement (ARR mEUR)' gets
      ``<c:numFmt formatCode='#,##0\\ "M"' sourceLinked="0"/>`` on its valAx.
    * divider-dedupe: a synthetic deck containing 2 dividers + 2 normal
      slides ends up with only the 2 normal slides.
    * naked-chart-frame: a slide with only a graphicFrame chart gains
      a PolishPassNakedTitle + PolishPassNakedSubtitle text shape.
    * cover-treatment: slide1 gains PolishPassCoverNavyStripe +
      PolishPassCoverCoralBand shapes, idempotent on repeat.
    * mekko-polish: slide whose text contains "Stage by industry" gains
      PolishPassMekkoBaseline + 5 PolishPassMekkoYTickN labels.
    * footer-subtler: master with PolishMasterFooter has its line softened
      and text run sizes downscaled to 800 (8pt), srgbClr to neutral_mid.
    * round-trip on Jesper's enhanced deck: polish_pass produces a valid
      .pptx with slide count 32 -> 28 (4 dividers removed) and the donor
      patterns purged from the 7 affected slides.
    * idempotency: re-polishing a deck whose audit sidecar already has
      ``polish_pass_applied: true`` raises ValueError.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from tcrender.polish_pass import (
    POLISH_PASS_AUDIT_KEY,
    PolishPassResult,
    SIMCORP_CORAL_HEX,
    SIMCORP_NAVY_HEX,
    SIMCORP_NEUTRAL_MID_HEX,
    polish_pass,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
JESPER_ENHANCED = (
    REPO_ROOT
    / "state"
    / "2026-Q2"
    / "Jesper-Tyrer"
    / "decks"
    / "20260503-182730"
    / "Jesper-Tyrer-LAND-2026-Q2-enhanced.pptx"
)


# -- shared synthetic-deck fixture builder --------------------------------


def _read_part(pptx: Path, name: str) -> str:
    with zipfile.ZipFile(pptx, "r") as zf:
        return zf.read(name).decode("utf-8")


def _slide_count(pptx: Path) -> int:
    with zipfile.ZipFile(pptx, "r") as zf:
        return sum(1 for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n))


def _make_synthetic_pptx(
    tmp_path: Path,
    slides: list[tuple[str, str]],
    *,
    masters: dict[str, str] | None = None,
    charts: dict[str, str] | None = None,
    chart_rels_per_slide: dict[str, list[str]] | None = None,
) -> Path:
    """Build a minimal synthetic .pptx for tests.

    Args:
        tmp_path: pytest tmp_path.
        slides: list of (slide_filename, slide_xml_body); slide_filename
            should be like 'slide1.xml'.
        masters: optional dict of {filename: xml_body} for slideMaster1/etc.
        charts: optional dict of {filename: xml_body} for chartN.xml in
            ppt/charts/.
        chart_rels_per_slide: optional dict of {slide_filename: [chart_filename...]}
            -- emits ppt/slides/_rels/<slide>.xml.rels referencing those charts.
    """
    out = tmp_path / "synth.pptx"
    masters = masters or {}
    charts = charts or {}
    chart_rels_per_slide = chart_rels_per_slide or {}

    # Build [Content_Types].xml -- one Override per slide + one for each
    # master + chart.
    overrides_xml = ""
    overrides_xml += (
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
    )
    for s_name, _ in slides:
        overrides_xml += (
            f'<Override PartName="/ppt/slides/{s_name}" '
            f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    if masters:
        for m_name in masters:
            overrides_xml += (
                f'<Override PartName="/ppt/slideMasters/{m_name}" '
                f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            )
    else:
        overrides_xml += (
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        )
    for c_name in charts:
        overrides_xml += (
            f'<Override PartName="/ppt/charts/{c_name}" '
            f'ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
        )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{overrides_xml}"
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="ppt/presentation.xml"/>'
        "</Relationships>"
    )

    pres_rel_lines = [
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
        'Target="slideMasters/slideMaster1.xml"/>'
    ]
    sld_id_entries: list[str] = []
    for i, (s_name, _) in enumerate(slides, start=2):
        rid = f"rId{i}"
        pres_rel_lines.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/{s_name}"/>'
        )
        sld_id_entries.append(f'<p:sldId id="{255 + i}" r:id="{rid}"/>')
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(pres_rel_lines)
        + "</Relationships>"
    )

    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        "<p:sldIdLst>" + "".join(sld_id_entries) + "</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/>'
        "</p:presentation>"
    )

    default_master = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        "</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
        'accent1="accent1" accent2="accent2" accent3="accent3" '
        'accent4="accent4" accent5="accent5" accent6="accent6" '
        'hlink="hlink" folHlink="folHlink"/>'
        "</p:sldMaster>"
    )

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("ppt/presentation.xml", presentation)
        zf.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        for s_name, body in slides:
            zf.writestr(f"ppt/slides/{s_name}", body)
            chart_targets = chart_rels_per_slide.get(s_name) or []
            if chart_targets:
                rel_lines = []
                for j, ct in enumerate(chart_targets, start=1):
                    rel_lines.append(
                        f'<Relationship Id="rId{j}" '
                        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" '
                        f'Target="../charts/{ct}"/>'
                    )
                rels = (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(rel_lines)
                    + "</Relationships>"
                )
                zf.writestr(f"ppt/slides/_rels/{s_name}.rels", rels)
        if masters:
            for m_name, body in masters.items():
                zf.writestr(f"ppt/slideMasters/{m_name}", body)
        else:
            zf.writestr("ppt/slideMasters/slideMaster1.xml", default_master)
        for c_name, body in charts.items():
            zf.writestr(f"ppt/charts/{c_name}", body)
    return out


def _wrap_slide(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        f"{body}"
        "</p:spTree></p:cSld>"
        "</p:sld>"
    )


def _shape(name: str, text: str, shape_id: int = 5) -> str:
    return (
        "<p:sp>"
        "<p:nvSpPr>"
        f'<p:cNvPr id="{shape_id}" name="{name}"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "<p:txBody>"
        "<a:bodyPr/><a:lstStyle/>"
        f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
    )


# -- fix 1: donor-strip ---------------------------------------------------


def test_donor_strip_removes_instruction_shapes(tmp_path: Path) -> None:
    """Donor-text shapes are removed; tcfield_* shapes are preserved."""
    body = (
        _shape(
            "Rectangle 5",
            "[think-cell TABLE WITH FORMATTING - datalinked] | "
            "Source: legacy land.xlsx (NOT model.xlsx) | Range: Foo!A1",
            shape_id=10,
        )
        + _shape("tcfield_S07_TopDealsLand", "#", shape_id=11)
        + _shape("Title 7", "Real title text", shape_id=12)
    )
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(body))],
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out, director_name="X", period="2026-Q2")
    assert out.exists()

    # Donor shape gone.
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "Rectangle 5" not in s1
    assert "[think-cell TABLE" not in s1
    # tcfield shape preserved.
    assert "tcfield_S07_TopDealsLand" in s1
    # Other title preserved.
    assert "Real title text" in s1

    assert any(f.startswith("donor_strip:slide1:Rectangle 5") for f in result.fixes_applied)


def test_donor_strip_preserves_tcfield_runs_clears_offending(tmp_path: Path) -> None:
    """tcfield_* shapes whose runs contain donor text get those runs cleared."""
    sp = (
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="20" name="tcfield_S02_ExecSummaryLeft"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "<p:txBody>"
        "<a:bodyPr/><a:lstStyle/>"
        "<a:p>"
        "<a:r><a:t>[Exec summary - manual paste for Phase 1]</a:t></a:r>"
        "<a:r><a:t>Real director data line</a:t></a:r>"
        "</a:p>"
        "</p:txBody>"
        "</p:sp>"
    )
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(sp))],
    )
    out = tmp_path / "polished.pptx"
    polish_pass(src, output_path=out, director_name="X", period="2026-Q2")
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    # tcfield wrapper preserved.
    assert "tcfield_S02_ExecSummaryLeft" in s1
    # The donor run got cleared, but the real run remains.
    assert "Real director data line" in s1
    assert "Exec summary - manual paste" not in s1


# -- fix 2: axis numFmt ---------------------------------------------------


def _chart_xml(title_text: str, *, with_existing_numfmt: bool = False) -> str:
    extra_nf = '<c:numFmt formatCode="0,0000" sourceLinked="1"/>' if with_existing_numfmt else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<c:chart>"
        "<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/>"
        f"<a:p><a:r><a:t>{title_text}</a:t></a:r></a:p></c:rich></c:tx></c:title>"
        "<c:plotArea>"
        '<c:barChart><c:barDir val="col"/></c:barChart>'
        "<c:catAx>"
        '<c:axId val="111"/>'
        '<c:scaling><c:orientation val="minMax"/></c:scaling>'
        '<c:delete val="0"/>'
        '<c:axPos val="b"/>'
        "</c:catAx>"
        "<c:valAx>"
        '<c:axId val="222"/>'
        "<c:scaling/>"
        '<c:delete val="0"/>'
        '<c:axPos val="l"/>'
        "<c:majorGridlines/>"
        "<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/>"
        "<a:p><a:r><a:t>Y</a:t></a:r></a:p></c:rich></c:tx></c:title>"
        f"{extra_nf}"
        '<c:majorTickMark val="out"/>'
        '<c:tickLblPos val="nextTo"/>'
        '<c:crossAx val="111"/>'
        "</c:valAx>"
        "</c:plotArea>"
        "</c:chart>"
        "</c:chartSpace>"
    )


def test_axis_fmt_injects_numfmt_on_eur_chart(tmp_path: Path) -> None:
    """A chart titled 'Pipe movement (ARR mEUR)' gets EUR numFmt on valAx."""
    chart_body = _chart_xml("Pipe movement (ARR mEUR)")
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
        charts={"chart1.xml": chart_body},
        chart_rels_per_slide={"slide1.xml": ["chart1.xml"]},
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out, director_name="X", period="2026-Q2")
    chart_out = _read_part(out, "ppt/charts/chart1.xml")
    # Expect '#,##0\\ "M"' as formatCode (XML-escaped).
    assert 'formatCode="#,##0\\ &quot;M&quot;"' in chart_out or '#,##0\\ "M"' in chart_out
    assert 'sourceLinked="0"' in chart_out
    assert any(f.startswith("axis_fmt:chart1") for f in result.fixes_applied)


def test_axis_fmt_replaces_existing_numfmt(tmp_path: Path) -> None:
    """A chart that already has a stale numFmt gets overwritten."""
    chart_body = _chart_xml("Concentration risk", with_existing_numfmt=True)
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
        charts={"chart1.xml": chart_body},
        chart_rels_per_slide={"slide1.xml": ["chart1.xml"]},
    )
    out = tmp_path / "polished.pptx"
    polish_pass(src, output_path=out)
    chart_out = _read_part(out, "ppt/charts/chart1.xml")
    assert "0,0000" not in chart_out
    assert "#,##0.0%" in chart_out


# -- fix 3: divider dedupe -----------------------------------------------


def test_divider_dedupe_removes_dividers(tmp_path: Path) -> None:
    """Two synthetic dividers + two normal slides -> only the two normal."""
    divider_body = (
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="2" name="SectionDividerBackground"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="12192000" cy="6858000"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NAVY_HEX}"/></a:solidFill>'
        "</p:spPr>"
        "<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        "</p:sp>"
    )
    normal_body = _shape("Title 7", "Normal slide", shape_id=2)

    src = _make_synthetic_pptx(
        tmp_path,
        slides=[
            ("slide1.xml", _wrap_slide(normal_body)),
            ("slide2.xml", _wrap_slide(divider_body)),
            ("slide3.xml", _wrap_slide(normal_body)),
            ("slide4.xml", _wrap_slide(divider_body)),
        ],
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out)
    assert _slide_count(out) == 2

    pres = _read_part(out, "ppt/presentation.xml")
    sld_ids = re.findall(r"<p:sldId[^>]*r:id=\"([^\"]+)\"", pres)
    assert len(sld_ids) == 2

    rels = _read_part(out, "ppt/_rels/presentation.xml.rels")
    # Only the two non-divider slide rels remain.
    assert "slides/slide1.xml" in rels
    assert "slides/slide3.xml" in rels
    assert "slides/slide2.xml" not in rels
    assert "slides/slide4.xml" not in rels

    # [Content_Types] no longer mentions divider slide overrides.
    ct = _read_part(out, "[Content_Types].xml")
    assert "/ppt/slides/slide2.xml" not in ct
    assert "/ppt/slides/slide4.xml" not in ct

    assert sum(1 for f in result.fixes_applied if f.startswith("divider_dedupe:")) == 2


# -- fix 4: naked-chart frame --------------------------------------------


def test_naked_chart_frame_adds_title_and_subtitle(tmp_path: Path) -> None:
    """A naked-chart slide gets PolishPassNakedTitle + PolishPassNakedSubtitle."""
    gframe = (
        "<p:graphicFrame>"
        "<p:nvGraphicFramePr>"
        '<p:cNvPr id="2" name="Chart 1"/>'
        "<p:cNvGraphicFramePr/><p:nvPr/>"
        "</p:nvGraphicFramePr>"
        '<p:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></p:xfrm>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'r:id="rId1"/>'
        "</a:graphicData></a:graphic>"
        "</p:graphicFrame>"
    )
    # Subtitle band only -- no real title.
    subtitle_band = _shape("TextBox 2", "2026-Q2 LAND review - APAC", shape_id=3)
    body = subtitle_band + gframe
    chart_body = _chart_xml("Territory performance")
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(body))],
        charts={"chart1.xml": chart_body},
        chart_rels_per_slide={"slide1.xml": ["chart1.xml"]},
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(
        src,
        output_path=out,
        director_name="Jesper Tyrer",
        period="2026-Q2",
        scope_label="APAC",
    )
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "PolishPassNakedTitle" in s1
    assert "PolishPassNakedSubtitle" in s1
    assert "Territory performance" in s1
    assert "Jesper Tyrer" in s1
    assert any(f.startswith("naked_chart_frame:slide1:") for f in result.fixes_applied)


# -- fix 5: cover treatment ----------------------------------------------


def test_cover_treatment_adds_navy_stripe_and_coral_band(tmp_path: Path) -> None:
    """Slide1 gains a navy stripe + bottom coral band; idempotent on repeat."""
    body = _shape("Text Placeholder 1", "LAND review", shape_id=2)
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(body))],
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out)
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "PolishPassCoverNavyStripe" in s1
    assert "PolishPassCoverCoralBand" in s1
    assert SIMCORP_NAVY_HEX in s1
    assert SIMCORP_CORAL_HEX in s1
    assert "cover_treatment:navy_stripe+coral_band" in result.fixes_applied

    # Idempotent: re-polish should NOT double-inject (after wiping audit
    # sidecar).
    out2 = tmp_path / "polished2.pptx"
    result2 = polish_pass(out, output_path=out2)
    s1b = _read_part(out2, "ppt/slides/slide1.xml")
    assert s1b.count("PolishPassCoverNavyStripe") == 1
    assert s1b.count("PolishPassCoverCoralBand") == 1
    assert "cover_treatment:navy_stripe+coral_band" not in result2.fixes_applied


# -- fix 6: mekko polish -------------------------------------------------


def test_mekko_polish_adds_baseline_and_y_ticks(tmp_path: Path) -> None:
    """A 'Stage by industry' slide gets baseline + 5 tick labels."""
    body = _shape("TextBox 3", "Stage by industry (mekko)", shape_id=2)
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(body))],
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out)
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "PolishPassMekkoBaseline" in s1
    for label in ("0%", "25%", "50%", "75%", "100%"):
        assert label in s1
    assert sum(1 for f in result.fixes_applied if f.startswith("mekko_polish:")) == 1


# -- fix 7: footer subtler -----------------------------------------------


def test_footer_subtler_softens_line_and_text(tmp_path: Path) -> None:
    """The master's PolishMasterFooter line shrinks; text gets neutral_mid + 8pt."""
    master_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        # Polish footer line (accent1 0.5pt)
        "<p:cxnSp>"
        "<p:nvCxnSpPr>"
        '<p:cNvPr id="10" name="PolishMasterFooterLine"/>'
        "<p:cNvCxnSpPr/><p:nvPr/>"
        "</p:nvCxnSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="0"/></a:xfrm>'
        '<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        '<a:ln w="6350">'
        '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
        "</a:ln>"
        "</p:spPr>"
        "</p:cxnSp>"
        # Polish footer text (sz 900 navy)
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="11" name="PolishMasterFooter"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "<p:txBody>"
        "<a:bodyPr/><a:lstStyle/>"
        "<a:p>"
        '<a:r><a:rPr lang="en-US" sz="900">'
        '<a:solidFill><a:srgbClr val="6B7280"/></a:solidFill>'
        "</a:rPr><a:t>Footer</a:t></a:r>"
        "</a:p>"
        "</p:txBody>"
        "</p:sp>"
        "</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
        'accent1="accent1" accent2="accent2" accent3="accent3" '
        'accent4="accent4" accent5="accent5" accent6="accent6" '
        'hlink="hlink" folHlink="folHlink"/>'
        "</p:sldMaster>"
    )
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
        masters={"slideMaster1.xml": master_xml},
    )
    out = tmp_path / "polished.pptx"
    result = polish_pass(src, output_path=out)
    sm = _read_part(out, "ppt/slideMasters/slideMaster1.xml")
    # Line softened: w="3175" + grey srgbClr.
    assert 'w="3175"' in sm
    assert SIMCORP_NEUTRAL_MID_HEX in sm
    # Text size shrunk to 800 (8pt).
    assert 'sz="800"' in sm
    assert 'sz="900"' not in sm
    assert any(f.startswith("footer_subtler:") for f in result.fixes_applied)


# -- composite + idempotency ---------------------------------------------


def test_polish_pass_composite_minimal(tmp_path: Path) -> None:
    """Composite call hits multiple fixes on a single synthetic deck."""
    donor_body = _shape(
        "Rectangle 5",
        "[think-cell TABLE WITH FORMATTING] | Range: Foo!A1",
        shape_id=10,
    )
    cover_body = _shape("Text Placeholder 1", "LAND review", shape_id=2)
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[
            ("slide1.xml", _wrap_slide(cover_body)),
            ("slide2.xml", _wrap_slide(donor_body)),
        ],
    )
    out = tmp_path / "out.pptx"
    result = polish_pass(src, output_path=out)
    assert isinstance(result, PolishPassResult)
    assert result.original_slide_count == 2
    assert result.polished_slide_count == 2
    # Multiple fixes triggered.
    assert any(f.startswith("donor_strip:") for f in result.fixes_applied)
    assert any(f.startswith("cover_treatment") for f in result.fixes_applied)


def test_polish_pass_idempotency_guard(tmp_path: Path) -> None:
    """A deck whose audit.json says polish_pass_applied=true raises ValueError."""
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
    )
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({POLISH_PASS_AUDIT_KEY: True}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="already polished"):
        polish_pass(src, output_path=tmp_path / "polished.pptx")


def test_polish_pass_does_not_mutate_input(tmp_path: Path) -> None:
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
    )
    src_bytes = src.read_bytes()
    polish_pass(src, output_path=tmp_path / "polished.pptx")
    assert src.read_bytes() == src_bytes


def test_polish_pass_default_output_path(tmp_path: Path) -> None:
    """When output_path is None, default emits sibling -polished-<ts>.pptx."""
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
    )
    result = polish_pass(src)
    assert result.output_path.parent == src.parent
    assert "-polished-" in result.output_path.name
    assert result.output_path.exists()


def test_polish_pass_updates_audit_sidecar(tmp_path: Path) -> None:
    """When an audit sidecar is present, it gains polish_pass_applied=true."""
    src = _make_synthetic_pptx(
        tmp_path,
        slides=[("slide1.xml", _wrap_slide(""))],
    )
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"director": "X"}), encoding="utf-8")
    polish_pass(src, output_path=tmp_path / "polished.pptx")
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert payload[POLISH_PASS_AUDIT_KEY] is True
    assert "polish_pass_fixes_applied" in payload


# -- live round-trip on Jesper's enhanced deck ---------------------------


@pytest.mark.skipif(
    not JESPER_ENHANCED.exists(),
    reason="Jesper-Tyrer enhanced fixture not present",
)
def test_polish_pass_jesper_round_trip(tmp_path: Path) -> None:
    """Live round-trip on the Jesper enhanced deck.

    Asserts:
        * Slide count drops from 32 -> 28 (4 dividers removed).
        * Donor patterns no longer appear in any slide XML.
        * Output file is a valid zip + python-pptx parses it.
        * Cover slide carries navy stripe + coral band markers.
        * Mekko slide carries the baseline + tick marker.
    """
    # Copy to a writable tmp path -- tests should never rely on fixture
    # mtime / write back into state/.
    src_copy = tmp_path / JESPER_ENHANCED.name
    shutil.copyfile(JESPER_ENHANCED, src_copy)
    out = tmp_path / "Jesper-Tyrer-LAND-2026-Q2-final.pptx"

    result = polish_pass(
        src_copy,
        output_path=out,
        director_name="Jesper Tyrer",
        period="2026-Q2",
        scope_label="APAC",
    )
    assert isinstance(result, PolishPassResult)
    assert out.exists()

    # Slide-count delta: 32 -> 28.
    assert result.original_slide_count == 32
    assert result.polished_slide_count == 28

    # python-pptx must parse cleanly.
    pptx = pytest.importorskip("pptx")
    pres = pptx.Presentation(str(out))
    assert len(pres.slides) == 28

    # Donor patterns purged from every slide.
    forbidden = (
        "[think-cell TABLE WITH FORMATTING",
        "[Exec summary - manual paste",
        "Source: legacy land.xlsx",
    )
    with zipfile.ZipFile(out, "r") as zf:
        slide_blobs = [
            zf.read(n).decode("utf-8", errors="ignore")
            for n in zf.namelist()
            if re.match(r"^ppt/slides/slide\d+\.xml$", n)
        ]
    for blob in slide_blobs:
        for pat in forbidden:
            assert pat not in blob, f"forbidden donor text found: {pat}"

    # Cover slide carries navy stripe + coral band markers.
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "PolishPassCoverNavyStripe" in s1
    assert "PolishPassCoverCoralBand" in s1

    # Charts gain numFmt on valAx (sample chart13 = S04 Pipe movement).
    chart13 = _read_part(out, "ppt/charts/chart13.xml")
    assert 'sourceLinked="0"' in chart13

    # Result reports many fixes_applied entries.
    assert len(result.fixes_applied) >= 10
