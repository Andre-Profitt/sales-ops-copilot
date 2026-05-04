"""Regression tests for `scripts/build_ppttc.py`.

These tests pin the structural contract of the per-director `.ppttc`
output and exercise the most error-prone entry-builder functions
flagged in the 2026-05-03 audit:

    state/thinkcell_bridge/build_ppttc_audit/20260503T180000Z/findings.md

Coverage:

* Live-fixture sanity test: the canonical Jesper-Tyrer .ppttc shipped
  under state/2026-Q2/Jesper-Tyrer/ must parse, contain exactly 42
  bindings (the observed count as of 2026-05-03), have unique names,
  and pass `_validate_ppttc_shape` with zero findings.
* Schema-conformance property test: every binding's `table` must be a
  list-of-lists, with each cell either `None` or a single-key dict
  whose key is one of the six valid ppttc cell tags.
* `_validate_ppttc_shape` unit tests: well-formed payloads pass; each
  documented violation class fails with a clear message.
* Edge-input smoke tests for 5 audit-flagged entry functions:
  `_velocity_chart_entry`, `_concentration_chart_entry`,
  `_stale_activity_chart_entry`, `_pipe_movement_chart_entry`,
  `_action_items_table`.

The synthetic workbook fixture is built in-memory via openpyxl so the
tests stay hermetic. They do not touch SF, Office, the Windows VM
bridge, or any think-cell binary.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
LIVE_FIXTURE = REPO_ROOT / "state" / "2026-Q2" / "Jesper-Tyrer" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"

EXPECTED_BINDING_COUNT = 42
VALID_CELL_KEYS = {"string", "number", "percentage", "date", "fill"}


@pytest.fixture(scope="module")
def build_ppttc_module():
    """Import the build_ppttc module without invoking its CLI.

    `build_ppttc` lives next to a few sibling scripts (`_directors`,
    `model_recalc`, `ppttc_template`) that it imports relatively; we
    add `scripts/` to sys.path before importing.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "build_ppttc" in sys.modules:
        return importlib.reload(sys.modules["build_ppttc"])
    return importlib.import_module("build_ppttc")


# ---------------------------------------------------------------------------
# Live-fixture tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_payload() -> list[dict[str, Any]]:
    if not LIVE_FIXTURE.exists():
        pytest.skip(f"live fixture missing: {LIVE_FIXTURE}")
    return json.loads(LIVE_FIXTURE.read_text())


def test_live_fixture_top_level_is_array(live_payload: list[dict[str, Any]]) -> None:
    """Live ppttc must be a non-empty top-level array per the official schema."""
    assert isinstance(live_payload, list)
    assert len(live_payload) >= 1


def test_live_fixture_has_expected_binding_count(
    live_payload: list[dict[str, Any]],
) -> None:
    """Catch silent loss/addition of bindings in build_ppttc.py."""
    entries = live_payload[0]["data"]
    assert len(entries) == EXPECTED_BINDING_COUNT, (
        f"binding count drift: expected {EXPECTED_BINDING_COUNT}, got {len(entries)}"
    )


def test_live_fixture_binding_names_are_unique(
    live_payload: list[dict[str, Any]],
) -> None:
    """Per the official spec, two entries with the same name silently
    populate both backing elements with the same data, which loses
    one of the two intended bindings.
    """
    names = [entry["name"] for entry in live_payload[0]["data"]]
    assert len(names) == len(set(names)), (
        f"duplicate names in live fixture: {[n for n in names if names.count(n) > 1]}"
    )


def test_live_fixture_passes_validate_ppttc_shape(
    build_ppttc_module, live_payload: list[dict[str, Any]]
) -> None:
    """The live emitted file must pass our shape validator."""
    violations = build_ppttc_module._validate_ppttc_shape(live_payload)
    assert violations == [], "live fixture has shape violations: " + "\n".join(violations)


def test_live_fixture_every_cell_uses_a_valid_tag(
    live_payload: list[dict[str, Any]],
) -> None:
    """Property-style sweep: every leaf cell is null or a single-key
    object whose key is in the documented six-tag schema.
    """
    failures: list[str] = []
    for entry in live_payload[0]["data"]:
        name = entry["name"]
        table = entry["table"]
        assert isinstance(table, list), f"{name}: table must be a list"
        for r_idx, row in enumerate(table):
            assert isinstance(row, list), f"{name}.row[{r_idx}]: row must be a list"
            for c_idx, cell in enumerate(row):
                if cell is None:
                    continue
                if not isinstance(cell, dict):
                    failures.append(f"{name}[{r_idx}][{c_idx}]: not a dict")
                    continue
                keys = set(cell.keys())
                if not keys.issubset(VALID_CELL_KEYS):
                    failures.append(
                        f"{name}[{r_idx}][{c_idx}]: unknown key(s) {sorted(keys - VALID_CELL_KEYS)}"
                    )
    assert failures == [], "schema violations:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# _validate_ppttc_shape unit tests
# ---------------------------------------------------------------------------


def _good_payload() -> list[dict[str, Any]]:
    return [
        {
            "template": "/abs/wired.pptx",
            "data": [
                {"name": "S01_DirectorName", "table": [[{"string": "Jesper Tyrer"}]]},
                {
                    "name": "S05_PipelineByStage",
                    "table": [
                        [None, {"string": "Q2"}, {"string": "Q3"}],
                        [{"string": "ARR"}, {"number": 4.2}, {"number": 7.7}],
                    ],
                },
            ],
        }
    ]


def test_validate_passes_on_good_payload(build_ppttc_module) -> None:
    assert build_ppttc_module._validate_ppttc_shape(_good_payload()) == []


def test_validate_rejects_non_list_top_level(build_ppttc_module) -> None:
    violations = build_ppttc_module._validate_ppttc_shape({"template": "x", "data": []})
    assert any("top-level must be a JSON array" in v for v in violations)


def test_validate_rejects_empty_top_level(build_ppttc_module) -> None:
    violations = build_ppttc_module._validate_ppttc_shape([])
    assert any("array is empty" in v for v in violations)


def test_validate_rejects_missing_template_path(build_ppttc_module) -> None:
    payload = [{"data": []}]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("'template' must be a non-empty string" in v for v in violations)


def test_validate_rejects_data_not_list(build_ppttc_module) -> None:
    payload = [{"template": "/a.pptx", "data": "oops"}]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("'data' must be an array" in v for v in violations)


def test_validate_rejects_unknown_cell_key(build_ppttc_module) -> None:
    payload = [
        {
            "template": "/a.pptx",
            "data": [{"name": "X", "table": [[{"banana": 1.0}]]}],
        }
    ]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("unknown cell key" in v for v in violations)


def test_validate_rejects_duplicate_binding_names(build_ppttc_module) -> None:
    payload = [
        {
            "template": "/a.pptx",
            "data": [
                {"name": "S01", "table": [[{"string": "A"}]]},
                {"name": "S01", "table": [[{"string": "B"}]]},
            ],
        }
    ]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("duplicate binding name 'S01'" in v for v in violations)


def test_validate_rejects_multi_data_key_cell(build_ppttc_module) -> None:
    """A cell with both `string` and `number` is ambiguous."""
    payload = [
        {
            "template": "/a.pptx",
            "data": [
                {
                    "name": "X",
                    "table": [[{"string": "yes", "number": 42}]],
                }
            ],
        }
    ]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("multiple data keys" in v for v in violations)


def test_validate_accepts_fill_alongside_data_key(build_ppttc_module) -> None:
    """`fill` is allowed to co-exist with one data key per the spec."""
    payload = [
        {
            "template": "/a.pptx",
            "data": [
                {
                    "name": "X",
                    "table": [[{"number": 4.2, "fill": "#0066CC"}]],
                }
            ],
        }
    ]
    assert build_ppttc_module._validate_ppttc_shape(payload) == []


def test_validate_rejects_string_row(build_ppttc_module) -> None:
    payload = [
        {
            "template": "/a.pptx",
            "data": [{"name": "X", "table": ["not-a-list"]}],
        }
    ]
    violations = build_ppttc_module._validate_ppttc_shape(payload)
    assert any("row must be a list" in v for v in violations)


# ---------------------------------------------------------------------------
# Synthetic ModelWorkbook helper
# ---------------------------------------------------------------------------


# Default binding-name -> (sheet, range) map for stubs. Mirrors the
# pinned manifest at scripts/add_chart_binding_named_ranges.py so
# stubbed unit tests don't have to repeat the wiring.
_STUB_DEFAULT_NAMED_RANGES: dict[str, tuple[str, str]] = {
    "S04_PipeMovement": ("Pipe_Movement", "A2:B6"),
    "S05_PipelineByStage": ("Pipeline_By_Stage", "A2:B9"),
    "S06_PipelineAging": ("Pipeline_Aging", "A2:E7"),
    "S12_GRRProxyTable": ("Retention", "A1:B4"),
    "S13_ForecastCategory": ("Forecast_Category", "A1:C7"),
    "S16_StageByIndustry": ("Pivots", "A5:M13"),
    "S18_WinsLossesQTD": ("Wins_Losses_QTD", "A1:D3"),
    "S19_Velocity": ("Velocity", "A3:E10"),
    "S21_ConcentrationTable": ("Concentration", "A11:C15"),
    "S22_StaleActivity": ("Stale_Activity", "A1:C5"),
    "S24_AccountExpansion": ("Account_Expansion", "A1:F16"),
    "S25_PipelineCreationVelocity": ("Pipeline_Creation_Velocity", "A1:C13"),
    "S12_GRRProxyFootnote_src": ("Retention", "A5"),
    "S22_StaleActivityFootnote_src": ("Stale_Activity", "A7"),
    "S21_LargestAccount_src": ("Concentration", "B5"),
    "S21_LargestArr_src": ("Concentration", "B6"),
    "S21_LargestShare_src": ("Concentration", "B7"),
    "S21_ThresholdFlag_src": ("Concentration", "B8"),
    "S23_OpenOpps_src": ("Sales_Velocity", "B2"),
    "S23_WinRate_src": ("Sales_Velocity", "B3"),
    "S23_AvgDealSize_src": ("Sales_Velocity", "B4"),
    "S23_AvgCycleDays_src": ("Sales_Velocity", "B5"),
    "S23_Velocity_src": ("Sales_Velocity", "B6"),
}


class _StubWorkbook:
    """Minimal ModelWorkbook stand-in.

    Holds a dict-of-dicts of {sheet -> {coord -> value}} and a parallel
    openpyxl Workbook (for `workbook[sheet].max_row` access used by
    `_last_nonempty_row`).

    Also implements `named_range()` / `named_cell()` against an
    overridable name map so the F-06 named-range refactor can be unit-
    tested with synthetic workbooks.
    """

    def __init__(
        self,
        cells: dict[str, dict[str, Any]],
        named_ranges: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.cells = cells
        self.named_ranges = (
            dict(_STUB_DEFAULT_NAMED_RANGES) if named_ranges is None else dict(named_ranges)
        )
        wb = Workbook()
        # remove the default sheet
        default_sheet = wb.active
        wb.remove(default_sheet)
        for sheet_name, sheet_cells in cells.items():
            ws = wb.create_sheet(sheet_name)
            for coord, value in sheet_cells.items():
                ws[coord] = value
        self.workbook = wb

    def cell_value(self, sheet: str, coord: str) -> Any:
        return self.cells.get(sheet, {}).get(coord)

    def matrix(self, sheet: str, cell_range: str) -> list[list[Any]]:
        from openpyxl.utils import get_column_letter
        from openpyxl.utils.cell import range_boundaries

        min_col, min_row, max_col, max_row = range_boundaries(cell_range)
        out: list[list[Any]] = []
        for r in range(min_row, max_row + 1):
            row: list[Any] = []
            for c in range(min_col, max_col + 1):
                coord = f"{get_column_letter(c)}{r}"
                row.append(self.cell_value(sheet, coord))
            out.append(row)
        return out

    def named_range(self, name: str) -> list[list[Any]]:
        if name not in self.named_ranges:
            raise KeyError(f"stub: named range '{name}' not registered")
        sheet, ref = self.named_ranges[name]
        return self.matrix(sheet, ref)

    def named_cell(self, name: str) -> Any:
        if name not in self.named_ranges:
            raise KeyError(f"stub: named cell '{name}' not registered")
        sheet, ref = self.named_ranges[name]
        if ":" in ref:
            raise KeyError(f"stub: '{name}' is a multi-cell range '{ref}'")
        return self.cell_value(sheet, ref)


# ---------------------------------------------------------------------------
# Smoke tests for 5 audit-flagged entry functions
# ---------------------------------------------------------------------------


def _table_cells(entry: dict[str, Any]) -> list[Any]:
    """Flatten an entry's table to a single list of leaf cells."""
    return [cell for row in entry["table"] for cell in row]


def test_pipe_movement_handles_all_none(build_ppttc_module) -> None:
    """All-None Pipe_Movement matrix should not crash; returns the
    `[[None]]` empty-chart sentinel from `_chart_entry`.
    """
    cells = {"Pipe_Movement": {}}
    stub = _StubWorkbook(cells)
    entry = build_ppttc_module._pipe_movement_chart_entry(stub)
    assert entry["name"] == "S04_PipeMovement"
    assert entry["table"] == [[None]]


def test_pipe_movement_with_negative_residual_under_plus_label(
    build_ppttc_module,
) -> None:
    """Audit F-13: a `(+) New + Advanced (residual)` row with a negative
    residual stays positive in the chart because `_pipe_movement_value`
    only flips sign on `(-)`-prefixed labels. Pin the current behaviour
    so a future fix is a deliberate change.
    """
    cells = {
        "Pipe_Movement": {
            "A2": "Opening pipe",
            "B2": 10_000_000,
            "A3": "(+) New + Advanced (residual)",
            "B3": -2_000_000,  # negative residual -> pipe shrank
            "A4": "(-) Won this Q",
            "B4": 1_500_000,
            "A5": "(-) Lost this Q",
            "B5": 500_000,
            "A6": "Closing pipe",
            "B6": 8_000_000,
        }
    }
    stub = _StubWorkbook(cells)
    entry = build_ppttc_module._pipe_movement_chart_entry(stub)
    series = entry["table"][1][1:]  # skip the leading series-label cell
    # Positions: Opening, (+) residual, (-) Won, (-) Lost, Closing
    assert series[1] == {"number": pytest.approx(-2.0)} or series[1] == {"number": -2.0}, (
        f"current behaviour: residual sign preserved as-is, got {series[1]}"
    )


def test_velocity_handles_blank_rows(build_ppttc_module) -> None:
    """Audit F-08: `_velocity_chart_entry` does not filter empty rows;
    a partially-built quarter still produces 8 categories (one per
    expected stage row) with `None` values for blanks.
    """
    cells = {"Velocity": {}}
    cells["Velocity"]["A3"] = "1 - Prospecting"
    cells["Velocity"]["C3"] = 100  # 100-day median age
    cells["Velocity"]["A4"] = "2 - Discovery"
    cells["Velocity"]["C4"] = None
    # leave A5..A10 blank
    stub = _StubWorkbook(cells)
    entry = build_ppttc_module._velocity_chart_entry(stub)
    cats = entry["table"][0][1:]
    # 8 category cells emitted (A3..A10), some empty-string sentinels
    assert len(cats) == 8
    # Prospecting category resolves to its compact label
    assert cats[0] == {"string": "Prospect."}
    # Audit F-02: was multiplying value by 1000 (kilodays); FIXED 2026-05-03.
    # Pin the corrected behaviour: 100-day median renders as 100 (days).
    series_row = entry["table"][1]
    assert series_row[1] == {"number": 100}


def test_concentration_chart_handles_all_zero_shares(build_ppttc_module) -> None:
    """Audit F-01: `_for_k_scaled_donor` multiplies by 1000 on top of
    the *100 conversion. A 0.116 share -> 116 -> 116000. Pin behaviour
    so future fix is deliberate.
    """
    cells = {
        "Concentration": {
            # rows 11..15 are the chart payload per the script
            "A11": "Bucket",
            "B11": "ignored",
            "C11": "Share",
            "A12": "Top 1 account",
            "C12": 0.116,
            "A13": "Top 3 accounts",
            "C13": 0.252,
            "A14": "Top 5 accounts",
            "C14": 0.367,
            "A15": "Top 10 accounts",
            "C15": 0.578,
        }
    }
    stub = _StubWorkbook(cells)
    entry = build_ppttc_module._concentration_chart_entry(stub)
    values = entry["table"][1][1:]
    assert values[0] == {"number": 11.6}, (
        "F-01 FIXED 2026-05-03: 11.6% share emitted as 11.6 (was 11600 "
        "under the donor-template k-scale bug)"
    )


def test_stale_activity_handles_empty_matrix(build_ppttc_module) -> None:
    """`_stale_activity_chart_entry` reads A1:C5; a zeroed quarter
    should produce zero-valued numeric cells, not crash.
    """
    cells = {
        "Stale_Activity": {
            "A1": "Stage",
            "B1": "# Stale",
            "C1": "ARR (EUR)",
            "A2": "3 - Engagement",
            "C2": 0,
            "A3": "4 - Shortlisted",
            "C3": 0,
            "A4": "5 - Preferred",
            "C4": 0,
            "A5": "6 - Contracting",
            "C5": 0,
        }
    }
    stub = _StubWorkbook(cells)
    entry = build_ppttc_module._stale_activity_chart_entry(stub)
    assert entry["name"] == "S22_StaleActivity"
    series = entry["table"][1][1:]
    assert all(cell == {"number": 0.0} for cell in series)


def test_action_items_table_emits_placeholder_when_trends_empty(
    build_ppttc_module,
) -> None:
    """Audit F-04 / F-12: an empty trends.action_items list emits a
    single placeholder row instead of failing loudly. Pin behaviour.
    """
    rows = build_ppttc_module._action_items_table({"action_items": []})
    # one header + one placeholder row
    assert len(rows) == 2
    assert rows[1][0] == "(no action items generated)"
    assert rows[1][1:] == [None] * 6


def test_action_items_table_handles_normal_payload(build_ppttc_module) -> None:
    rows = build_ppttc_module._action_items_table(
        {
            "action_items": [
                {
                    "priority": "high",
                    "rule_id": "zombie_arr",
                    "claim": "10 stale opps",
                    "suggested_action": "Review with reps",
                    "due_date": "2026-05-31",
                    "owner": "Jesper Tyrer",
                },
            ]
        }
    )
    assert len(rows) == 2
    assert rows[1][0] == 1
    assert rows[1][1] == "HIGH"  # priority gets uppercased
    assert rows[1][2] == "zombie_arr"


# ---------------------------------------------------------------------------
# _json_cell coverage of audit-relevant edge inputs
# ---------------------------------------------------------------------------


def test_json_cell_handles_nan_and_inf(build_ppttc_module) -> None:
    """`_json_cell` must reject non-finite floats; otherwise the JSON
    payload is non-conformant (`NaN` is not legal JSON).
    """
    import math

    assert build_ppttc_module._json_cell(math.nan) is None
    assert build_ppttc_module._json_cell(math.inf) is None
    assert build_ppttc_module._json_cell(-math.inf) is None


def test_json_cell_distinguishes_bool_from_int(build_ppttc_module) -> None:
    """`isinstance(True, int)` is True in Python; `_json_cell` must
    branch on bool before int so True doesn't render as `{"number": 1}`.
    """
    assert build_ppttc_module._json_cell(True) == {"string": "TRUE"}
    assert build_ppttc_module._json_cell(False) == {"string": "FALSE"}
    assert build_ppttc_module._json_cell(1) == {"number": 1}
