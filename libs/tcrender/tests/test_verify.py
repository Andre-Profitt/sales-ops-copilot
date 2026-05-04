"""Tests for tcrender.verify -- post-render evidence checks."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tcrender.verify import (
    VerifyResult,
    binding_evidence_strings,
    verify_render,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PPTTC = REPO_ROOT / "_windows_test" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"


# -- VerifyResult dataclass -----------------------------------------------


def test_verify_result_is_frozen() -> None:
    r = VerifyResult(
        found=("a",),
        missing=(),
        match_ratio=1.0,
        passed=True,
        scanned_xml_parts=1,
    )
    with pytest.raises((AttributeError, Exception)):
        r.passed = False  # type: ignore[misc]


# -- verify_render --------------------------------------------------------


def test_verify_render_finds_all_expected_strings(tmp_path: Path) -> None:
    """When every expected string appears in slide XML, passed=True ratio=1.0."""
    pptx = _make_pptx_with_slides(
        tmp_path,
        slides=[
            "Jesper Tyrer review",
            "Period: 2026-Q2 -- APAC",
        ],
    )
    r = verify_render(
        pptx,
        expected_strings=["Jesper Tyrer", "2026-Q2", "APAC"],
        min_match_ratio=0.5,
    )
    assert r.passed
    assert r.match_ratio == 1.0
    assert r.found == ("Jesper Tyrer", "2026-Q2", "APAC")
    assert r.missing == ()
    assert r.scanned_xml_parts == 2


def test_verify_render_fails_when_expected_strings_absent(tmp_path: Path) -> None:
    """A template-only deck (placeholders unsubstituted) must fail verification."""
    pptx = _make_pptx_with_slides(
        tmp_path,
        slides=["{director_name} review for {period} -- {scope_label}"],
    )
    r = verify_render(
        pptx,
        expected_strings=["Jesper Tyrer", "2026-Q2", "APAC"],
        min_match_ratio=0.5,
    )
    assert not r.passed
    assert r.match_ratio == 0.0
    assert r.found == ()
    assert set(r.missing) == {"Jesper Tyrer", "2026-Q2", "APAC"}


def test_verify_render_partial_match_meets_threshold(tmp_path: Path) -> None:
    """match_ratio ≥ min_match_ratio -> passed=True."""
    pptx = _make_pptx_with_slides(
        tmp_path,
        slides=["Jesper Tyrer in 2026-Q2"],  # 2/3 strings present
    )
    r = verify_render(
        pptx,
        expected_strings=["Jesper Tyrer", "2026-Q2", "APAC"],
        min_match_ratio=0.5,
    )
    assert r.passed
    assert r.match_ratio == round(2 / 3, 4)
    assert "Jesper Tyrer" in r.found
    assert "2026-Q2" in r.found
    assert "APAC" in r.missing


def test_verify_render_empty_expected_is_vacuous_pass(tmp_path: Path) -> None:
    pptx = _make_pptx_with_slides(tmp_path, slides=["anything"])
    r = verify_render(pptx, expected_strings=[], min_match_ratio=0.5)
    assert r.passed
    assert r.match_ratio == 1.0
    assert r.found == ()
    assert r.missing == ()


def test_verify_render_rejects_invalid_min_match_ratio(tmp_path: Path) -> None:
    pptx = _make_pptx_with_slides(tmp_path, slides=["x"])
    with pytest.raises(ValueError):
        verify_render(pptx, expected_strings=["x"], min_match_ratio=1.5)


def test_verify_render_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify_render(tmp_path / "nope.pptx", expected_strings=["x"])


# -- binding_evidence_strings ---------------------------------------------


def test_binding_evidence_strings_on_jesper_fixture() -> None:
    """Evidence list must include director-specific scalars and exclude boilerplate."""
    assert FIXTURE_PPTTC.exists(), f"fixture missing: {FIXTURE_PPTTC}"
    ev = binding_evidence_strings(FIXTURE_PPTTC)
    # Must include the director-specific identifiers we care about.
    assert "Jesper Tyrer" in ev
    assert "2026-Q2" in ev
    assert "APAC" in ev
    assert "Colonial First State Investments Limited" in ev
    # Must EXCLUDE boring stage labels that show up across every deck.
    assert "1 - Prospecting" not in ev
    assert "2 - Discovery" not in ev
    # Must exclude single-word "no" / generic short tokens.
    assert "no" not in ev
    # Order: deduped while preserving first-seen.
    assert len(ev) == len(set(ev))


def test_binding_evidence_strings_filters_short_strings(tmp_path: Path) -> None:
    """Strings shorter than the evidence floor are rejected."""
    p = tmp_path / "demo.ppttc"
    p.write_text(
        json.dumps(
            [
                {
                    "template": "x.pptx",
                    "data": [
                        # too short -> filtered
                        {"name": "S01_X", "table": [[{"string": "no"}]]},
                        {"name": "S01_Y", "table": [[{"string": "1"}]]},
                        # boring -> filtered
                        {
                            "name": "S05_StageLabel",
                            "table": [[{"string": "1 - Prospecting"}]],
                        },
                        # good
                        {
                            "name": "S01_DirectorName",
                            "table": [[{"string": "Jesper Tyrer"}]],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    ev = binding_evidence_strings(p)
    assert ev == ["Jesper Tyrer"]


def test_binding_evidence_strings_walks_multi_row_tables(tmp_path: Path) -> None:
    """Cells inside multi-row tables surface as evidence too (when good)."""
    p = tmp_path / "demo.ppttc"
    p.write_text(
        json.dumps(
            [
                {
                    "template": "x.pptx",
                    "data": [
                        {
                            "name": "S04_Pipe",
                            "table": [
                                [
                                    None,
                                    {"string": "Opening pipe (start of 2026-Q2)"},
                                    {"string": "Closing pipe (2026-Q2 CFQ)"},
                                ],
                                [
                                    {"string": "ARR (EUR)"},
                                    {"number": 0.0},
                                    {"number": 5_220_548.26},
                                ],
                            ],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    ev = binding_evidence_strings(p)
    # The two long header strings survive the boring-pattern filter.
    assert "Opening pipe (start of 2026-Q2)" in ev
    assert "Closing pipe (2026-Q2 CFQ)" in ev
    # 'ARR (EUR)' is len=9 so passes the >=4 floor; it's not filtered by
    # the boring pattern (which only catches bare "ARR").
    assert "ARR (EUR)" in ev


def test_binding_evidence_strings_rejects_invalid_top_level(tmp_path: Path) -> None:
    p = tmp_path / "bad.ppttc"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        binding_evidence_strings(p)


# -- helpers --------------------------------------------------------------


_SLIDE_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:bodyPr/>
          <a:p><a:r><a:t>{text}</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""


def _make_pptx_with_slides(tmp_path: Path, slides: list[str]) -> Path:
    """Build a minimal .pptx with N slides; each slide contains its text body."""
    out = tmp_path / "fake.pptx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, body in enumerate(slides, start=1):
            xml = _SLIDE_XML_TEMPLATE.format(text=_xml_escape(body))
            zf.writestr(f"ppt/slides/slide{i}.xml", xml.encode("utf-8"))
        zf.writestr("[Content_Types].xml", b"<Types/>")
    return out


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
