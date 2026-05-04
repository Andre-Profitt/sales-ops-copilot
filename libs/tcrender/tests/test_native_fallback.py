"""Tests for tcrender.native_fallback -- post-render native chart/table fallback.

Mac-runnable. No SSH. Uses python-pptx to assert chart/table shapes were
added to the slides. The round-trip test (enhance against the live Jesper
deck) is gated behind ``TCRENDER_FALLBACK_LIVE=1`` so a missing fixture
doesn't break CI -- but it runs eagerly in dev because the fixture is
checked in.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pptx import Presentation
from pptx.util import Inches

from tcrender.native_fallback import (
    BRAND_PALETTE,
    EnhanceResult,
    enhance_deck,
)
from tcrender.verify import binding_evidence_strings, verify_render

# Repo layout: libs/tcrender/tests/test_native_fallback.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


# ----------------------------------------------------------------- API smoke


def test_brand_palette_has_required_keys() -> None:
    """BRAND_PALETTE is a small const dict with the documented keys."""
    required = {"primary", "accent", "success", "warning", "highlight"}
    assert required.issubset(BRAND_PALETTE.keys())
    # All values are hex colors
    for key, value in BRAND_PALETTE.items():
        assert isinstance(value, str)
        assert value.startswith("#")
        assert len(value) == 7


def test_enhance_result_is_frozen(tmp_path: Path) -> None:
    """EnhanceResult is a frozen dataclass."""
    r = EnhanceResult(enhanced_path=tmp_path / "x.pptx", bindings_inserted=[], skipped=[])
    with pytest.raises((AttributeError, Exception)):
        r.enhanced_path = tmp_path / "y.pptx"  # type: ignore[misc]


def test_enhance_deck_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        enhance_deck(
            deck_path=tmp_path / "nope.pptx",
            ppttc_path=tmp_path / "nope.ppttc",
        )


# ------------------------------------------------------- per-renderer smoke

# We build a minimal donor deck programmatically and a tiny synthetic
# .ppttc whose binding NAMES match S04..S26. enhance_deck will then
# dispatch to each renderer; we assert the resulting deck contains the
# expected shape kinds on the right slides.


def _synthetic_pptx(tmp_path: Path) -> Path:
    """Build a 28-slide blank donor deck so enhance_deck has slots to render into."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    for _ in range(28):
        prs.slides.add_slide(blank)
    out = tmp_path / "synthetic.pptx"
    prs.save(str(out))
    return out


def _synthetic_ppttc(tmp_path: Path) -> Path:
    """Build a synthetic .ppttc with one cell per multi-row binding."""
    bindings: list[dict[str, Any]] = [
        # Cover slide scalars (so subtitle resolves)
        {"name": "S01_DirectorName", "table": [[{"string": "Synthetic Director"}]]},
        {"name": "S01_Period", "table": [[{"string": "2026-Q9"}]]},
        {"name": "S01_ScopeLabel", "table": [[{"string": "TEST"}]]},
        # S04 waterfall
        {
            "name": "S04_PipeMovement",
            "table": [
                [
                    None,
                    {"string": "Open"},
                    {"string": "New"},
                    {"string": "Won"},
                    {"string": "Lost"},
                    {"string": "Close"},
                ],
                [
                    {"string": "ARR (mEUR)"},
                    {"number": 0.0},
                    {"number": 5.0},
                    {"number": -1.0},
                    {"number": -2.0},
                    {"number": 2.0},
                ],
            ],
        },
        # S05 stage bar
        {
            "name": "S05_PipelineByStage",
            "table": [
                [
                    None,
                    {"string": "1 - Prospecting"},
                    {"string": "2 - Discovery"},
                    {"string": "3 - Engagement"},
                ],
                [{"string": "Open ARR (mEUR)"}, {"number": 0.5}, {"number": 1.2}, {"number": 2.3}],
            ],
        },
        # S06 aging bar
        {
            "name": "S06_PipelineAging",
            "table": [
                [None, {"string": "0-30 days"}, {"string": "31-90 days"}, {"string": "> 730 days"}],
                [{"string": "Open ARR (mEUR)"}, {"number": 0.8}, {"number": 2.3}, {"number": 12.3}],
            ],
        },
        # S07 table
        {
            "name": "S07_TopDealsLand",
            "table": [
                [{"string": "#"}, {"string": "Account"}, {"string": "ARR (EUR)"}],
                [{"number": 1}, {"string": "Acme Corp Synthetic"}, {"number": 5000000}],
                [{"number": 2}, {"string": "Beta Industries"}, {"number": 2500000}],
            ],
        },
        # S08 table
        {
            "name": "S08_TopDealsExpand",
            "table": [
                [{"string": "#"}, {"string": "Account"}, {"string": "ARR (EUR)"}],
                [{"number": 1}, {"string": "Existing Acct One"}, {"number": 1000000}],
            ],
        },
        # S09 table
        {
            "name": "S09_PendingCommercialApproval",
            "table": [
                [{"string": "#"}, {"string": "Account"}, {"string": "ARR (EUR)"}],
                [{"number": 1}, {"string": "Pending Acct"}, {"number": 500000}],
            ],
        },
        # S11 risk table
        {
            "name": "S11_RenewalPipeline",
            "table": [
                [{"string": "#"}, {"string": "Account"}, {"string": "Risk score (0-4)"}],
                [{"number": 1}, {"string": "Renewal Acct"}, {"number": 3.5}],
            ],
        },
        # S12 GRR proxy
        {
            "name": "S12_GRRProxyTable",
            "table": [
                [{"string": "Metric"}, {"string": "Value"}],
                [{"string": "Won Renewal ACV"}, {"number": 9853726.64}],
                [{"string": "GRR proxy %"}, {"number": 1.0}],
            ],
        },
        # S13 forecast bar
        {
            "name": "S13_ForecastCategory",
            "table": [
                [None, {"string": "Pipeline"}, {"string": "Best Case"}, {"string": "Commit"}],
                [{"string": "ARR (mEUR)"}, {"number": 2.3}, {"number": 1.0}, {"number": 2.8}],
            ],
        },
        # S15 owner bar
        {
            "name": "S15_ByOwner",
            "table": [
                [None, {"string": "Alice Owner"}, {"string": "Bob Owner"}],
                [{"string": "Open ARR (mEUR)"}, {"number": 3.0}, {"number": 1.0}],
            ],
        },
        # S16 mekko
        {
            "name": "S16_StageByIndustry",
            "table": [
                [
                    None,
                    {"string": "Pension"},
                    {"string": "Asset Management"},
                    {"string": "Central Bank"},
                ],
                [{"string": "Prospecting"}, {"number": 0.0}, {"number": 0.0}, {"number": 4.9}],
                [{"string": "Discovery"}, {"number": 3.0}, {"number": 5.5}, {"number": 0.9}],
                [{"string": "Engagement"}, {"number": 8.8}, {"number": 3.3}, {"number": 0.8}],
            ],
        },
        # S17 territory bar
        {
            "name": "S17_TerritoryPerformance",
            "table": [
                [None, {"string": "Australia"}, {"string": "Malaysia"}],
                [{"string": "Open ARR (mEUR)"}, {"number": 12.7}, {"number": 6.9}],
            ],
        },
        # S18 wins/losses
        {
            "name": "S18_WinsLossesQTD",
            "table": [
                [None, {"string": "Won"}, {"string": "Lost"}],
                [{"string": "ARR (mEUR)"}, {"number": 1.6}, {"number": 6.0}],
            ],
        },
        # S19 velocity
        {
            "name": "S19_Velocity",
            "table": [
                [None, {"string": "Prospect."}, {"string": "Discovery"}, {"string": "Shortlist"}],
                [
                    {"string": "Median age (days)"},
                    {"number": 284.4},
                    {"number": 391.8},
                    {"number": 1344.0},
                ],
            ],
        },
        # S21 concentration
        {
            "name": "S21_ConcentrationRiskChart",
            "table": [
                [None, {"string": "Top 1 account"}, {"string": "Top 3 accounts"}],
                [{"string": "Share (%)"}, {"number": 11.6}, {"number": 25.2}],
            ],
        },
        # S22 stale
        {
            "name": "S22_StaleActivity",
            "table": [
                [None, {"string": "3 - Engagement"}, {"string": "6 - Contracting"}],
                [{"string": "ARR (mEUR)"}, {"number": 18.4}, {"number": 2.0}],
            ],
        },
        # S24 expansion table
        {
            "name": "S24_AccountExpansion",
            "table": [
                [{"string": "#"}, {"string": "Account"}, {"string": "Land ARR (EUR)"}],
                [{"number": 1}, {"string": "Expansion Acct"}, {"number": 5013582.78}],
            ],
        },
        # S25 line
        {
            "name": "S25_PipelineCreationVelocity",
            "table": [
                [None, {"string": "Feb 9"}, {"string": "Feb 16"}],
                [{"string": "New ARR (mEUR)"}, {"number": 0.0}, {"number": 1.7}],
            ],
        },
        # S26 priority table
        {
            "name": "S26_ActionItems",
            "table": [
                [{"string": "#"}, {"string": "Priority"}, {"string": "Claim"}],
                [{"number": 1}, {"string": "HIGH"}, {"string": "Synthetic high-priority claim"}],
                [{"number": 2}, {"string": "MEDIUM"}, {"string": "Synthetic medium claim"}],
            ],
        },
    ]
    out = tmp_path / "synthetic.ppttc"
    out.write_text(
        json.dumps([{"template": "synthetic.pptx", "data": bindings}]),
        encoding="utf-8",
    )
    return out


def test_enhance_deck_round_trip_synthetic(tmp_path: Path) -> None:
    """End-to-end on a synthetic donor + .ppttc -- every binding lands."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)

    out = tmp_path / "enhanced.pptx"
    result = enhance_deck(deck, ppttc, output_path=out)

    assert result.enhanced_path == out
    assert out.exists()
    # 19 multi-row bindings expected (S04..S26 except scalars)
    assert len(result.bindings_inserted) == 19, (
        f"expected 19 inserted, got {len(result.bindings_inserted)}: {result.bindings_inserted}"
    )
    assert not result.skipped, f"unexpected skips: {result.skipped}"


def test_enhance_deck_does_not_mutate_input(tmp_path: Path) -> None:
    """Input deck is never modified -- output goes to a new path."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)
    before = deck.read_bytes()

    out = tmp_path / "enhanced.pptx"
    enhance_deck(deck, ppttc, output_path=out)

    after = deck.read_bytes()
    assert before == after, "input deck was mutated"


def test_enhance_deck_inserts_native_charts(tmp_path: Path) -> None:
    """After enhancement, chart slides have a chart graphicFrame."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)
    out = tmp_path / "enhanced.pptx"
    enhance_deck(deck, ppttc, output_path=out)

    counts = _per_slide_counts(out)
    # Chart slides we expect a native chart on
    chart_slides = [4, 5, 6, 13, 15, 17, 18, 19, 21, 22, 25]
    for slide_num in chart_slides:
        chart_count, _ = counts[slide_num]
        assert chart_count >= 1, f"slide {slide_num} missing chart (got counts={counts[slide_num]})"


def test_enhance_deck_inserts_native_tables(tmp_path: Path) -> None:
    """After enhancement, table slides have a native table graphicFrame."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)
    out = tmp_path / "enhanced.pptx"
    enhance_deck(deck, ppttc, output_path=out)

    counts = _per_slide_counts(out)
    table_slides = [7, 8, 9, 11, 12, 24, 26]
    for slide_num in table_slides:
        _, tbl_count = counts[slide_num]
        assert tbl_count >= 1, f"slide {slide_num} missing table"


def test_enhance_deck_mekko_columns_proportional(tmp_path: Path) -> None:
    """S16 column rectangles are sized proportional to industry totals."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)
    out = tmp_path / "enhanced.pptx"
    enhance_deck(deck, ppttc, output_path=out)

    # Synthetic S16 totals: Pension=11.8, Asset Management=8.8, Central Bank=6.6
    expected_totals = [11.8, 8.8, 6.6]
    grand = sum(expected_totals)

    # Pull the top-row "industry-name + total" textboxes from slide 16; one
    # per industry. Their X positions should accumulate cleanly.
    widths = _mekko_column_widths(out, slide_num=16, n_industries=3)
    assert len(widths) == 3, f"expected 3 column widths, got {widths}"
    # Proportional within tolerance (Mekko has a 30k EMU gutter per column).
    canvas = sum(widths)
    for w, expected_share in zip(widths, [t / grand for t in expected_totals], strict=False):
        actual_share = w / canvas
        # +/-5% tolerance (gutters + minimum-width clamp on tiny columns).
        assert abs(actual_share - expected_share) < 0.05, (
            f"column width share {actual_share:.3f} != expected {expected_share:.3f}"
        )


def test_enhance_deck_data_lands_in_chart_xml(tmp_path: Path) -> None:
    """Synthetic-data evidence strings appear in chart XML or slide XML."""
    deck = _synthetic_pptx(tmp_path)
    ppttc = _synthetic_ppttc(tmp_path)
    out = tmp_path / "enhanced.pptx"
    enhance_deck(deck, ppttc, output_path=out)

    blob = _full_text_blob(out)
    # Period subtitle is added to every chart slide by enhance_deck.
    assert "2026-Q9" in blob, "subtitle period missing"
    # Table-cell data lands in slide XML
    assert "Acme Corp Synthetic" in blob, "S07 table data missing"
    assert "Expansion Acct" in blob, "S24 table data missing"
    assert "Synthetic high-priority claim" in blob, "S26 table data missing"
    # Chart-category evidence (lives in chart XML, not slide XML)
    assert "Australia" in blob, "S17 chart category missing"
    assert "Pension" in blob, "S16 mekko industry missing"


# ------------------------------------------------------ live (real fixture)

# The Jesper deck + .ppttc are checked in to state/. Run if present.

LIVE_DECK_DIR = REPO_ROOT / "state" / "2026-Q2" / "Jesper-Tyrer" / "decks"
LIVE_PPTTC = REPO_ROOT / "state" / "2026-Q2" / "Jesper-Tyrer" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"
LIVE = LIVE_PPTTC.exists() and LIVE_DECK_DIR.exists() and any(LIVE_DECK_DIR.iterdir())


def _latest_jesper_deck() -> Path | None:
    if not LIVE_DECK_DIR.exists():
        return None
    sub = sorted(p for p in LIVE_DECK_DIR.iterdir() if p.is_dir())
    if not sub:
        return None
    candidates = list(sub[-1].glob("Jesper-Tyrer-LAND-2026-Q2.pptx"))
    return candidates[0] if candidates else None


@pytest.mark.skipif(not LIVE, reason="Jesper-Tyrer fixture not present")
def test_enhance_deck_jesper_live_round_trip(tmp_path: Path) -> None:
    """Enhance the latest live Jesper deck; verify match-ratio >= 0.85."""
    src = _latest_jesper_deck()
    if src is None:
        pytest.skip("no Jesper archived deck found")

    out = tmp_path / "Jesper-Tyrer-enhanced-test.pptx"
    result = enhance_deck(src, LIVE_PPTTC, output_path=out)
    assert out.exists()
    assert len(result.bindings_inserted) >= 14, (
        f"expected at least 14 bindings inserted, got {len(result.bindings_inserted)}"
    )

    # Director-specific evidence persists
    blob = _full_text_blob(out)
    for evidence in ["Jesper Tyrer", "2026-Q2", "APAC", "Colonial First State"]:
        assert evidence in blob, f"director-specific evidence missing: {evidence!r}"

    # Slide-XML verify-render (legacy contract: scans only slide bodies).
    ev = binding_evidence_strings(LIVE_PPTTC)
    vr = verify_render(out, expected_strings=ev, min_match_ratio=0.85)
    assert vr.passed, (
        f"verify_render failed: match_ratio={vr.match_ratio} < 0.85; "
        f"missing sample={list(vr.missing[:3])}"
    )


# --------------------------------------------------------------- helpers


_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _per_slide_counts(pptx_path: Path) -> dict[int, tuple[int, int]]:
    """Return ``{slide_num: (chart_count, table_count)}`` for every slide."""
    out: dict[int, tuple[int, int]] = {}
    with zipfile.ZipFile(pptx_path) as zf:
        slides = sorted(
            (n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
            key=lambda n: int(n.split("slide")[-1].split(".")[0]),
        )
        for s in slides:
            idx = int(s.split("slide")[-1].split(".")[0])
            from lxml import etree

            root = etree.fromstring(zf.read(s))
            chart_count = 0
            table_count = 0
            for gf in root.findall(f".//{{{_NS['p']}}}graphicFrame"):
                graphic = gf.find(f"{{{_NS['a']}}}graphic/{{{_NS['a']}}}graphicData")
                if graphic is None:
                    continue
                uri = graphic.get("uri", "")
                if "chart" in uri:
                    chart_count += 1
                elif "table" in uri:
                    table_count += 1
            out[idx] = (chart_count, table_count)
    return out


def _full_text_blob(pptx_path: Path) -> str:
    """Concatenate text content of every slide AND chart part."""
    blob_parts: list[str] = []
    with zipfile.ZipFile(pptx_path) as zf:
        for n in zf.namelist():
            if n.startswith("ppt/slides/slide") and n.endswith(".xml"):
                blob_parts.append(zf.read(n).decode("utf-8", errors="ignore"))
            elif n.startswith("ppt/charts/chart") and n.endswith(".xml"):
                blob_parts.append(zf.read(n).decode("utf-8", errors="ignore"))
            elif n.startswith("ppt/embeddings/") and n.endswith(".xlsx"):
                # Chart-data spreadsheets often carry the literal numbers.
                pass
    return "\n".join(blob_parts)


def _mekko_column_widths(pptx_path: Path, *, slide_num: int, n_industries: int) -> list[int]:
    """Return widths (EMU) of the top-row industry-name boxes on the Mekko slide.

    The Mekko renderer adds N text boxes (one per industry) at the very top
    of the chart canvas, then draws stacked rectangles below. The text-box
    widths exactly match the column widths, so we sample those.
    """
    from lxml import etree

    widths: list[int] = []
    with zipfile.ZipFile(pptx_path) as zf:
        root = etree.fromstring(zf.read(f"ppt/slides/slide{slide_num}.xml"))
        for sp in root.findall(f".//{{{_NS['p']}}}sp"):
            xfrm = sp.find(f"{{{_NS['p']}}}spPr/{{{_NS['a']}}}xfrm")
            if xfrm is None:
                continue
            off = xfrm.find(f"{{{_NS['a']}}}off")
            ext = xfrm.find(f"{{{_NS['a']}}}ext")
            if off is None or ext is None:
                continue
            y = int(off.get("y", "0"))
            cy = int(ext.get("cy", "0"))
            cx = int(ext.get("cx", "0"))
            # Industry-name boxes sit just below the title (between roughly
            # 1.85M and 2.1M EMU vertically) and have a small height.
            if 1_800_000 < y < 2_000_000 and 200_000 < cy < 400_000:
                # Skip obvious legend / decorative shapes by minimum width
                if cx > 200_000:
                    widths.append(cx)
        # Sort by x to get column order
        # Re-extract with x for sorting
        xy_pairs = []
        for sp in root.findall(f".//{{{_NS['p']}}}sp"):
            xfrm = sp.find(f"{{{_NS['p']}}}spPr/{{{_NS['a']}}}xfrm")
            if xfrm is None:
                continue
            off = xfrm.find(f"{{{_NS['a']}}}off")
            ext = xfrm.find(f"{{{_NS['a']}}}ext")
            if off is None or ext is None:
                continue
            y = int(off.get("y", "0"))
            cy = int(ext.get("cy", "0"))
            cx = int(ext.get("cx", "0"))
            x = int(off.get("x", "0"))
            if 1_800_000 < y < 2_000_000 and 200_000 < cy < 400_000 and cx > 200_000:
                xy_pairs.append((x, cx))
        xy_pairs.sort()
        return [cx for _, cx in xy_pairs[:n_industries]]
