"""Regression tests for the F-06 chart-binding named-range refactor.

Pins three contracts:

1. Every binding in the migration manifest's `named_range_safe=true`
   subset is present as a workbook-scoped defined name in each of the
   four production director Excel models.

2. ``ModelWorkbook.named_range()`` and ``ModelWorkbook.named_cell()``
   resolve correctly against the live Jesper-Tyrer workbook and return
   the same payload as the equivalent positional ``matrix()`` /
   ``cell_value()`` calls.

3. Re-running the migration is idempotent -- a second invocation must
   not duplicate names or otherwise mutate the workbook beyond what the
   first run produced.

The .ppttc byte-identity contract (data flowing through the named-range
read must produce a byte-identical .ppttc file vs the pre-refactor
positional code path) is asserted against the baseline captured in
``state/thinkcell_bridge/excel_named_ranges/_baselines/<slug>.ppttc``.
The baselines are tracked in git so any future drift surfaces as a
test failure.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BASELINES_DIR = REPO_ROOT / "state" / "thinkcell_bridge" / "excel_named_ranges" / "_baselines"
DIRECTOR_SLUGS = ("Jesper-Tyrer", "Sarah-Pittroff", "Patrick-Gaughan", "Megan-Miceli")
PERIOD = "2026-Q2"


@pytest.fixture(scope="module")
def add_named_ranges_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "add_chart_binding_named_ranges" in sys.modules:
        return importlib.reload(sys.modules["add_chart_binding_named_ranges"])
    return importlib.import_module("add_chart_binding_named_ranges")


@pytest.fixture(scope="module")
def build_ppttc_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "build_ppttc" in sys.modules:
        return importlib.reload(sys.modules["build_ppttc"])
    return importlib.import_module("build_ppttc")


def _xlsx_path(slug: str) -> Path:
    return REPO_ROOT / "state" / PERIOD / slug / "land.model.xlsx"


def _safe_binding_names(add_named_ranges_module) -> list[str]:
    return [
        b["name"]
        for b in add_named_ranges_module._BINDING_TO_RANGE_MANIFEST
        if b["named_range_safe"]
    ]


# ---------------------------------------------------------------------------
# Contract 1 -- migration is present on every director
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", DIRECTOR_SLUGS)
def test_director_xlsx_has_all_safe_named_ranges(add_named_ranges_module, slug: str) -> None:
    xlsx = _xlsx_path(slug)
    if not xlsx.exists():
        pytest.skip(f"missing fixture: {xlsx}")
    wb = load_workbook(xlsx)
    actual = set(wb.defined_names)
    expected = set(_safe_binding_names(add_named_ranges_module))
    missing = expected - actual
    assert not missing, (
        f"{slug} land.model.xlsx is missing chart-binding named ranges: "
        f"{sorted(missing)}. Re-run scripts/add_chart_binding_named_ranges.py."
    )


@pytest.mark.parametrize("slug", DIRECTOR_SLUGS)
def test_director_xlsx_preserves_existing_data_named_ranges(slug: str) -> None:
    """The 56 pre-existing data-source named ranges (Data_*, ClosedCFQ_*,
    Renewals12mo_*, Parameters!*) must remain untouched.
    """
    xlsx = _xlsx_path(slug)
    if not xlsx.exists():
        pytest.skip(f"missing fixture: {xlsx}")
    wb = load_workbook(xlsx)
    expected_prefixes = (
        "Data_",
        "ClosedCFQ_",
        "ClosedWon6mo_",
        "Renewals12mo_",
    )
    expected_singletons = {
        "period_start",
        "period_end",
        "today",
        "zombie_age_days",
        "activity_drought_days",
        "late_stage_floor_pct",
        "simcorp_one_floor_pct",
        "commercial_approval_eur",
        "eur_to_meur",
    }
    have = set(wb.defined_names)
    for name in expected_singletons:
        assert name in have, f"{slug}: pre-existing Parameters name '{name}' was lost"
    for prefix in expected_prefixes:
        prefixed = [n for n in have if n.startswith(prefix)]
        assert prefixed, f"{slug}: pre-existing '{prefix}*' names lost"


# ---------------------------------------------------------------------------
# Contract 2 -- named_range / named_cell resolve correctly
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def jesper_model(build_ppttc_module):
    xlsx = _xlsx_path("Jesper-Tyrer")
    if not xlsx.exists():
        pytest.skip(f"missing fixture: {xlsx}")
    return build_ppttc_module.ModelWorkbook(xlsx)


def test_named_range_matches_positional_matrix_for_S16(jesper_model) -> None:
    by_name = jesper_model.named_range("S16_StageByIndustry")
    by_pos = jesper_model.matrix("Pivots", "A5:M13")
    assert by_name == by_pos
    assert len(by_name) == 9  # 1 header row + 8 stages
    assert len(by_name[0]) == 13  # stage label + 12 industries


def test_named_range_matches_positional_matrix_for_S05(jesper_model) -> None:
    by_name = jesper_model.named_range("S05_PipelineByStage")
    by_pos = jesper_model.matrix("Pipeline_By_Stage", "A2:B9")
    assert by_name == by_pos


def test_named_cell_matches_positional_cell_value(jesper_model) -> None:
    cases = [
        ("S22_StaleActivityFootnote_src", "Stale_Activity", "A7"),
        ("S12_GRRProxyFootnote_src", "Retention", "A5"),
        ("S21_LargestAccount_src", "Concentration", "B5"),
        ("S21_LargestArr_src", "Concentration", "B6"),
        ("S21_LargestShare_src", "Concentration", "B7"),
        ("S23_OpenOpps_src", "Sales_Velocity", "B2"),
        ("S23_WinRate_src", "Sales_Velocity", "B3"),
        ("S23_AvgDealSize_src", "Sales_Velocity", "B4"),
        ("S23_AvgCycleDays_src", "Sales_Velocity", "B5"),
        ("S23_Velocity_src", "Sales_Velocity", "B6"),
    ]
    for name, sheet, ref in cases:
        assert jesper_model.named_cell(name) == jesper_model.cell_value(sheet, ref), (
            f"named_cell('{name}') != cell_value('{sheet}', '{ref}')"
        )


def test_named_range_raises_on_missing_name(build_ppttc_module, jesper_model) -> None:
    with pytest.raises(build_ppttc_module.NamedRangeError):
        jesper_model.named_range("does_not_exist_anywhere")


def test_named_cell_rejects_multi_cell_range(build_ppttc_module, jesper_model) -> None:
    with pytest.raises(build_ppttc_module.NamedRangeError):
        # S16 is a 9x13 range, not a single cell.
        jesper_model.named_cell("S16_StageByIndustry")


# ---------------------------------------------------------------------------
# Contract 3 -- migration is idempotent
# ---------------------------------------------------------------------------


def test_add_named_ranges_is_idempotent(tmp_path: Path, add_named_ranges_module) -> None:
    """Run the migration twice on a copy of Jesper's xlsx; the workbook
    contents and defined-name count must be identical after run #2.
    """
    src = _xlsx_path("Jesper-Tyrer")
    if not src.exists():
        pytest.skip(f"missing fixture: {src}")
    work = tmp_path / "land.model.xlsx"
    shutil.copy2(src, work)

    safe = [b for b in add_named_ranges_module._BINDING_TO_RANGE_MANIFEST if b["named_range_safe"]]

    report1 = add_named_ranges_module.add_named_ranges(work, safe)
    digest_after_first = hashlib.sha256(work.read_bytes()).hexdigest()

    report2 = add_named_ranges_module.add_named_ranges(work, safe)
    digest_after_second = hashlib.sha256(work.read_bytes()).hexdigest()

    # Run #2 must add zero new names; all should be reported as skipped.
    assert report2["added_count"] == 0, (
        f"second run should be a no-op, but added: {report2['added']}"
    )
    assert report2["skipped_count"] == report1["added_count"] + report1["skipped_count"]

    # Bytes are identical (the second run never opened the workbook for write
    # because there was nothing to add).
    assert digest_after_first == digest_after_second


# ---------------------------------------------------------------------------
# Contract 4 -- .ppttc output is byte-identical to pre-refactor baseline
# ---------------------------------------------------------------------------


def _has_baseline(slug: str) -> bool:
    return (BASELINES_DIR / f"{slug}.ppttc.sha256").exists()


@pytest.mark.parametrize("slug", DIRECTOR_SLUGS)
def test_ppttc_byte_identity_against_pre_refactor_baseline(slug: str) -> None:
    """The .ppttc generated post-refactor must hash-match the pre-
    refactor baseline. The baseline files in
    ``state/thinkcell_bridge/excel_named_ranges/_baselines/`` were
    captured before refactoring build_ppttc.py to read named ranges.
    """
    if not _has_baseline(slug):
        pytest.skip(f"no baseline pinned for {slug}")
    expected = (BASELINES_DIR / f"{slug}.ppttc.sha256").read_text().strip().split()[0]
    current_path = REPO_ROOT / "state" / PERIOD / slug / f"{slug}-LAND-{PERIOD}.ppttc"
    if not current_path.exists():
        pytest.skip(f"current .ppttc not built for {slug}")
    actual = hashlib.sha256(current_path.read_bytes()).hexdigest()
    assert actual == expected, (
        f"{slug} .ppttc drifted from pre-refactor baseline.\n"
        f"  expected (pre-refactor): {expected}\n"
        f"  actual   (post-refactor): {actual}\n"
        "If the drift is intentional (not a regression), regenerate the\n"
        "baseline file with the updated hash."
    )


def test_jesper_ppttc_payload_round_trip(build_ppttc_module) -> None:
    """End-to-end smoke: generate Jesper's entries via the refactored
    code path, validate the ppttc shape, and confirm S16 + S05 + S04
    bindings are present in the output (i.e. the refactor didn't
    silently drop any of them).
    """
    xlsx = _xlsx_path("Jesper-Tyrer")
    legacy = REPO_ROOT / "state" / PERIOD / "Jesper-Tyrer" / "land.xlsx"
    trends = REPO_ROOT / "state" / PERIOD / "Jesper-Tyrer" / "trends.json"
    brief = REPO_ROOT / "state" / PERIOD / "Jesper-Tyrer" / "brief.md"
    if not all(p.exists() for p in (xlsx, legacy, trends, brief)):
        pytest.skip("Jesper fixtures incomplete")

    artifacts = build_ppttc_module.DirectorArtifacts(
        name="Jesper Tyrer",
        scope_label="APAC",
        slug="Jesper-Tyrer",
        period=PERIOD,
        director_dir=xlsx.parent,
        model_path=xlsx,
        legacy_path=legacy,
        trends_path=trends,
        brief_path=brief,
    )

    model = build_ppttc_module.ModelWorkbook(xlsx)
    legacy_wb = build_ppttc_module.LiteralWorkbook(legacy)
    trends_data = json.loads(trends.read_text())
    brief_sections = build_ppttc_module._parse_markdown_sections(brief.read_text())

    entries = build_ppttc_module._ppttc_entries_from_context(
        artifacts,
        trends=trends_data,
        brief_sections=brief_sections,
        model=model,
        legacy=legacy_wb,
    )
    names = {e["name"] for e in entries}
    for name in (
        "S04_PipeMovement",
        "S05_PipelineByStage",
        "S06_PipelineAging",
        "S13_ForecastCategory",
        "S16_StageByIndustry",
        "S18_WinsLossesQTD",
        "S19_Velocity",
        "S21_ConcentrationTable",
        "S22_StaleActivity",
        "S24_AccountExpansion",
        "S25_PipelineCreationVelocity",
        "S12_GRRProxyTable",
    ):
        assert name in names, f"refactored pipeline dropped binding {name}"

    payload = [{"template": "/x.pptx", "data": entries}]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert violations == [], "refactored entries fail shape validation: " + "\n".join(violations)
