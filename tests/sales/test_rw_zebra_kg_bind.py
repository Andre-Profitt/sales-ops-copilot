"""Tests for scripts.sales.rw_zebra_kg_bind — RW binding overlay."""

from __future__ import annotations

from scripts.sales import rw_zebra_kg_bind as bd


SAMPLE_DOC = """
## Exact elements to pull

### 1. Stage Hygiene - Zebra BI Tables proof

Source: `sales-funnel-power-bi-template`, pages `Home 3`.

RW element:

- `Stage x Motion Hygiene` table with embedded bars and variance notation.

Bindings:

- Category: `f_stage_transition[from_stage_name]`
- Values:
  - `Stage Forward Pct (LE)`
  - `Stage Backward Pct (LE)`

### 2. VP Ops Scorecard - exception table, not RAG cards

Source: `sales-dashboard-power-bi-template`, page `Landing`.

RW element:

- VP Ops Scorecard top exception table.

Bindings:

- Values:
  - `ARR FQTD`
"""


def test_parse_extracts_sections_with_source_template_and_values():
    sections = bd.parse_element_map(SAMPLE_DOC)
    assert len(sections) == 2

    s1 = sections[0]
    assert s1.rw_tab == "Stage Hygiene"
    assert s1.rw_element == "Stage x Motion Hygiene"
    assert s1.source_template == "sales-funnel-power-bi-template"
    assert "Stage Forward Pct (LE)" in s1.rw_values
    assert "Stage Backward Pct (LE)" in s1.rw_values


def test_classify_status_marks_bound_when_measure_exists():
    rw_model = {"f_stage_transition": ["Stage Forward Pct (LE)"]}
    status = bd.classify_status("Stage Forward Pct (LE)", rw_model)
    assert status == "bound"


def test_classify_status_marks_needs_measure_when_absent():
    rw_model = {"f_opp": ["ARR FQTD"]}
    status = bd.classify_status("Stage Forward Pct (LE)", rw_model)
    assert status == "needs_measure"


def test_emit_bindings_yields_one_per_value():
    rw_model = {"f_stage_transition": ["Stage Forward Pct (LE)"]}
    sections = bd.parse_element_map(SAMPLE_DOC)
    rows = list(bd.emit_bindings(sections, rw_model))

    # 2 from section 1 + 1 from section 2 = 3 bindings
    assert len(rows) == 3
    statuses = {r["status"] for r in rows}
    assert "bound" in statuses
    assert "needs_measure" in statuses
    assert all(r["type"] == "RWBinding" for r in rows)
