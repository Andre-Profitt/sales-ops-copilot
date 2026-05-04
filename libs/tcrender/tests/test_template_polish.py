"""Tests for tcrender.template_polish.

Coverage:
    * embed_thinkcell_style: customXml part landed, content-types updated,
      presentation rels has the new customXml relationship.
    * add_section_dividers: new slide parts created, sldIdLst patched at
      correct positions, navy + coral hex visible in divider XML, footer
      suppressed via <p:hf>.
    * add_footer_to_master: master XML grew with PolishMasterFooter +
      separator line, slidenum/slidecount fields present, cover slide
      gets <p:hf> suppression.
    * polish_template: composite path produces a valid .pptx that
      python-pptx can parse, ends with the expected slide count, and the
      polished template still passes the verify-pptx-shape sanity.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from tcrender.template_polish import (
    PolishResult,
    SectionDivider,
    add_footer_to_master,
    add_section_dividers,
    embed_thinkcell_style,
    polish_template,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_TEMPLATE = REPO_ROOT / "assets" / "LAND_thinkcell_seed.pptx"
STYLE_XML = REPO_ROOT / "assets" / "SimCorp-thinkcell-style.xml"


# -- shared fixtures ------------------------------------------------------


def _read_part(pptx: Path, name: str) -> str:
    with zipfile.ZipFile(pptx, "r") as zf:
        return zf.read(name).decode("utf-8")


def _slide_count(pptx: Path) -> int:
    with zipfile.ZipFile(pptx, "r") as zf:
        return sum(1 for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n))


def _make_minimal_pptx(tmp_path: Path) -> Path:
    """Build a minimal .pptx fixture for tests that do not need the seed."""
    out = tmp_path / "minimal.pptx"
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/slides/slide1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        '<Override PartName="/ppt/slides/slide2.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
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
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
        'Target="slideMasters/slideMaster1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        'Target="slides/slide1.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        'Target="slides/slide2.xml"/>'
        "</Relationships>"
    )
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        "<p:sldIdLst>"
        '<p:sldId id="256" r:id="rId2"/>'
        '<p:sldId id="257" r:id="rId3"/>'
        "</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/>'
        "</p:presentation>"
    )
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        "</p:spTree></p:cSld>"
        "</p:sld>"
    )
    master = (
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
        zf.writestr("ppt/slides/slide1.xml", slide)
        zf.writestr("ppt/slides/slide2.xml", slide)
        zf.writestr("ppt/slideMasters/slideMaster1.xml", master)
    return out


# -- embed_thinkcell_style ------------------------------------------------


def test_embed_thinkcell_style_minimal(tmp_path: Path) -> None:
    """Embedding a tiny style XML lands as customXml/itemN.xml."""
    src = _make_minimal_pptx(tmp_path)
    style = tmp_path / "style.xml"
    style.write_text("<style><x/></style>", encoding="utf-8")
    out = tmp_path / "polished.pptx"

    result = embed_thinkcell_style(src, style, out)
    assert result == out and out.exists()

    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        # First free index is 1 in the minimal fixture (no existing items).
        assert "customXml/item1.xml" in names
        assert "customXml/itemProps1.xml" in names
        assert "customXml/_rels/item1.xml.rels" in names
        assert zf.read("customXml/item1.xml") == style.read_bytes()
        ct = zf.read("[Content_Types].xml").decode("utf-8")
        assert "/customXml/item1.xml" in ct
        assert "/customXml/itemProps1.xml" in ct
        rels = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        assert "../customXml/item1.xml" in rels
        assert "/customXml" in rels  # the relationship type is customXml

    # Input untouched.
    assert "customXml/item1.xml" not in zipfile.ZipFile(src).namelist()


def test_embed_thinkcell_style_does_not_mutate_input(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    src_bytes_before = src.read_bytes()
    style = tmp_path / "style.xml"
    style.write_text("<style/>", encoding="utf-8")

    embed_thinkcell_style(src, style, tmp_path / "out.pptx")
    assert src.read_bytes() == src_bytes_before


def test_embed_thinkcell_style_rejects_malformed_xml(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    style = tmp_path / "bad.xml"
    style.write_text("<not closed>", encoding="utf-8")
    with pytest.raises(ValueError):
        embed_thinkcell_style(src, style, tmp_path / "out.pptx")


def test_embed_thinkcell_style_picks_next_free_index_with_existing_items(
    tmp_path: Path,
) -> None:
    """When customXml/item1.xml..item3.xml exist, the new style lands at item4."""
    if not SEED_TEMPLATE.exists():
        pytest.skip(f"seed template missing: {SEED_TEMPLATE}")
    out = tmp_path / "polished.pptx"
    result = embed_thinkcell_style(SEED_TEMPLATE, STYLE_XML, out)
    with zipfile.ZipFile(result, "r") as zf:
        assert "customXml/item4.xml" in zf.namelist()
        assert "customXml/itemProps4.xml" in zf.namelist()


# -- add_section_dividers -------------------------------------------------


def test_add_section_dividers_minimal(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    out = tmp_path / "out.pptx"
    dividers = [
        SectionDivider(insert_before_slide_index=0, roman="I", title="First"),
        SectionDivider(insert_before_slide_index=1, roman="II", title="Second"),
    ]
    add_section_dividers(src, dividers, out)
    assert out.exists()

    # Started with 2 slides, expect 4.
    assert _slide_count(out) == 4

    pres = _read_part(out, "ppt/presentation.xml")
    sld_ids = re.findall(r"<p:sldId[^>]*r:id=\"([^\"]+)\"", pres)
    assert len(sld_ids) == 4

    # Each new slide carries navy + coral hex and the footer-suppression flag.
    new_slides = [n for n in zipfile.ZipFile(out).namelist() if n.startswith("ppt/slides/slide")]
    new_slides = sorted(new_slides)
    # slide3 + slide4 are the new ones (next free indices in the minimal fixture).
    new_count = 0
    for n in new_slides:
        x = _read_part(out, n)
        if "SectionDividerBackground" in x:
            new_count += 1
            assert "083EA7" in x
            assert "EF3E4A" in x
            assert "<p:hf" in x
            assert "{director_name}" in x
            assert "{period}" in x
    assert new_count == 2


def test_add_section_dividers_inserts_at_correct_positions(tmp_path: Path) -> None:
    """A divider with insert_before_slide_index=0 must end up at position 1."""
    src = _make_minimal_pptx(tmp_path)
    out = tmp_path / "out.pptx"
    add_section_dividers(
        src,
        [SectionDivider(insert_before_slide_index=0, roman="I", title="Top")],
        out,
    )
    pres = _read_part(out, "ppt/presentation.xml")
    rels = _read_part(out, "ppt/_rels/presentation.xml.rels")
    rel_targets = {
        m.group(1): m.group(2)
        for m in re.finditer(r'Id="([^"]+)"[^>]*Target="(slides/slide\d+\.xml)"', rels)
    }
    sld_ids = re.findall(r"<p:sldId[^>]*r:id=\"([^\"]+)\"", pres)
    # First entry must point at the new divider, not slide1.
    first_target = rel_targets[sld_ids[0]]
    # The minimal fixture's existing slides are slide1.xml + slide2.xml,
    # so the new divider must land on slide3.xml.
    assert first_target == "slides/slide3.xml"


def test_add_section_dividers_rejects_invalid_input(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    with pytest.raises(ValueError):
        add_section_dividers(
            src,
            [SectionDivider(insert_before_slide_index=-1, roman="I", title="x")],
            tmp_path / "out.pptx",
        )
    with pytest.raises(ValueError):
        add_section_dividers(
            src,
            [SectionDivider(insert_before_slide_index=0, roman="", title="x")],
            tmp_path / "out.pptx",
        )
    with pytest.raises(ValueError):
        add_section_dividers(
            src,
            [SectionDivider(insert_before_slide_index=0, roman="I", title="")],
            tmp_path / "out.pptx",
        )


def test_add_section_dividers_xml_escapes_title(tmp_path: Path) -> None:
    """Titles like 'Concentration & Risk' must produce well-formed XML."""
    src = _make_minimal_pptx(tmp_path)
    out = tmp_path / "out.pptx"
    add_section_dividers(
        src,
        [SectionDivider(insert_before_slide_index=0, roman="III", title="A & B <c>")],
        out,
    )
    # Read the new slide and parse it (guards against bad escaping).
    from lxml import etree

    with zipfile.ZipFile(out, "r") as zf:
        # Find the new divider slide.
        for n in zf.namelist():
            if n.startswith("ppt/slides/slide") and n.endswith(".xml"):
                xml_bytes = zf.read(n)
                if b"SectionDividerBackground" in xml_bytes:
                    etree.fromstring(xml_bytes)  # must not raise
                    assert b"A &amp; B &lt;c&gt;" in xml_bytes


# -- add_footer_to_master -------------------------------------------------


def test_add_footer_to_master_minimal(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    out = tmp_path / "out.pptx"
    add_footer_to_master(src, out)
    assert out.exists()
    sm = _read_part(out, "ppt/slideMasters/slideMaster1.xml")
    assert "PolishMasterFooter" in sm
    assert "PolishMasterFooterLine" in sm
    assert "slidenum" in sm
    assert "slidecount" in sm
    assert "{director_name}" in sm
    assert "{period}" in sm
    # Cover slide receives <p:hf> opt-out.
    s1 = _read_part(out, "ppt/slides/slide1.xml")
    assert "<p:hf" in s1


def test_add_footer_to_master_idempotent(tmp_path: Path) -> None:
    """Running twice does not double-inject."""
    src = _make_minimal_pptx(tmp_path)
    once = tmp_path / "once.pptx"
    twice = tmp_path / "twice.pptx"
    add_footer_to_master(src, once)
    add_footer_to_master(once, twice)
    sm_twice = _read_part(twice, "ppt/slideMasters/slideMaster1.xml")
    assert sm_twice.count('PolishMasterFooter"') == 1


def test_add_footer_to_master_does_not_mutate_input(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    src_bytes_before = src.read_bytes()
    add_footer_to_master(src, tmp_path / "out.pptx")
    assert src.read_bytes() == src_bytes_before


# -- polish_template (composite) ------------------------------------------


def test_polish_template_minimal_composite(tmp_path: Path) -> None:
    src = _make_minimal_pptx(tmp_path)
    style = tmp_path / "style.xml"
    style.write_text("<style/>", encoding="utf-8")
    out = tmp_path / "polished.pptx"

    result = polish_template(
        template_path=src,
        style_xml_path=style,
        section_dividers=[
            SectionDivider(insert_before_slide_index=0, roman="I", title="A"),
            SectionDivider(insert_before_slide_index=1, roman="II", title="B"),
        ],
        output_path=out,
    )
    assert isinstance(result, PolishResult)
    assert result.style_embedded is True
    assert result.section_dividers_added == 2
    assert result.footer_added is True
    assert result.original_slide_count == 2
    assert result.polished_slide_count == 4

    # Polished file must be a valid zip and contain all three additions.
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        assert any(n.startswith("customXml/item") and n.endswith(".xml") for n in names)
        assert "ppt/slideMasters/slideMaster1.xml" in names
        sm = zf.read("ppt/slideMasters/slideMaster1.xml").decode("utf-8")
        assert "PolishMasterFooter" in sm


def test_polish_template_empty_dividers(tmp_path: Path) -> None:
    """Composite still works when no dividers are requested."""
    src = _make_minimal_pptx(tmp_path)
    style = tmp_path / "style.xml"
    style.write_text("<style/>", encoding="utf-8")
    out = tmp_path / "polished.pptx"
    result = polish_template(
        template_path=src,
        style_xml_path=style,
        section_dividers=[],
        output_path=out,
    )
    assert result.section_dividers_added == 0
    assert result.original_slide_count == result.polished_slide_count == 2


@pytest.mark.skipif(
    not SEED_TEMPLATE.exists() or not STYLE_XML.exists(),
    reason="seed template / style xml missing",
)
def test_polish_template_seed_end_to_end(tmp_path: Path) -> None:
    """Full polish on the production seed: 28 -> 32 slides, all checks pass."""
    out = tmp_path / "LAND_thinkcell_seed_polished.pptx"
    result = polish_template(
        template_path=SEED_TEMPLATE,
        style_xml_path=STYLE_XML,
        section_dividers=[
            SectionDivider(insert_before_slide_index=3, roman="I", title="Pipeline"),
            SectionDivider(insert_before_slide_index=10, roman="II", title="Renewals"),
            SectionDivider(insert_before_slide_index=20, roman="III", title="Concentration & Risk"),
            SectionDivider(insert_before_slide_index=25, roman="IV", title="Actions & Outlook"),
        ],
        output_path=out,
    )
    assert result.original_slide_count == 28
    assert result.polished_slide_count == 32

    # python-pptx round-trip: must parse without raising.
    pptx = pytest.importorskip("pptx")
    pres = pptx.Presentation(str(out))
    assert len(pres.slides) == 32
    # Master shape names contain the polished marker.
    master_shape_names = [s.name for s in pres.slide_master.shapes]
    assert "PolishMasterFooter" in master_shape_names
    assert "PolishMasterFooterLine" in master_shape_names

    # Existing tcfield_* binding shape on slide1 must still be present.
    with zipfile.ZipFile(out, "r") as zf:
        s1 = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "tcfield_S01_DirectorName" in s1
