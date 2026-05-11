# RW Dashboard Redesign — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the test infrastructure, visual-builder primitives (tables, matrix, page management), and all new DAX measures required to compose the 5-tab redesigned RW VP Ops scorecard. Foundation only — tab composition lives in follow-up per-tab plans.

**Architecture:** Extract pure JSON builders from `rw_add_visual.py` into a tested `_pbir_helpers.py` module; extend with table + matrix + page-management primitives. Extend the model-bim DAX block in `rw_push_semantic_model.py` with backward-rate / time-in-stage / stall / risk-class / window-delta / S3-gate / Growth-Mix measures. All work shipped via existing Fabric REST + idempotent `updateDefinition` paths.

**Tech Stack:** Python 3.13, Fabric REST API, Power BI report.json schema, TMSL (model.bim), DAX, pytest, `azure-identity` (`AzureCliCredential`), DuckDB (existing OFH transform).

**Spec:** `docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md`

**Follow-up plans (out of scope here):** per-tab composition plans for What Changed · Forecast · Stage Hygiene · Renewals · Growth Mix. Each will use the primitives + measures shipped here and is one separate planning session.

---

## Phase 0 — Test infrastructure

### Task 1: Stand up tests/sales/

**Files:**

- Create: `tests/sales/__init__.py`
- Create: `tests/sales/conftest.py`
- Create: `tests/sales/fixtures/salesmanager_report.json` (copy from `/tmp/pbi_ref/`)

- [ ] **Step 1: Create empty package marker**

```bash
touch tests/sales/__init__.py
```

- [ ] **Step 2: Copy reference report fixture**

```bash
cp /tmp/pbi_ref/salesmanager_report.json tests/sales/fixtures/salesmanager_report.json
```

- [ ] **Step 3: Write conftest with fixtures**

```python
# tests/sales/conftest.py
"""Fixtures for tests/sales/. Pure data only — no network."""
from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def salesmanager_report() -> dict:
    """Reference report.json from a working PBI report (with table visuals)."""
    return json.loads((FIXTURES / "salesmanager_report.json").read_text())


@pytest.fixture
def empty_report() -> dict:
    """Minimal report.json shape — one empty section."""
    return {
        "config": "{}",
        "sections": [
            {
                "name": "ReportSection",
                "displayName": "Page 1",
                "filters": "[]",
                "visualContainers": [],
                "displayOption": 1,
                "height": 720,
                "width": 1280,
            }
        ],
        "resourcePackages": [],
    }
```

- [ ] **Step 4: Sanity test the fixtures load**

```python
# tests/sales/test_fixtures.py
def test_salesmanager_report_loads(salesmanager_report):
    assert "sections" in salesmanager_report
    assert isinstance(salesmanager_report["sections"], list)


def test_empty_report_shape(empty_report):
    assert len(empty_report["sections"]) == 1
    assert empty_report["sections"][0]["visualContainers"] == []
```

- [ ] **Step 5: Run and verify**

Run: `pytest tests/sales/ -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/sales/
git commit -m "test(track:rw): bootstrap tests/sales/ with PBI report fixtures"
```

---

## Phase 1 — Visual builder primitives

### Task 2: Extract pure JSON builders into `_pbir_helpers.py`

Move `build_card_visual` and `build_slicer_visual` out of `rw_add_visual.py` into a dependency-free helper module. This unblocks unit testing and creates the home for future builders.

**Files:**

- Create: `scripts/sales/_pbir_helpers.py`
- Modify: `scripts/sales/rw_add_visual.py:80-207` (delete the two functions, replace with import)
- Create: `tests/sales/test_pbir_helpers.py`

- [ ] **Step 1: Write failing test for `build_card_visual`**

```python
# tests/sales/test_pbir_helpers.py
import json

from scripts.sales._pbir_helpers import build_card_visual


def test_build_card_visual_basic_shape():
    vc = build_card_visual(
        measure_table="f_opportunity",
        measure_name="Total Closed Won ARR",
        display_title="Closed Won ARR",
        x=20, y=20, w=280, h=110,
    )
    assert vc["x"] == 20 and vc["y"] == 20
    assert vc["width"] == 280 and vc["height"] == 110
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "card"
    select = config["singleVisual"]["prototypeQuery"]["Select"][0]
    assert select["Measure"]["Property"] == "Total Closed Won ARR"
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/sales/test_pbir_helpers.py -v`
Expected: collection error (`No module named 'scripts.sales._pbir_helpers'`).

- [ ] **Step 3: Create `_pbir_helpers.py` with extracted code**

Copy these top-level imports + the two builders from `scripts/sales/rw_add_visual.py:80-207` verbatim into `scripts/sales/_pbir_helpers.py`. Header:

```python
"""Pure JSON builders for Power BI PBIR-Legacy report.json.

No network, no auth, no side effects. Functions return dict shapes
that get base64-encoded into report.json `visualContainers`."""

from __future__ import annotations

import json
import uuid
```

Then paste `build_card_visual(...)` (lines 80-140) and `build_slicer_visual(...)` (lines 143-207) — no edits to function bodies.

- [ ] **Step 4: Replace the functions in `rw_add_visual.py` with re-exports**

Edit `scripts/sales/rw_add_visual.py`:

- Delete the bodies of `build_card_visual` (lines 80-140) and `build_slicer_visual` (lines 143-207)
- Add to imports section near the top:

```python
from scripts.sales._pbir_helpers import (
    build_card_visual,
    build_slicer_visual,
)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/sales/ -v`
Expected: 3 passed (2 from Task 1 + 1 from this task).

- [ ] **Step 6: Smoke-test the CLI still works**

Run: `python3 -m scripts.sales.rw_add_visual --help`
Expected: argparse help prints, no import errors.

- [ ] **Step 7: Commit**

```bash
git add scripts/sales/_pbir_helpers.py scripts/sales/rw_add_visual.py tests/sales/test_pbir_helpers.py
git commit -m "refactor(track:rw): extract PBIR builders into _pbir_helpers.py"
```

---

### Task 3: Add `build_table_visual` to `_pbir_helpers.py`

A table visual = a list of measure/column projections rendered as rows. Used for: change detail (Tab 1), commit-risk (Tab 2), stall (Tab 3), renewal cohort (Tab 4).

**Files:**

- Modify: `scripts/sales/_pbir_helpers.py` (append new function)
- Modify: `tests/sales/test_pbir_helpers.py` (append test)

- [ ] **Step 1: Inspect a table visual in the reference fixture**

Run: `python3 -c "import json; r=json.load(open('tests/sales/fixtures/salesmanager_report.json')); [print(json.loads(v['config'])['singleVisual']['visualType']) for s in r['sections'] for v in s.get('visualContainers',[])]" | sort -u`
Expected: list of visualType values present (look for `tableEx` or `pivotTable`).

If `tableEx` is not present, run:

```bash
python3 -c "import json; r=json.load(open('tests/sales/fixtures/salesmanager_report.json')); [print(json.dumps(json.loads(v['config'])['singleVisual'], indent=2)) for s in r['sections'] for v in s.get('visualContainers',[]) if json.loads(v['config'])['singleVisual']['visualType']=='tableEx'][:1]"
```

Save the printed JSON for reference. **If no table is present in the fixture**, deploy a one-off probe table via the live PBI editor in browser, pull the report.json via `get_current_report_json`, and use that as reference.

- [ ] **Step 2: Write failing test**

```python
# append to tests/sales/test_pbir_helpers.py
from scripts.sales._pbir_helpers import build_table_visual


def test_build_table_visual_columns():
    vc = build_table_visual(
        name="commit_risk_table",
        columns=[
            {"table": "f_opportunity", "field": "opp_name", "kind": "column", "title": "Opp"},
            {"table": "f_opportunity", "field": "owner_name", "kind": "column", "title": "Owner"},
            {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "kind": "measure", "title": "ARR"},
        ],
        x=20, y=400, w=900, h=240,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "tableEx"
    assert len(config["singleVisual"]["prototypeQuery"]["Select"]) == 3
    # First two are columns, third is a measure
    sel = config["singleVisual"]["prototypeQuery"]["Select"]
    assert "Column" in sel[0] and sel[0]["Column"]["Property"] == "opp_name"
    assert "Measure" in sel[2] and sel[2]["Measure"]["Property"] == "Total Open Pipeline ARR"
```

- [ ] **Step 3: Run — expect ImportError**

Run: `pytest tests/sales/test_pbir_helpers.py::test_build_table_visual_columns -v`
Expected: ImportError on `build_table_visual`.

- [ ] **Step 4: Implement**

Append to `scripts/sales/_pbir_helpers.py`:

```python
def build_table_visual(
    name: str,
    columns: list[dict],
    x: float,
    y: float,
    w: float = 900,
    h: float = 240,
) -> dict:
    """Construct a tableEx visualContainer.

    columns: list of {"table": str, "field": str, "kind": "column"|"measure", "title": str}.
    Order of columns in the list = display order in the table.
    """
    visual_name = uuid.uuid4().hex[:20]
    # One alias per distinct table referenced
    aliases: dict[str, str] = {}
    for c in columns:
        aliases.setdefault(c["table"], chr(ord("a") + len(aliases)))

    select = []
    projections = []
    column_props: dict[str, dict] = {}
    for c in columns:
        alias = aliases[c["table"]]
        query_ref = f"{c['table']}.{c['field']}"
        node_key = "Measure" if c["kind"] == "measure" else "Column"
        select.append(
            {
                node_key: {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": c["field"],
                },
                "Name": query_ref,
            }
        )
        projections.append({"queryRef": query_ref})
        column_props[query_ref] = {"displayName": c["title"]}

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 800, "width": w, "height": h, "tabOrder": 800},
            }
        ],
        "singleVisual": {
            "visualType": "tableEx",
            "projections": {"Values": projections},
            "prototypeQuery": {
                "Version": 2,
                "From": [
                    {"Name": alias, "Entity": tbl, "Type": 0}
                    for tbl, alias in aliases.items()
                ],
                "Select": select,
            },
            "columnProperties": column_props,
            "drillFilterOtherVisuals": True,
        },
    }
    return {
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 800,
    }
```

- [ ] **Step 5: Run test**

Run: `pytest tests/sales/test_pbir_helpers.py -v`
Expected: all pass.

- [ ] **Step 6: Live integration probe — deploy a one-off table**

Add a temporary `--probe-table` flag to `rw_add_visual.py` main() that builds a 3-column commit-risk table (opp_name, owner_name, Total Open Pipeline ARR) in the bottom-left of the current page, then pushes. Run it. Open the report URL. Verify the table renders with the right columns and data.

If schema is rejected, capture the error from `_wait_lro`, compare against the fixture's tableEx config, fix the builder, re-run.

- [ ] **Step 7: Remove the temporary probe flag (keep the builder)**

- [ ] **Step 8: Commit**

```bash
git add scripts/sales/_pbir_helpers.py tests/sales/test_pbir_helpers.py
git commit -m "feat(track:rw): add build_table_visual to PBIR helpers"
```

---

### Task 4: Add `build_matrix_visual` to `_pbir_helpers.py`

A matrix visual = pivoted table: rows × columns × values. Used for: stage × motion (Tab 2 hero), stage hygiene matrix (Tab 3 hero).

**Files:**

- Modify: `scripts/sales/_pbir_helpers.py`
- Modify: `tests/sales/test_pbir_helpers.py`

- [ ] **Step 1: Write failing test**

```python
# append to tests/sales/test_pbir_helpers.py
from scripts.sales._pbir_helpers import build_matrix_visual


def test_build_matrix_visual_axes():
    vc = build_matrix_visual(
        rows=[{"table": "f_opportunity", "field": "stage_name", "title": "Stage"}],
        columns=[{"table": "f_opportunity", "field": "motion_type", "title": "Motion"}],
        values=[
            {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "title": "Open ARR"},
            {"table": "f_opportunity", "field": "Total Closed Won ARR", "title": "Won ARR"},
        ],
        x=20, y=120, w=900, h=260,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "pivotTable"
    proj = config["singleVisual"]["projections"]
    assert "Rows" in proj and "Columns" in proj and "Values" in proj
    assert len(proj["Values"]) == 2
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/sales/test_pbir_helpers.py::test_build_matrix_visual_axes -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Append to `scripts/sales/_pbir_helpers.py`:

```python
def build_matrix_visual(
    rows: list[dict],
    columns: list[dict],
    values: list[dict],
    x: float,
    y: float,
    w: float = 900,
    h: float = 260,
) -> dict:
    """Construct a pivotTable (matrix) visualContainer.

    rows / columns: list of {"table": str, "field": str, "title": str} — column refs.
    values: list of {"table": str, "field": str, "title": str} — measure refs.
    """
    visual_name = uuid.uuid4().hex[:20]
    aliases: dict[str, str] = {}
    for c in rows + columns + values:
        aliases.setdefault(c["table"], chr(ord("a") + len(aliases)))

    def _col_node(c: dict) -> dict:
        alias = aliases[c["table"]]
        return {
            "Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": c["field"]},
            "Name": f"{c['table']}.{c['field']}",
        }

    def _measure_node(c: dict) -> dict:
        alias = aliases[c["table"]]
        return {
            "Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": c["field"]},
            "Name": f"{c['table']}.{c['field']}",
        }

    select = [_col_node(c) for c in rows] + [_col_node(c) for c in columns] + [_measure_node(v) for v in values]
    projections = {
        "Rows": [{"queryRef": f"{c['table']}.{c['field']}"} for c in rows],
        "Columns": [{"queryRef": f"{c['table']}.{c['field']}"} for c in columns],
        "Values": [{"queryRef": f"{v['table']}.{v['field']}"} for v in values],
    }
    column_props: dict[str, dict] = {}
    for c in rows + columns + values:
        column_props[f"{c['table']}.{c['field']}"] = {"displayName": c["title"]}

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 800, "width": w, "height": h, "tabOrder": 800},
            }
        ],
        "singleVisual": {
            "visualType": "pivotTable",
            "projections": projections,
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()],
                "Select": select,
            },
            "columnProperties": column_props,
            "drillFilterOtherVisuals": True,
        },
    }
    return {
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 800,
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/sales/ -v`
Expected: all pass.

- [ ] **Step 5: Live integration probe**

Add a temporary `--probe-matrix` flag that builds a Stage × Motion matrix (rows = stage_name, columns = motion_type, values = `Total Open Pipeline ARR` + `Total Closed Won ARR`) and pushes. Verify in browser. Capture and fix any schema rejections by comparing to a manually-built reference matrix in the live workspace.

- [ ] **Step 6: Remove temporary probe flag**

- [ ] **Step 7: Commit**

```bash
git add scripts/sales/_pbir_helpers.py tests/sales/test_pbir_helpers.py
git commit -m "feat(track:rw): add build_matrix_visual to PBIR helpers"
```

---

### Task 5: Page management primitives

Multi-tab redesign needs to add / remove / list / clear pages in `report.json`. Today only `--clear` exists (wipes visualContainers in section 0). We need `add_page`, `remove_page`, `ensure_pages`.

**Files:**

- Modify: `scripts/sales/_pbir_helpers.py`
- Modify: `tests/sales/test_pbir_helpers.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/sales/test_pbir_helpers.py
from scripts.sales._pbir_helpers import add_page, ensure_pages, remove_page


def test_add_page_appends_section(empty_report):
    add_page(empty_report, name="ReportSection2", display_name="Forecast")
    names = [s["name"] for s in empty_report["sections"]]
    assert "ReportSection2" in names
    new = [s for s in empty_report["sections"] if s["name"] == "ReportSection2"][0]
    assert new["displayName"] == "Forecast"
    assert new["visualContainers"] == []


def test_remove_page_drops_section(empty_report):
    add_page(empty_report, name="X", display_name="X")
    remove_page(empty_report, name="X")
    assert all(s["name"] != "X" for s in empty_report["sections"])


def test_ensure_pages_idempotent(empty_report):
    targets = [
        ("PageWhatChanged", "What Changed"),
        ("PageForecast", "Forecast"),
        ("PageStageHygiene", "Stage Hygiene"),
        ("PageRenewals", "Renewals"),
        ("PageGrowthMix", "Growth Mix"),
    ]
    ensure_pages(empty_report, targets)
    ensure_pages(empty_report, targets)  # second call is a no-op
    names = [s["name"] for s in empty_report["sections"]]
    for n, _ in targets:
        assert n in names
    # No duplicates
    assert len(names) == len(set(names))
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/sales/test_pbir_helpers.py -k page -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Append to `scripts/sales/_pbir_helpers.py`:

```python
def _new_section(name: str, display_name: str, ordinal: int) -> dict:
    return {
        "name": name,
        "displayName": display_name,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": [],
        "displayOption": 1,
        "height": 720,
        "width": 1280,
    }


def add_page(report: dict, name: str, display_name: str) -> dict:
    """Append a new page (section) to report. Returns the new section dict."""
    if any(s["name"] == name for s in report["sections"]):
        return next(s for s in report["sections"] if s["name"] == name)
    section = _new_section(name, display_name, ordinal=len(report["sections"]))
    report["sections"].append(section)
    return section


def remove_page(report: dict, name: str) -> None:
    """Remove a page (section) by name. No-op if not found."""
    report["sections"] = [s for s in report["sections"] if s["name"] != name]


def ensure_pages(report: dict, targets: list[tuple[str, str]]) -> None:
    """Idempotently ensure each (name, display_name) page exists.

    Existing pages are left untouched (visualContainers preserved).
    Missing pages are appended in the order given.
    """
    existing = {s["name"] for s in report["sections"]}
    for name, display in targets:
        if name not in existing:
            add_page(report, name, display)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/sales/ -v`
Expected: all pass.

- [ ] **Step 5: Add CLI integration in `rw_add_visual.py`**

In `main()`, add the argparse flag and handler:

```python
ap.add_argument(
    "--ensure-pages",
    action="store_true",
    help="Idempotently ensure the 5 redesign tabs exist in report.json",
)
# ...
if args.ensure_pages:
    from scripts.sales._pbir_helpers import ensure_pages
    ensure_pages(rj, [
        ("PageWhatChanged", "What Changed"),
        ("PageForecast", "Forecast"),
        ("PageStageHygiene", "Stage Hygiene"),
        ("PageRenewals", "Renewals"),
        ("PageGrowthMix", "Growth Mix"),
    ])
    print(f"  pages now: {[s['displayName'] for s in rj['sections']]}")
    push_report(token, rj)
    return
```

- [ ] **Step 6: Live integration**

Run: `python3 -m scripts.sales.rw_add_visual --ensure-pages`
Expected: stdout shows 5 page names. Open the report URL and verify 5 tabs appear at the bottom.

- [ ] **Step 7: Re-run to verify idempotency**

Run: `python3 -m scripts.sales.rw_add_visual --ensure-pages`
Expected: same 5 pages, no duplicates, no errors.

- [ ] **Step 8: Commit**

```bash
git add scripts/sales/_pbir_helpers.py scripts/sales/rw_add_visual.py tests/sales/test_pbir_helpers.py
git commit -m "feat(track:rw): add page management to PBIR helpers + --ensure-pages CLI"
```

---

## Phase 2 — DAX measure additions

All DAX additions land in `scripts/sales/rw_push_semantic_model.py`'s `build_model_bim()` function. Each task appends measure dicts to the same list at the same shape. Idempotent push via the existing `deploy()` flow.

**Verification:** DAX query API is tenant-disabled per `project_rw_dashboard_progress_2026-05-07.md`. Verification per measure = build a probe card via `rw_add_visual.py`, open the report, eyeball the value. Build one card per measure family at the end of each task; remove them after.

### Task 6: Backward-rate stage measures (6 measures)

Mirror the existing `Stage Forward Pct` family with `Stage Backward Pct`. Same TREATAS pattern but counts negative `direction` events.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py` (extend the measures list inside `build_model_bim()`)

- [ ] **Step 1: Locate the measures list in build_model_bim**

Open `scripts/sales/rw_push_semantic_model.py`. Search for the existing `Stage Forward Pct` measure to find the insertion site. The measures live in the table block for `f_opportunity` (or `f_stage_transition` for stage-related) inside `build_model_bim()`.

- [ ] **Step 2: Add the 6 backward measures**

Append to the same `measures` list that contains `Stage Forward Pct`:

```python
        {
            "name": "Stage Backward Pct",
            "expression": "DIVIDE ( CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[direction] = -1 ), CALCULATE ( COUNTROWS ( f_stage_transition ) ) )",
            "formatString": "0.0%",
        },
        {
            "name": "Stage Backward Pct (LE)",
            "expression": (
                "CALCULATE ( "
                "  [Stage Backward Pct], "
                "  TREATAS ( "
                "    CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "                     f_opportunity[motion_type] IN { \"Land\", \"Expand\" } ), "
                "    f_stage_transition[opp_id] "
                "  ) "
                ")"
            ),
            "formatString": "0.0%",
        },
```

Then 6 per-stage variants — one per from_stage_num 1..6. Pattern (repeat for stages 1-6):

```python
        {
            "name": "Stage Backward Pct S1->S2",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 1 )",
            "formatString": "0.0%",
        },
```

Generate all 6 by varying `from_stage_num` 1..6 and the suffix (S1->S2, S2->S3, ..., S6->Won).

- [ ] **Step 3: Run the deploy**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Expected: stdout shows "Updating existing semantic model ..." then "refresh enqueued". No HTTP errors.

- [ ] **Step 4: Probe-build a verification card for one measure**

Run: `python3 -m scripts.sales.rw_add_visual --probe-measure "Stage Backward Pct" --table f_opportunity`
(If `--probe-measure` doesn't exist yet, use `build_card_visual` directly via a temp script or extend `--probe` to take a measure name.)

Open the report URL, verify a percentage value renders (>0% expected — backward moves are common).

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add 6 stage backward-rate DAX measures"
```

---

### Task 7: Time-in-stage measures (avg + per-stage)

`time_in_stage` KPI from KG (MEDIUM, missing). Avg days an opp spent in each stage before transitioning out. Derived from OFH transition timestamps.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Verify the OFH transform exposes a duration column**

Read `scripts/sales/sf_to_fabric_rw_phase2.py`. Confirm `f_stage_transition` has columns: `opp_id`, `from_stage_num`, `from_stage_name`, `to_stage_num`, `to_stage_name`, `transition_date`, `direction`. If a `days_in_from_stage` column is NOT computed during the transform, add it now (Step 2). Else jump to Step 3.

- [ ] **Step 2: Add `days_in_from_stage` to the OFH transform (only if missing)**

Edit `scripts/sales/sf_to_fabric_rw_phase2.py`'s `transform()` SQL. After the existing select, add a windowed difference:

```sql
SELECT *,
  date_diff('day',
    LAG(transition_date) OVER (PARTITION BY opp_id ORDER BY transition_date),
    transition_date
  ) AS days_in_from_stage
FROM raw_transitions
```

Re-run: `python3 -m scripts.sales.sf_to_fabric_rw_phase2`
Verify the Lakehouse delta refresh includes the new column (check via Fabric workspace → lakehouse → table preview).

- [ ] **Step 3: Add the time-in-stage measures**

In `build_model_bim()`, append to the measures list:

```python
        {
            "name": "Avg Days in Stage",
            "expression": "AVERAGE ( f_stage_transition[days_in_from_stage] )",
            "formatString": "0.0",
        },
        {
            "name": "Avg Days in Stage (LE)",
            "expression": (
                "CALCULATE ( "
                "  [Avg Days in Stage], "
                "  TREATAS ( "
                "    CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "                     f_opportunity[motion_type] IN { \"Land\", \"Expand\" } ), "
                "    f_stage_transition[opp_id] "
                "  ) "
                ")"
            ),
            "formatString": "0.0",
        },
        # Per-stage variants — generate stages 1..6
        {
            "name": "Avg Days in Stage 1",
            "expression": "CALCULATE ( [Avg Days in Stage (LE)], f_stage_transition[from_stage_num] = 1 )",
            "formatString": "0.0",
        },
        # ... repeat for 2,3,4,5,6
```

Generate all 6 per-stage variants.

- [ ] **Step 4: Deploy and probe**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Probe-card one measure: e.g., `Avg Days in Stage 3` — eyeball the value (expect 15-40 days range based on KG target).

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py scripts/sales/sf_to_fabric_rw_phase2.py
git commit -m "feat(track:rw): add time-in-stage DAX measures + days_in_from_stage column"
```

---

### Task 8: Stall-detection measures

Open opps with no movement in the last N days. Two thresholds: 14d (Watch) and 21d (At-risk).

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Append measures**

```python
        {
            "name": "Last Stage Move Date",
            "expression": (
                "CALCULATE ( "
                "  MAX ( f_stage_transition[transition_date] ), "
                "  USERELATIONSHIP ( f_stage_transition[opp_id], f_opportunity[opp_id] ) "
                ")"
            ),
            "formatString": "yyyy-mm-dd",
        },
        {
            "name": "Days Since Last Stage Move",
            "expression": "DATEDIFF ( [Last Stage Move Date], TODAY (), DAY )",
            "formatString": "0",
        },
        {
            "name": "Stalled Opps Count (>14d)",
            "expression": (
                "SUMX ( "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && [Days Since Last Stage Move] > 14 "
                "  ), "
                "  1 "
                ")"
            ),
            "formatString": "0",
        },
        {
            "name": "Stalled Opps ARR (>14d)",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && [Days Since Last Stage Move] > 14 "
                "  ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
        {
            "name": "Stalled Opps Count (>21d)",
            "expression": (
                "SUMX ( "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && [Days Since Last Stage Move] > 21 "
                "  ), "
                "  1 "
                ")"
            ),
            "formatString": "0",
        },
        {
            "name": "Stalled Opps ARR (>21d)",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && [Days Since Last Stage Move] > 21 "
                "  ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
```

- [ ] **Step 2: Deploy and probe**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Probe-card `Stalled Opps Count (>14d)` and `Stalled Opps ARR (>14d)`. Expect non-zero values (at any given time, a real org has stalls).

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add stall-detection DAX measures (14d / 21d thresholds)"
```

---

### Task 9: Risk-classification measures

Three buckets shown on Tab 1's risk band: At Risk, Watch, Healthy. Each gets count + ARR.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Append measures**

```python
        # At Risk = Stage 5+ open AND (slipped close-date OR moved backward in last 7d)
        {
            "name": "At Risk Opps Count",
            "expression": (
                "SUMX ( "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && f_opportunity[stage_num] >= 5 && ( "
                "      [Stalled Opps Count (>21d)] > 0 || "
                "      CALCULATE ( COUNTROWS ( f_stage_transition ), "
                "                  f_stage_transition[direction] = -1, "
                "                  f_stage_transition[transition_date] >= TODAY () - 7 ) > 0 "
                "    ) "
                "  ), "
                "  1 "
                ")"
            ),
            "formatString": "0",
        },
        {
            "name": "At Risk Opps ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && f_opportunity[stage_num] >= 5 && "
                "    [Stalled Opps Count (>21d)] > 0 "
                "  ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
        # Watch = Stage 3-4 open AND stalled >14d
        {
            "name": "Watch Opps Count",
            "expression": (
                "SUMX ( "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && "
                "    f_opportunity[stage_num] >= 3 && f_opportunity[stage_num] <= 4 && "
                "    [Stalled Opps Count (>14d)] > 0 "
                "  ), "
                "  1 "
                ")"
            ),
            "formatString": "0",
        },
        {
            "name": "Watch Opps ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  FILTER ( "
                "    f_opportunity, "
                "    f_opportunity[is_closed] = FALSE() && "
                "    f_opportunity[stage_num] >= 3 && f_opportunity[stage_num] <= 4 && "
                "    [Stalled Opps Count (>14d)] > 0 "
                "  ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
        # Healthy = forward stage move in last 7d
        {
            "name": "Healthy Moves Count",
            "expression": (
                "CALCULATE ( "
                "  COUNTROWS ( f_stage_transition ), "
                "  f_stage_transition[direction] = 1, "
                "  f_stage_transition[transition_date] >= TODAY () - 7 "
                ")"
            ),
            "formatString": "0",
        },
        {
            "name": "Healthy Moves ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  TREATAS ( "
                "    CALCULATETABLE ( VALUES ( f_stage_transition[opp_id] ), "
                "                     f_stage_transition[direction] = 1, "
                "                     f_stage_transition[transition_date] >= TODAY () - 7 ), "
                "    f_opportunity[opp_id] "
                "  ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
```

- [ ] **Step 2: Deploy + probe each of the three count measures**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Build temporary cards for `At Risk Opps Count`, `Watch Opps Count`, `Healthy Moves Count`. Eyeball: counts should sum to less than the total open-pipe count (overlaps possible but shouldn't exceed total).

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add risk-classification DAX measures (At Risk / Watch / Healthy)"
```

---

### Task 10: Window-bound delta measures

Tab 1 needs counts/ARR for changes within a window. Three named windows: 1d, 7d, FQ-to-date. Six measure families: Stage Moves · Slips · New Opps · Closed Won · Closed Lost · Backward Moves. Each family × 3 windows = 18 measures.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Generate the window-bound measures programmatically**

Insert a helper inside `build_model_bim()` before the measures list construction:

```python
def _window_measures():
    out = []
    windows = {
        "1d": "TODAY () - 1",
        "7d": "TODAY () - 7",
        "FQ": "DATE ( YEAR ( TODAY () ), CEILING ( MONTH ( TODAY () ) / 3, 1 ) * 3 - 2, 1 )",
    }
    for label, since in windows.items():
        out.extend([
            {
                "name": f"Stage Moves Count {label}",
                "expression": f"CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[transition_date] >= {since} )",
                "formatString": "0",
            },
            {
                "name": f"Stage Moves ARR {label}",
                "expression": (
                    "CALCULATE ( "
                    "  SUM ( f_opportunity[arr_org_ccy] ), "
                    "  TREATAS ( "
                    f"    CALCULATETABLE ( VALUES ( f_stage_transition[opp_id] ), f_stage_transition[transition_date] >= {since} ), "
                    "    f_opportunity[opp_id] "
                    "  ) "
                    ")"
                ),
                "formatString": "$#,##0",
            },
            {
                "name": f"Slips Count {label}",
                "expression": (
                    "CALCULATE ( COUNTROWS ( f_ofh_close_date ), "
                    f"f_ofh_close_date[transition_date] >= {since}, "
                    "f_ofh_close_date[new_value] > f_ofh_close_date[old_value] )"
                ),
                "formatString": "0",
            },
            {
                "name": f"New Opps Count {label}",
                "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[created_date] >= {since} )",
                "formatString": "0",
            },
            {
                "name": f"Closed Won Count {label}",
                "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[close_date] >= {since} )",
                "formatString": "0",
            },
            {
                "name": f"Closed Lost Count {label}",
                "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_closed] = TRUE(), f_opportunity[is_won] = FALSE(), f_opportunity[close_date] >= {since} )",
                "formatString": "0",
            },
        ])
    return out
```

Then in the measures list assembly, splat in: `*_window_measures(),`

**Note:** the Slips measures reference `f_ofh_close_date`. If this table doesn't exist in the Lakehouse yet, either (a) defer Slips to a follow-up and remove those 3 measures, or (b) add a CloseDate-OFH pull to `sf_to_fabric_rw_phase2.py` (similar SOQL with `Field = 'CloseDate'`). Pick (b) if the close-date OFH is in the existing pull (re-grep `Field` filter); pick (a) otherwise.

- [ ] **Step 2: Deploy + spot-check**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Probe-card `Stage Moves Count 7d`, `New Opps Count 7d`, `Closed Won Count FQ`. Eyeball values for plausibility.

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add window-bound delta DAX measures (1d/7d/FQ × 6 families)"
```

---

### Task 11: Stage 3 gate measures

`stage3_acv_value` and `stage3_approvals_compliance` from KG.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Append measures**

```python
        {
            "name": "S3+ Open ACV",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[acv_org_ccy] ), "
                "  f_opportunity[is_closed] = FALSE(), "
                "  f_opportunity[stage_num] >= 3 "
                ")"
            ),
            "formatString": "$#,##0",
        },
        {
            "name": "S3+ Open ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  f_opportunity[is_closed] = FALSE(), "
                "  f_opportunity[stage_num] >= 3 "
                ")"
            ),
            "formatString": "$#,##0",
        },
        {
            "name": "S3+ Approval Compliance Pct",
            "expression": (
                "DIVIDE ( "
                "  CALCULATE ( COUNTROWS ( f_opportunity ), "
                "    f_opportunity[is_closed] = FALSE(), "
                "    f_opportunity[stage_num] >= 3, "
                "    f_opportunity[has_commercial_approval] = TRUE() ), "
                "  CALCULATE ( COUNTROWS ( f_opportunity ), "
                "    f_opportunity[is_closed] = FALSE(), "
                "    f_opportunity[stage_num] >= 3 ) "
                ")"
            ),
            "formatString": "0.0%",
        },
```

**Note:** `has_commercial_approval` may not exist as a column on `f_opportunity` today. Check `sf_to_fabric_rw.py` for the SF SOQL — if the field isn't pulled, the approval-compliance measure will be invalid. Two options:

- (a) Defer the compliance measure; ship S3 ACV value only.
- (b) Add the field. Likely SF source: `APTS_Commercial_Approval_Status__c` or similar — verify with a SOQL probe: `sf data query --query "SELECT QualifiedApiName FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='Opportunity' AND QualifiedApiName LIKE '%pproval%'"`.

Pick (a) for first ship if the field requires SF discovery; cycle back to add (b) once confirmed.

- [ ] **Step 2: Deploy + probe `S3+ Open ACV`**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Probe-card and verify a non-zero $ value.

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add S3 gate DAX measures (S3+ ACV/ARR + approval compliance)"
```

---

### Task 12: Growth Mix measures (Phase-1-feasible only)

Of the 8 KPIs assigned to Tab 5 Growth Mix, ship the 3 that need no new ETL: SaaS YoY growth + synergy pipe/won. Defer ILF/ALF, cross-sell-to-acquired, PS attach, one-off rev to a follow-up data pull.

**Files:**

- Modify: `scripts/sales/rw_push_semantic_model.py`

- [ ] **Step 1: Append measures**

```python
        {
            "name": "SaaS Closed Won ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  f_opportunity[is_won] = TRUE(), "
                "  f_opportunity[product_motion] = \"SaaS\" "
                ")"
            ),
            "formatString": "$#,##0",
        },
        {
            "name": "SaaS Closed Won ARR LY",
            "expression": "CALCULATE ( [SaaS Closed Won ARR], SAMEPERIODLASTYEAR ( d_calendar[date] ) )",
            "formatString": "$#,##0",
        },
        {
            "name": "SaaS ARR YoY Growth Pct",
            "expression": "DIVIDE ( [SaaS Closed Won ARR] - [SaaS Closed Won ARR LY], [SaaS Closed Won ARR LY] )",
            "formatString": "0.0%",
        },
        {
            "name": "Synergy Pipe ARR",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  f_opportunity[is_closed] = FALSE(), "
                "  f_opportunity[is_synergy] = TRUE() "
                ")"
            ),
            "formatString": "$#,##0",
        },
        {
            "name": "Synergy Pipe Count",
            "expression": (
                "CALCULATE ( COUNTROWS ( f_opportunity ), "
                "  f_opportunity[is_closed] = FALSE(), "
                "  f_opportunity[is_synergy] = TRUE() )"
            ),
            "formatString": "0",
        },
        {
            "name": "Synergy Won ARR FQTD",
            "expression": (
                "CALCULATE ( "
                "  SUM ( f_opportunity[arr_org_ccy] ), "
                "  f_opportunity[is_won] = TRUE(), "
                "  f_opportunity[is_synergy] = TRUE(), "
                "  f_opportunity[close_date] >= DATE ( YEAR ( TODAY () ), CEILING ( MONTH ( TODAY () ) / 3, 1 ) * 3 - 2, 1 ) "
                ")"
            ),
            "formatString": "$#,##0",
        },
```

**Verify upstream column names:** `product_motion` and `is_synergy` may not exist on `f_opportunity`. Probe via `sf_to_fabric_rw.py` SOQL — likely candidates: `Type` (for SaaS distinction), `APTS_Synergy_Deal__c` or `Is_Synergy__c`. If a column is missing in the Lakehouse, defer that measure and add the SF field to the next ETL run; do NOT ship a measure that references a non-existent column (model deploy will fail).

- [ ] **Step 2: Deploy + probe one measure per family**

Run: `python3 -m scripts.sales.rw_push_semantic_model`
Probe-card `SaaS ARR YoY Growth Pct` and `Synergy Pipe ARR`. Eyeball plausibility.

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_push_semantic_model.py
git commit -m "feat(track:rw): add Growth Mix DAX measures (SaaS YoY, synergy pipe/won)"
```

---

## Phase 3 — Foundation ship + docs

### Task 13: End-to-end verification + measure inventory

Confirm the deployed semantic model has all expected measures and they all evaluate without errors.

**Files:**

- Create: `scripts/sales/rw_inventory_measures.py` (small helper)

- [ ] **Step 1: Write the inventory script**

```python
# scripts/sales/rw_inventory_measures.py
"""Print the measure list deployed to sm_sales_kpis_rw, grouped by family."""
from __future__ import annotations

import base64
import json

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
SEMANTIC_MODEL_ID = "3c58b5dd-b321-4aaa-a5cd-fb73e474edbb"
FABRIC = "https://api.fabric.microsoft.com"


def main() -> None:
    token = AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default").token
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels/{SEMANTIC_MODEL_ID}/getDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    r.raise_for_status()
    # 202 LRO; for inventory we accept the simpler synchronous response; if 202, follow Location.
    data = r.json() if r.status_code == 200 else None
    if data is None:
        print("LRO response — extend script to follow Location header")
        return
    bim_part = next(p for p in data["definition"]["parts"] if p["path"] == "model.bim")
    bim = json.loads(base64.b64decode(bim_part["payload"]).decode("utf-8"))
    measures = []
    for tbl in bim.get("model", {}).get("tables", []):
        for m in tbl.get("measures", []):
            measures.append((tbl["name"], m["name"]))
    print(f"Total measures: {len(measures)}")
    for tbl, name in sorted(measures):
        print(f"  [{tbl}] {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run inventory**

Run: `python3 -m scripts.sales.rw_inventory_measures > /tmp/rw_measure_inventory.txt && wc -l /tmp/rw_measure_inventory.txt`
Expected: line count ≥ 70 (15 base + 6 backward + 8 time-in-stage + 6 stall + 6 risk + 18 windows + 3 S3 + 6 Growth Mix = 68+ deltas + base = 80+). Adjust expectation based on which measures were deferred in Tasks 11 and 12.

- [ ] **Step 3: Open the report and verify all 5 pages render without errors**

Open: `https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/d7362a11-f3dd-4bd1-a69a-68c941c2598b`

Click each tab. Each should be empty (no visualContainers) but render without errors. Tabs visible: What Changed · Forecast · Stage Hygiene · Renewals · Growth Mix.

- [ ] **Step 4: Commit**

```bash
git add scripts/sales/rw_inventory_measures.py
git commit -m "feat(track:rw): add measure inventory CLI for semantic-model audit"
```

---

### Task 14: Update build doc

**Files:**

- Modify: `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`

- [ ] **Step 1: Append a "Foundation Phase Complete" section**

Add at the bottom of `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`:

```markdown
## 2026-05-08 — Foundation Phase Complete

Foundation work for the 5-tab redesign (spec: `docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md`):

**Builders shipped (`scripts/sales/_pbir_helpers.py`):**

- `build_card_visual` (extracted from `rw_add_visual.py`)
- `build_slicer_visual` (extracted)
- `build_table_visual` — tableEx with mixed column/measure projections
- `build_matrix_visual` — pivotTable with rows/columns/values axes
- `add_page` / `remove_page` / `ensure_pages` — idempotent page management

**Pages ensured:** PageWhatChanged · PageForecast · PageStageHygiene · PageRenewals · PageGrowthMix (all empty, ready for visual composition)

**DAX measures added** (run `python3 -m scripts.sales.rw_inventory_measures` for current count):

- 6 backward-rate (Stage Backward Pct + LE + 6 per-stage)
- 8 time-in-stage (avg + LE + 6 per-stage)
- 6 stall-detection (14d + 21d × count + ARR + helper)
- 6 risk-classification (At Risk / Watch / Healthy × count + ARR)
- 18 window-bound deltas (1d/7d/FQ × 6 families)
- 3 S3 gate (S3+ Open ACV/ARR + Approval Compliance)
- 6 Growth Mix (SaaS YoY × 3 + Synergy × 3)

**Tests:** `tests/sales/` covers all helper builders.

**Deferred to follow-up plans:**

- Slips measures if `f_ofh_close_date` table not in Phase 2 ETL
- `S3+ Approval Compliance Pct` if `has_commercial_approval` field not in SF pull
- ILF/ALF pipeline split, cross-sell-to-acquired, PS attach, one-off revenue (need ETL extensions)
- Per-tab visual composition (5 separate plans, one per tab)
```

- [ ] **Step 2: Commit**

```bash
git add docs/sales/RW_VPOPS_DASHBOARD_BUILD.md
git commit -m "docs(track:rw): document foundation phase completion"
```

---

## Self-review notes

**Spec coverage check:**

- Tab 1 What Changed — measures shipped (Tasks 9, 10). Tile composition deferred to Tab 1 plan. ✅
- Tab 2 Forecast — base measures already exist; new commit-risk needs stall (Task 8) + window deltas (Task 10). ✅
- Tab 3 Stage Hygiene — backward (Task 6) + time-in-stage (Task 7) + stall (Task 8) + S3 gate (Task 11). ✅
- Tab 4 Renewals — base measures exist; cohort table needs `build_table_visual` (Task 3). ✅
- Tab 5 Growth Mix — Task 12 ships 6 of 8 KPIs; ETL gaps documented in spec. ✅
- Sync slicers (spec layout standards) — implementation deferred to per-tab plans. Acknowledged.
- "Data not available" tile pattern (spec Growth Mix) — spec-only; render in per-tab plan.

**Type consistency:** all builders return `dict` shaped `{config, filters, height, width, x, y, z}`; all DAX measures use `formatString`; all measure names use Title Case.

**Known pre-existing column dependencies that must be verified during execution:**

- `f_stage_transition[direction]`, `[from_stage_num]`, `[transition_date]`, `[opp_id]` (from Phase 2 ETL)
- `f_opportunity[stage_num]`, `[is_won]`, `[is_closed]`, `[motion_type]`, `[arr_org_ccy]`, `[acv_org_ccy]`, `[created_date]`, `[close_date]`, `[opp_id]`
- New optional fields flagged for verification: `[has_commercial_approval]`, `[product_motion]`, `[is_synergy]`, `f_ofh_close_date` table

If any column is missing, the responsible task's "Note" block tells the engineer to defer that specific measure rather than block the whole task.
