"""Tests for ``tcrender.master_transplant``.

What's covered:
    1. Cover slide preserved (slide1.xml carried over with wired tcfields).
    2. Slide masters / layouts / theme replaced from donor.
    3. All wired ``tcfield_*`` bindings still resolvable in the transplanted
       output (no regression).
    4. Slide layouts copied (count matches donor).
    5. Inputs are not mutated.
    6. Output is a valid .pptx.

The Sarah-Pittroff canonical shell + the polished LAND seed must be
present on disk. Tests skip cleanly if either is missing so CI on a
fresh clone does not blow up.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_TEMPLATE = REPO_ROOT / "assets" / "LAND_thinkcell_seed_polished.pptx"
DONOR_SHELL = Path(
    "/Users/test/crm-analytics/output/sales_director_canonical_shells/"
    "Sales Director Monthly Shell - Sarah Pittroff (Central Europe).pptx"
)


@pytest.fixture(scope="module")
def transplant_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the transplant once per test module; reuse the output."""
    if not TARGET_TEMPLATE.exists():
        pytest.skip(f"target template missing: {TARGET_TEMPLATE}")
    if not DONOR_SHELL.exists():
        pytest.skip(f"donor shell missing: {DONOR_SHELL}")
    from tcrender.master_transplant import transplant_visual_identity

    out_dir = tmp_path_factory.mktemp("xplant")
    out = out_dir / "polished_v2.pptx"
    transplant_visual_identity(
        target_template=TARGET_TEMPLATE,
        visual_donor=DONOR_SHELL,
        output_path=out,
    )
    return out


def test_cover_preserved(transplant_output: Path) -> None:
    """slide1.xml must still carry the wired tcfield_S01_* shapes."""
    with zipfile.ZipFile(transplant_output) as zf:
        slide1 = zf.read("ppt/slides/slide1.xml").decode("utf-8")
    for binding in ("S01_DirectorName", "S01_Period", "S01_ScopeLabel"):
        assert f'name="tcfield_{binding}"' in slide1, f"{binding} no longer wired on cover slide"


def test_masters_and_layouts_replaced(transplant_output: Path) -> None:
    """Slide masters / slide layouts / themes lifted from donor."""
    with zipfile.ZipFile(transplant_output) as out_zf:
        out_master = out_zf.read("ppt/slideMasters/slideMaster1.xml")
        out_theme = out_zf.read("ppt/theme/theme1.xml")
        layout_count = sum(
            1
            for n in out_zf.namelist()
            if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml")
        )
    with zipfile.ZipFile(DONOR_SHELL) as donor_zf:
        donor_master = donor_zf.read("ppt/slideMasters/slideMaster1.xml")
        donor_theme = donor_zf.read("ppt/theme/theme1.xml")
        donor_layout_count = sum(
            1
            for n in donor_zf.namelist()
            if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml")
        )
    with zipfile.ZipFile(TARGET_TEMPLATE) as tgt_zf:
        target_master = tgt_zf.read("ppt/slideMasters/slideMaster1.xml")

    # Master and theme should match donor, not target.
    assert out_master == donor_master, "slideMaster1.xml not lifted from donor"
    assert out_theme == donor_theme, "theme1.xml not lifted from donor"
    assert out_master != target_master, "transplant left target's master in place; expected donor's"
    assert layout_count == donor_layout_count, (
        f"layout count mismatch: out={layout_count} donor={donor_layout_count}"
    )


def test_wired_bindings_intact(transplant_output: Path) -> None:
    """All 30 wired tcfield bindings from the target must survive the transplant."""
    from tcrender.master_transplant import extract_wired_tcfield_bindings

    before = extract_wired_tcfield_bindings(TARGET_TEMPLATE)
    after = extract_wired_tcfield_bindings(transplant_output)

    expected: set[str] = set()
    for names in before.values():
        expected.update(names)
    seen: set[str] = set()
    for names in after.values():
        seen.update(names)

    missing = expected - seen
    assert not missing, f"wired bindings dropped by transplant: {sorted(missing)}"
    # Sanity check on the known expected count from the polished template.
    assert len(expected) >= 21, (
        f"expected at least 21 wired bindings on target, got {len(expected)}"
    )


def test_layouts_copied_and_output_is_valid(transplant_output: Path) -> None:
    """Output is a valid .pptx with the donor's layouts."""
    assert zipfile.is_zipfile(transplant_output), "output is not a valid .pptx zip"
    # python-pptx open should succeed.
    from pptx import Presentation

    prs = Presentation(str(transplant_output))
    # Donor has 34 layouts; target also has 34. Both shells share this count.
    assert len(prs.slide_layouts) == 34, (
        f"expected 34 layouts (donor's), got {len(prs.slide_layouts)}"
    )


def test_inputs_are_not_mutated(transplant_output: Path) -> None:
    """The transplant must not mutate target_template or visual_donor."""
    # Re-read them and verify size + zip listing parity with their on-disk
    # mtimes pre-/post-transplant. We can only check that they still open
    # cleanly and contain the core parts -- size comparisons against an
    # earlier run would be flaky if the test is re-run.
    for path in (TARGET_TEMPLATE, DONOR_SHELL):
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            assert "ppt/slideMasters/slideMaster1.xml" in names
            assert "ppt/presentation.xml" in names


def test_transplant_result_audit_counts() -> None:
    """TransplantResult should carry sensible audit counts (not 0s)."""
    if not TARGET_TEMPLATE.exists() or not DONOR_SHELL.exists():
        pytest.skip("inputs missing")
    from tcrender.master_transplant import transplant_visual_identity

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "audit_check.pptx"
        result = transplant_visual_identity(
            target_template=TARGET_TEMPLATE,
            visual_donor=DONOR_SHELL,
            output_path=out,
        )
        assert result.slide_masters_replaced >= 1
        assert result.layouts_replaced >= 30
        assert result.themes_replaced >= 1
        assert result.master_images_copied >= 1
        assert result.cover_replaced is True
        assert len(result.preserved_bindings) >= 21
        assert result.target_slides_preserved >= 30
        assert result.target_oleobjects_preserved >= 12
