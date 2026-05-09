# VP Ops Front-Page Spine Rebuild (PR1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 45-visualContainer card wall on the live `VP Ops Scorecard` page with two structured spines (exception, movement-placeholder) + one compact 4-KPI strip — using existing measures only, no new DAX, lab-first deploy with a render-proof gate.

**Architecture:** Three new builder functions in `scripts/sales/rw_compose_scorecard_home.py` (`_build_exception_spine`, `_build_movement_spine_placeholder`, `_build_kpi_strip`) replace the existing `_panel` / `_metric_card` / `_compose` body. Exception spine binds to `Exception ARR / Exception Opps Count / At Risk Opps ARR / Watch Opps ARR` (Codex's proven lab order). KPI strip uses native `build_card_visual_with_objects` from `_pbir_helpers.py`; sparklines/variance arrows are deferred to PR2 (Zebra Cards binding unproven). Lab apply via `rw_apply_zebra_lab_proof.py` extension; live promote via existing `rw_push_report.py` (no argparse, module-level constants).

**Tech Stack:** Python 3.13, stdlib + `requests` + `azure-identity`, pytest. PBIR JSON edits. Fabric REST `getDefinition` / push pattern (existing). Zebra BI Tables custom visual GUID per `_pbir_helpers.ZEBRA_BI_TABLES_VISUAL_TYPE`.

**Spec:** `docs/superpowers/specs/2026-05-09-vp-ops-front-page-spine-rebuild-design.md`

**Predecessor work:**

- Codex `303bc6b` — Zebra Exceptions lab proof (binding pattern lifted into Task 2)
- Claude `c419313..415bc37` — Zebra BI Knowledge Graph (validates 33/33 RW measure bindings)
- Claude `4a7454d..a26a9af` — spec + spec review fixes

**Branch:** `feat/track-rw-tooling`. Commit locally; do NOT push until Task 8.

**Layout zones (from spec, sums to 720):**

| Zone                           | x             | y   | w    | h   |
| ------------------------------ | ------------- | --- | ---- | --- |
| Page title (textbox)           | 0             | 0   | 1280 | 64  |
| Exception spine (Zebra Tables) | 0             | 80  | 1280 | 264 |
| Movement placeholder (textbox) | 0             | 360 | 1280 | 224 |
| KPI cards (×4)                 | 0/320/640/960 | 600 | 320  | 120 |

---

## Task 1: Lock the file + rewrite the test contract (failing baseline)

Goal: post the REBUILD IN PROGRESS lock comment so Codex doesn't touch the file mid-implementation, then rewrite the existing test to assert the _new_ 7-visualContainer contract. The test will fail until Tasks 2–5 land — that's the TDD baseline.

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py:1-10` (docstring + lock comment)
- Modify: `tests/sales/test_rw_compose_scorecard_home.py` (full rewrite)

- [ ] **Step 1: Add the lock comment**

Read the current header of `/Users/test/code/apps/sales-ops-copilot-rw/scripts/sales/rw_compose_scorecard_home.py`. Replace the first docstring block with:

```python
# REBUILD IN PROGRESS — see docs/superpowers/specs/2026-05-09-vp-ops-front-page-spine-rebuild-design.md
# DO NOT MODIFY UNTIL THE PR1 REBUILD MERGES. Removed in Task 7.

"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

PR1 layout (see spec): exception spine + movement-spine placeholder +
4-card KPI strip. Replaces the prior 45-visualContainer card wall.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""
```

(Drop the stale "26-card landing page" line. The lock comment is the _first_ thing in the file, before the docstring, so any agent reading the file sees it immediately.)

- [ ] **Step 2: Rewrite the test file**

Replace the entire contents of `/Users/test/code/apps/sales-ops-copilot-rw/tests/sales/test_rw_compose_scorecard_home.py` with:

```python
"""Tests for scripts.sales.rw_compose_scorecard_home — PR1 spine rebuild contract.

The page is composed of exactly 7 visualContainers:
- 1 page-title textbox
- 1 exception spine (Zebra BI Tables custom visual)
- 1 movement-spine placeholder textbox
- 4 KPI strip cards
"""

import json

from scripts.sales.rw_compose_scorecard_home import (
    KPI_STRIP_MEASURES,
    PAGE,
    _build_exception_spine,
    _build_kpi_strip,
    _build_movement_spine_placeholder,
    _compose,
)
from scripts.sales._pbir_helpers import ZEBRA_BI_TABLES_VISUAL_TYPE


# ---------- top-level shape ----------


def test_compose_emits_seven_visualcontainers():
    section = {"visualContainers": []}
    _compose(section)
    assert len(section["visualContainers"]) == 7


def test_compose_visuals_within_canvas():
    section = {"visualContainers": []}
    _compose(section)
    for v in section["visualContainers"]:
        assert v["x"] + v["width"] <= 1280
        assert v["y"] + v["height"] <= 720


def test_layout_zones_sum_to_720px():
    """Title 64 + 16 gap + Exception 264 + 16 gap + Movement 224 + 16 gap + KPI 120 = 720."""
    section = {"visualContainers": []}
    _compose(section)
    visuals = section["visualContainers"]
    # Title at y=0, h=64
    title = next(v for v in visuals if v["y"] == 0)
    assert title["height"] == 64
    # Exception spine at y=80, h=264
    spine = next(v for v in visuals if v["y"] == 80)
    assert spine["height"] == 264
    # Movement placeholder at y=360, h=224
    placeholder = next(v for v in visuals if v["y"] == 360)
    assert placeholder["height"] == 224
    # KPI strip at y=600, h=120 (4 cards)
    kpi_cards = [v for v in visuals if v["y"] == 600]
    assert len(kpi_cards) == 4
    assert all(c["height"] == 120 for c in kpi_cards)


# ---------- exception spine ----------


def test_exception_spine_value_order_matches_lab_proof():
    """Zebra Tables uses positional ordering for IBCS column grouping. The order
    here MUST match Codex's proven lab proof in
    rw_apply_zebra_lab_proof.py:apply_zebra_exceptions_proof."""
    visual = _build_exception_spine()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == ZEBRA_BI_TABLES_VISUAL_TYPE

    # Extract the value projection field names in order
    projections = sv["projections"]
    value_role = projections.get("Y") or projections.get("Values") or projections.get("Primary")
    assert value_role is not None, "expected Y/Values/Primary projection role"
    field_names = [p["queryRef"].split(".")[-1] for p in value_role]
    assert field_names == [
        "Exception ARR",
        "Exception Opps Count",
        "At Risk Opps ARR",
        "Watch Opps ARR",
    ]


def test_exception_spine_position():
    visual = _build_exception_spine()
    assert visual["x"] == 0
    assert visual["y"] == 80
    assert visual["width"] == 1280
    assert visual["height"] == 264


# ---------- movement placeholder ----------


def test_movement_placeholder_is_textbox_not_zebra():
    visual = _build_movement_spine_placeholder()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "textbox"
    assert visual["y"] == 360
    assert visual["height"] == 224


# ---------- KPI strip ----------


def test_kpi_strip_yields_four_cards():
    cards = _build_kpi_strip()
    assert len(cards) == 4


def test_kpi_strip_x_positions_are_evenly_spaced():
    cards = _build_kpi_strip()
    xs = sorted(c["x"] for c in cards)
    assert xs == [0, 320, 640, 960]
    assert all(c["width"] == 320 for c in cards)


def test_kpi_strip_uses_expected_measures():
    assert KPI_STRIP_MEASURES == [
        "Total Closed Won ARR",
        "Win Rate ARR",
        "Stage Forward Pct (LE)",
        "Renewal Retention Pct (Period)",
    ]


# ---------- contract: page name ----------


def test_page_constant_unchanged():
    assert PAGE == "VP Ops Scorecard"
```

(This deletes `test_front_page_kpi_routes_resolve_against_graph` — `FRONT_PAGE_KPI_ROUTES` is replaced by the simpler `KPI_STRIP_MEASURES` list constant, so the route-graph test is no longer applicable.)

- [ ] **Step 3: Run tests — confirm they fail**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py -v
```

Expected: ImportError or AttributeError because `_build_exception_spine`, `_build_movement_spine_placeholder`, `_build_kpi_strip`, `KPI_STRIP_MEASURES` don't exist yet. This is the failing baseline that Tasks 2–5 will turn green.

- [ ] **Step 4: Commit the lock + failing test contract**

```bash
git add scripts/sales/rw_compose_scorecard_home.py tests/sales/test_rw_compose_scorecard_home.py
git commit -m "test(track:rw): lock composer + new 7-visualContainer test contract (failing)"
```

---

## Task 2: Build the exception spine

Goal: implement `_build_exception_spine()` returning the Zebra BI Tables visualContainer at the spine's layout zone, binding to the four exception measures in Codex's proven order.

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py` (add new builder function)

- [ ] **Step 1: Run the spine-specific failing tests**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_exception_spine_value_order_matches_lab_proof tests/sales/test_rw_compose_scorecard_home.py::test_exception_spine_position -v
```

Expected: ImportError on `_build_exception_spine`.

- [ ] **Step 2: Add the builder import + function**

Add to the imports section of `scripts/sales/rw_compose_scorecard_home.py` (top of file, after the existing imports):

```python
from scripts.sales._pbir_helpers import (
    ZEBRA_BI_TABLES_VISUAL_TYPE,
    build_zebra_bi_table_visual,
)
```

(Note: the existing module already imports several things from `_pbir_helpers`. Augment that import block, don't duplicate it. If `ZEBRA_BI_TABLES_VISUAL_TYPE` and `build_zebra_bi_table_visual` are not in the existing import line, add them.)

Add the builder function near the bottom of the file, above `_compose`:

```python
def _build_exception_spine() -> dict:
    """Zebra BI Tables: regional exception view.

    Lifts the binding pattern verbatim from
    rw_apply_zebra_lab_proof.apply_zebra_exceptions_proof, with positions
    re-anchored to the live VP Ops Scorecard layout zone (y=80, h=264).

    Value order is positional — Zebra Tables uses it for IBCS column grouping.
    Do not reorder without re-rendering against the live model.
    """
    return build_zebra_bi_table_visual(
        visual_type=ZEBRA_BI_TABLES_VISUAL_TYPE,
        categories=[
            {"table": "d_region", "field": "region", "title": "Region"},
        ],
        values=[
            {"table": "f_opportunity", "field": "Exception ARR", "title": "Exception ARR"},
            {"table": "f_opportunity", "field": "Exception Opps Count", "title": "Exception opps"},
            {"table": "f_opportunity", "field": "At Risk Opps ARR", "title": "At-risk ARR"},
            {"table": "f_opportunity", "field": "Watch Opps ARR", "title": "Watch ARR"},
        ],
        x=0,
        y=80,
        w=1280,
        h=264,
    )
```

- [ ] **Step 3: Verify the spine tests pass**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_exception_spine_value_order_matches_lab_proof tests/sales/test_rw_compose_scorecard_home.py::test_exception_spine_position -v
```

Expected: 2 passed.

If `test_exception_spine_value_order_matches_lab_proof` fails because the projection role name doesn't match `Y`/`Values`/`Primary`, inspect the output of `_build_exception_spine()` in a Python repl and update the test's role-extraction logic:

```bash
.venv/bin/python -c "
import json
from scripts.sales.rw_compose_scorecard_home import _build_exception_spine
v = _build_exception_spine()
print(list(json.loads(v['config'])['singleVisual']['projections'].keys()))
"
```

If the role name is something other than `Y`/`Values`/`Primary`, add it to the test's `value_role = projections.get(...) or ...` chain (and only that — don't change the production code; the helper is shared with the working lab proof).

- [ ] **Step 4: Commit**

```bash
git add scripts/sales/rw_compose_scorecard_home.py tests/sales/test_rw_compose_scorecard_home.py
git commit -m "feat(track:rw): _build_exception_spine — Zebra Tables, lab-proven order"
```

---

## Task 3: Build the movement-spine placeholder

Goal: implement `_build_movement_spine_placeholder()` — a single textbox visualContainer signaling that the waterfall is coming in PR2.

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py` (add new builder function)

- [ ] **Step 1: Run the placeholder failing test**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_movement_placeholder_is_textbox_not_zebra -v
```

Expected: ImportError on `_build_movement_spine_placeholder`.

- [ ] **Step 2: Add the builder function**

Add to `scripts/sales/rw_compose_scorecard_home.py`, immediately after `_build_exception_spine`:

```python
def _build_movement_spine_placeholder() -> dict:
    """Textbox placeholder for the movement waterfall (PR2).

    Reserves the vertical real-estate so PR2's bridge visual lands cleanly,
    and signals to the executive viewer that 'what changed' is coming —
    rather than the rebuild looking permanently incomplete.
    """
    return build_textbox_visual(
        text=(
            "Movement spine — see PR2 (Pipeline ARR last 7d waterfall, "
            "pending new ARR-7d measures and Commercial Approval Gate "
            "Exception ARR measure)"
        ),
        x=0,
        y=360,
        w=1280,
        h=224,
        font_size_pt=11,
        color="#666666",
    )
```

(`build_textbox_visual` is already imported at the top of the file from `_pbir_helpers`.)

- [ ] **Step 3: Verify the placeholder test passes**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_movement_placeholder_is_textbox_not_zebra -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/sales/rw_compose_scorecard_home.py
git commit -m "feat(track:rw): _build_movement_spine_placeholder — textbox for PR2 waterfall"
```

---

## Task 4: Build the KPI strip

Goal: implement `_build_kpi_strip()` returning 4 native card visualContainers (Zebra Cards binding unproven; native fallback per spec). Sparkline + variance arrow are deferred to PR2.

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py` (add `KPI_STRIP_MEASURES` constant + builder)

- [ ] **Step 1: Run the KPI strip failing tests**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_yields_four_cards tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_x_positions_are_evenly_spaced tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_uses_expected_measures -v
```

Expected: ImportError on `KPI_STRIP_MEASURES` and `_build_kpi_strip`.

- [ ] **Step 2: Add the constant + builder**

Add the import for the card helper (augment the existing `from scripts.sales._pbir_helpers import (...)` block):

```python
from scripts.sales._pbir_helpers import (
    ZEBRA_BI_TABLES_VISUAL_TYPE,
    build_card_visual_with_objects,
    build_textbox_visual,
    build_zebra_bi_table_visual,
)
```

(Drop any existing imports from `_pbir_helpers` that the rewritten composer no longer uses — `build_clustered_bar_chart_visual`, `build_rag_card_visual`, `build_shape_visual`, `build_slicer_visual`, `build_table_style_objects`, `build_table_visual` were used by the deleted card wall and are no longer needed. If unsure, leave them and let Task 5 prune.)

Add the constant near the top, above `FRONT_PAGE_KPI_ROUTES`:

```python
# PR1 KPI strip — 4 measures, native cards (Zebra Cards binding deferred to PR2).
# Renewal Retention is on the same row as ARR cards by design — display layer
# only; the cardinal rule (no blending in compute) is preserved because each
# measure is computed independently.
KPI_STRIP_MEASURES = [
    "Total Closed Won ARR",
    "Win Rate ARR",
    "Stage Forward Pct (LE)",
    "Renewal Retention Pct (Period)",
]
```

Add the builder function below `_build_movement_spine_placeholder`:

```python
def _build_kpi_strip() -> list[dict]:
    """4 native cards, evenly spaced across 1280px at y=600.

    Each card binds one measure from KPI_STRIP_MEASURES. Sparklines and
    variance arrows are PR2 work (Zebra Cards binding pattern unproven).
    """
    cards: list[dict] = []
    for i, measure_name in enumerate(KPI_STRIP_MEASURES):
        cards.append(
            build_card_visual_with_objects(
                table="f_opportunity",
                field=measure_name,
                title=measure_name,
                x=i * 320,
                y=600,
                w=320,
                h=120,
            )
        )
    return cards
```

- [ ] **Step 3: Verify build_card_visual_with_objects accepts these kwargs**

```bash
.venv/bin/python -c "
import inspect
from scripts.sales._pbir_helpers import build_card_visual_with_objects
print(inspect.signature(build_card_visual_with_objects))
"
```

If the signature doesn't match `table=, field=, title=, x=, y=, w=, h=`, adjust the call in `_build_kpi_strip` to match the actual signature. The existing helper (line 921 of `_pbir_helpers.py`) is the source of truth.

If the signature differs (e.g., uses `measure=` instead of `field=`, or expects positional args), update the `_build_kpi_strip` body accordingly. Do NOT modify `_pbir_helpers.py` — that file is shared with other composers.

- [ ] **Step 4: Run KPI strip tests**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_yields_four_cards tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_x_positions_are_evenly_spaced tests/sales/test_rw_compose_scorecard_home.py::test_kpi_strip_uses_expected_measures -v
```

Expected: 3 passed.

- [ ] **Step 5: Verify all 4 KPI measures exist in the live RW model**

```bash
.venv/bin/python -c "
from scripts.sales.rw_compose_scorecard_home import KPI_STRIP_MEASURES
from scripts.sales.rw_inventory_measures import fetch_measures_by_table
m = fetch_measures_by_table()
all_measures = {n for ms in m.values() for n in ms}
missing = [k for k in KPI_STRIP_MEASURES if k not in all_measures]
print('present:', [k for k in KPI_STRIP_MEASURES if k not in missing])
print('missing:', missing)
assert not missing, f'KPI strip references measures not in live RW model: {missing}'
"
```

Expected: `missing: []`. If any measure is missing, STOP — that's a real authoring gap; the spec assumed all 4 are bound (per `data/zebra_kg_rw/bindings.jsonl`). Report which measure is missing and pause for plan revision.

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_compose_scorecard_home.py
git commit -m "feat(track:rw): _build_kpi_strip — 4 native cards, sparklines deferred to PR2"
```

---

## Task 5: Rewrite `_compose()` and delete the old card wall

Goal: replace the body of `_compose()` to call the three builders + delete the old `_panel`, `_metric_card`, `_target_line`, `_find_page` helpers and the `FRONT_PAGE_KPI_ROUTES` constant. After this task, the full new test suite passes.

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py` (significant deletion + rewrite of `_compose`)

- [ ] **Step 1: Read the current state of the file**

Use Read on `/Users/test/code/apps/sales-ops-copilot-rw/scripts/sales/rw_compose_scorecard_home.py` to see the full module. Note which helpers and constants are part of the old card wall vs. used by `main()` or other modules.

Verify the current line ranges (they may shift after Tasks 2–4):

- `FRONT_PAGE_KPI_ROUTES` — old, delete
- `_target_line` — only called by `_panel`/`_metric_card`, delete
- `_find_page` — likely still useful for `main()`, KEEP
- `_panel` — old card wall, delete
- `_metric_card` — old card wall, delete
- `_compose` — REWRITE body
- `main` — KEEP (just calls `_compose` against the report's section)

The color palette constants (`NAVY`, `BLUE`, `MUTED`, `LIGHT`, `BORDER`, `RED`, `AMBER`, `GREEN`, `RED_TINT`, `AMBER_TINT`, `GREEN_TINT`) — delete any not referenced elsewhere in the rewritten module. Run `grep -n "NAVY\|BLUE\|MUTED\|LIGHT\|BORDER\|RED\|AMBER\|GREEN" scripts/sales/rw_compose_scorecard_home.py` after rewriting `_compose` to confirm zero usage, then delete.

- [ ] **Step 2: Rewrite `_compose()`**

Replace the existing `_compose` function body with:

```python
def _compose(section: dict) -> None:
    """Compose the VP Ops Scorecard front page (PR1).

    Emits exactly 7 visualContainers:
      1. Page title (textbox at y=0)
      2. Exception spine (Zebra BI Tables at y=80)
      3. Movement-spine placeholder (textbox at y=360)
      4-7. KPI strip (4 native cards at y=600)

    Total layout closes to 720px with intentional 16px breathing-room gaps.
    """
    section["visualContainers"] = [
        build_textbox_visual(
            text="VP Ops Scorecard",
            x=0,
            y=0,
            w=1280,
            h=64,
            font_size_pt=20,
            color="#1F2937",
            bold=True,
        ),
        _build_exception_spine(),
        _build_movement_spine_placeholder(),
        *_build_kpi_strip(),
    ]
```

(Verify `build_textbox_visual` accepts `bold=True` — if not, drop the kwarg. The `font_size_pt=20` is meant to match the page-title textbox in `apply_zebra_exceptions_proof`'s scorecard header. If the helper signature differs, conform to it.)

- [ ] **Step 3: Delete the old helpers and constants**

Remove these from `scripts/sales/rw_compose_scorecard_home.py`:

- The entire `FRONT_PAGE_KPI_ROUTES = { ... }` block
- `def _target_line(route: str) -> str:` and its body
- `def _panel(...)` and its body
- `def _metric_card(...)` and its body
- Any color palette constants no longer referenced (run grep to confirm zero usages first)
- The `from scripts.sales.rw_kpi_graph import find_kpi` import (no longer used)
- Any other imports that were only for the deleted helpers (`build_clustered_bar_chart_visual`, `build_rag_card_visual`, `build_shape_visual`, `build_slicer_visual`, `build_table_style_objects`, `build_table_visual`)

After deletion, the file should be substantially shorter (~80–120 lines vs the current 428).

- [ ] **Step 4: Run the full composer test file**

```bash
.venv/bin/python -m pytest tests/sales/test_rw_compose_scorecard_home.py -v
```

Expected: all 8 tests pass.

If `test_compose_emits_seven_visualcontainers` fails with a non-7 count, count what `_compose` actually emits and reconcile against the layout zones table.

If `test_layout_zones_sum_to_720px` fails because no visual is found at the expected y, the position constants in the builders don't match the spec — re-check Tasks 2/3/4 positions.

- [ ] **Step 5: Run the full sales test suite**

```bash
.venv/bin/python -m pytest tests/sales/ -v
```

Expected: all tests pass. If any other test file (e.g., `test_rw_compose_what_changed.py`, `test_pbir_helpers.py`) fails because we deleted a helper or constant it imported, restore the import and add it back to the deletion list as out-of-scope (mark with a `# kept for <other consumer>` comment).

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_compose_scorecard_home.py
git commit -m "feat(track:rw): rewrite _compose to 7 visualContainers, delete card wall

45 → 7 visualContainers. Deletes _panel, _metric_card, _target_line,
FRONT_PAGE_KPI_ROUTES + unused color palette constants. Front page
now: title + exception spine + movement placeholder + 4-card KPI strip."
```

---

## Task 6: Lab apply

Goal: write the new `_compose()` output into the lab PBIP's `VP Ops Scorecard` section so we can render-verify in Power BI Desktop before promoting live.

**Files:**

- Modify: `scripts/sales/rw_apply_zebra_lab_proof.py` (add `apply_spine_rebuild_to_main_page` function + wire into `apply_lab_proof`)

- [ ] **Step 1: Inspect the lab PBIP's current section names**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
report_path = Path('/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json')
report = json.loads(report_path.read_text())
for s in report['sections']:
    print(s.get('name'), '|', s.get('displayName'))
"
```

Expected: list of sections including `VP Ops Scorecard` (or similar). Note the exact `displayName` — that's what `_compose` targets.

- [ ] **Step 2: Add the lab-apply function**

Add to `scripts/sales/rw_apply_zebra_lab_proof.py`, near `apply_zebra_exceptions_proof`:

```python
def apply_spine_rebuild_to_main_page(report: dict) -> None:
    """Apply the PR1 front-page rebuild to the main 'VP Ops Scorecard' section
    in the lab PBIP. Imports the live composer to keep the binding source of
    truth in one place.
    """
    from scripts.sales.rw_compose_scorecard_home import PAGE, _compose

    section = next(
        (s for s in report["sections"] if s.get("displayName") == PAGE),
        None,
    )
    if section is None:
        raise RuntimeError(
            f"lab PBIP has no section with displayName={PAGE!r}; "
            f"cannot apply spine rebuild"
        )
    _compose(section)
```

Then update `apply_lab_proof` (around line 337) to also call the new function. After the existing `apply_zebra_exceptions_proof(report)` line, add:

```python
    apply_spine_rebuild_to_main_page(report)
```

- [ ] **Step 3: Run the lab apply**

```bash
.venv/bin/python -m scripts.sales.rw_apply_zebra_lab_proof
```

Expected: writes the updated `report.json` back to the lab PBIP. No errors.

If the section name doesn't match `PAGE = "VP Ops Scorecard"`, the lab PBIP may have been generated with a different section displayName. Inspect with the Step 1 command and either: (a) update `PAGE` to match (also update the test), or (b) rename the section in the lab PBIP. Prefer (a) only if the live Fabric report's section name matches the lab — verify before changing.

- [ ] **Step 4: Verify the lab `report.json` now has 7 visualContainers in that section**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
report_path = Path('/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json')
report = json.loads(report_path.read_text())
for s in report['sections']:
    if s.get('displayName') == 'VP Ops Scorecard':
        print(f'visualContainers: {len(s[\"visualContainers\"])}')
        for v in s['visualContainers']:
            cfg = json.loads(v['config'])
            print(f'  {cfg[\"singleVisual\"][\"visualType\"]:30} x={v[\"x\"]:4} y={v[\"y\"]:4} w={v[\"width\"]:4} h={v[\"height\"]:3}')
        break
"
```

Expected: prints 7 visualContainers with the layout zones from the spec. If the count is wrong or positions don't match, re-check Tasks 2–5.

- [ ] **Step 5: Render proof in Power BI Desktop (manual)**

Open the lab PBIP in Power BI Desktop running on the Parallels VM (`Windows 11`, 32 GB / 8 CPU per the earlier session). The PBIP path is:

```
/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard_zebra_lab.pbip
```

In Desktop:

1. Wait for the model to load (may be 30–60s on first open after the lab apply).
2. Navigate to the `VP Ops Scorecard` page.
3. Verify visually:
   - Page title at top renders.
   - Zebra Tables exception spine renders with 4 value columns in the order `Exception ARR / Exception Opps Count / At Risk Opps ARR / Watch Opps ARR`.
   - Movement placeholder textbox renders the deferred-to-PR2 message.
   - 4 KPI cards render along the bottom with measures populated.
   - No empty Zebra shells, no Renewal ACV blended into ARR cards.

4. Capture a screenshot to `/Users/test/.frontier/artifacts/rw_vpops_spine_rebuild_20260509.png` (use macOS Cmd-Shift-4, then move).

If any visual fails to render, STOP. Most likely causes: (a) a measure name typo in `_compose`'s output (compare to `fetch_measures_by_table()`); (b) Zebra license popup (re-enter the trial key, then re-render); (c) Zebra Cards quirk if you swapped from native `kpiVisual` (revert to native).

- [ ] **Step 6: Commit the lab-apply script change**

```bash
git add scripts/sales/rw_apply_zebra_lab_proof.py
git commit -m "feat(track:rw): apply_spine_rebuild_to_main_page — lab apply hook"
```

(The screenshot lives outside the repo at `~/.frontier/artifacts/`. Don't commit it.)

---

## Task 7: Live promote + docs update + remove the lock

Goal: push the rebuilt page to the live Fabric report, update the build doc with the render proof, and remove the REBUILD IN PROGRESS lock comment.

**Files:**

- Modify: `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` (append PR1 section)
- Modify: `scripts/sales/rw_compose_scorecard_home.py` (remove lock comment)

- [ ] **Step 1: Run the live promote**

The existing `rw_push_report.py` reads `WORKSPACE_ID` and `REPORT_NAME` as module-level constants — no CLI flags. Confirm those constants point at the right workspace/report:

```bash
grep -E "^WORKSPACE_ID|^REPORT_NAME" scripts/sales/rw_push_report.py
```

Expected:

```
WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
REPORT_NAME = "rpt_vp_ops_scorecard"
```

If they differ, STOP — verify with Andre that the target workspace/report is correct before pushing.

If they match, run the push:

```bash
.venv/bin/python -m scripts.sales.rw_push_report
```

Expected: the script posts the report definition to Fabric REST and prints success. May take 30–60s for the LRO to complete.

If the push fails with a 401, run `az login` and retry. If it fails with a measure-not-found error, STOP — a measure binding in the rebuilt page references a measure that exists in the lab semantic model but not the live one. Inspect `fetch_measures_by_table()` against the live workspace and reconcile.

- [ ] **Step 2: Smoke-check the live workspace**

Open `https://app.powerbi.com` → workspace `b66233d5-9d4a-44ba-89a8-b70206d98ae7` → `rpt_vp_ops_scorecard` → `VP Ops Scorecard` page. Same visual checks as the lab Step 5 of Task 6. Capture screenshot to `/Users/test/.frontier/artifacts/rw_vpops_spine_rebuild_live_20260509.png`.

- [ ] **Step 3: Append PR1 section to the build doc**

Append to `/Users/test/code/apps/sales-ops-copilot-rw/docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`:

```markdown
## VP Ops Scorecard front-page spine rebuild — PR1 (2026-05-09)

PR1 of the spine rebuild replaces the 45-visualContainer card wall with two
spines + a 4-card KPI strip. Exception spine uses Codex's lab-proven Zebra
BI Tables binding pattern (`303bc6b`) lifted into
`scripts/sales/rw_compose_scorecard_home.py`. Movement spine is a textbox
placeholder pending PR2's ARR-7d measure authoring.

**Layout (sums to 720):**

| Zone                           | y   | h   |
| ------------------------------ | --- | --- |
| Page title                     | 0   | 64  |
| Exception spine (Zebra Tables) | 80  | 264 |
| Movement placeholder           | 360 | 224 |
| KPI strip (4 cards)            | 600 | 120 |

**Bindings:**

- Exception spine values (positional): `Exception ARR`, `Exception Opps Count`,
  `At Risk Opps ARR`, `Watch Opps ARR`. All Land+Expand only.
- KPI strip measures: `Total Closed Won ARR`, `Win Rate ARR`,
  `Stage Forward Pct (LE)`, `Renewal Retention Pct (Period)`. The retention
  card is Renewal-side ACV; cardinal rule preserved (compute layer, not display
  layer).

**Verification:**

- `python3 -m pytest tests/sales/test_rw_compose_scorecard_home.py` → 8 passed.
- Lab render: `~/.frontier/artifacts/rw_vpops_spine_rebuild_20260509.png`.
- Live render: `~/.frontier/artifacts/rw_vpops_spine_rebuild_live_20260509.png`.
- Local secret scan over `scripts/sales`, `tests/sales`, `docs/sales` — clean.

**Deferred to PR2:**

- Movement waterfall (4 new ARR-7d measures: `New Opps ARR 7d`,
  `Closed Won ARR 7d`, `Closed Lost ARR 7d`, `Backward Moves ARR 7d`).
- Gate-violation exception column (1 new measure
  `Commercial Approval Gate Exception ARR` joining f_opportunity to
  `Stage_20_Approval__c`).
- Zebra Cards binding pattern (current PR1 strip uses native cards;
  sparklines + variance arrows wait for the Cards binding to be authored).
```

- [ ] **Step 4: Remove the REBUILD IN PROGRESS lock comment**

Edit `/Users/test/code/apps/sales-ops-copilot-rw/scripts/sales/rw_compose_scorecard_home.py` and delete the two `# REBUILD IN PROGRESS — ...` lines added in Task 1 Step 1. The file should start with the docstring directly.

- [ ] **Step 5: Commit**

```bash
git add docs/sales/RW_VPOPS_DASHBOARD_BUILD.md scripts/sales/rw_compose_scorecard_home.py
git commit -m "docs(track:rw): RW_VPOPS_DASHBOARD_BUILD update + remove rebuild lock

Lab + live render proofs captured. PR1 closes 45 → 7 visualContainers
on VP Ops Scorecard. Movement waterfall + gate-violation column +
Zebra Cards binding deferred to PR2 (see followup section)."
```

---

## Task 8: Final pass + push

Goal: full pytest, secret scan, push branch for Codex's review.

**Files:** none modified.

- [ ] **Step 1: Full sales test suite**

```bash
.venv/bin/python -m pytest tests/sales/ -v
```

Expected: all tests pass. Note the count.

- [ ] **Step 2: Secret scan**

```bash
grep -RIE "xeqDi|TI2dmTyVm|licenseKey|license_key" scripts/sales/ tests/sales/ docs/sales/ data/zebra_kg/ data/zebra_kg_rw/ 2>/dev/null
```

Expected: empty output (no matches). If any line prints, STOP — pull it out before pushing.

- [ ] **Step 3: Confirm git status is clean**

```bash
git status --short
```

Expected: only the unrelated working-tree mods that pre-existed (`scripts/workforce/wf_*.py`, etc., per the session-start state). No tracked-file unstaged edits in `scripts/sales/` or `tests/sales/`.

- [ ] **Step 4: Push the branch**

```bash
git push origin feat/track-rw-tooling
```

Codex reviews at branch level. PR creation is Codex's lane per project CLAUDE.md.

- [ ] **Step 5: Report completion**

Print a final summary:

- Commits added in this PR1 (range from Task 1 base SHA to current HEAD, `git log --oneline <base>..HEAD`)
- Final test count
- Lab + live screenshot paths
- PR2 backlog (movement waterfall + gate-violation measure + Zebra Cards binding)

---

## Self-review checklist (run before declaring done)

1. **Spec coverage** — every spec section maps to a task:

   | Spec section                                   | Task                                    |
   | ---------------------------------------------- | --------------------------------------- |
   | Layout zones table                             | Tasks 2/3/4 (positions) + Task 1 (test) |
   | Exception spine binding (positional order)     | Task 2                                  |
   | Movement spine placeholder                     | Task 3                                  |
   | KPI strip — 4 native cards (Cards deferred)    | Task 4                                  |
   | Cardinal-rule justification                    | Task 4 (constant docstring)             |
   | `_compose` rewrite + 45 → 7 deletion           | Task 5                                  |
   | Lab-first deploy with render-proof gate        | Task 6                                  |
   | Live promote via existing CLI shape            | Task 7                                  |
   | Build-doc update with render proofs            | Task 7                                  |
   | Concurrency lock (REBUILD IN PROGRESS comment) | Task 1 + Task 7 (removal)               |
   | `rw_push_report.py` no-argparse fix            | Task 7 (no flags in command)            |

2. **Placeholder scan** — no "TBD", "TODO", "implement later", "fill in details", "Add appropriate error handling," or "Similar to Task N." Each step has explicit code or commands.

3. **Type consistency** — `_build_exception_spine() -> dict`, `_build_movement_spine_placeholder() -> dict`, `_build_kpi_strip() -> list[dict]`, `KPI_STRIP_MEASURES: list[str]`, `PAGE: str = "VP Ops Scorecard"`. Names used identically across Tasks 1, 2, 3, 4, 5.

4. **External signature dependencies** — `build_zebra_bi_table_visual(visual_type, categories, values, x, y, w, h)` and `build_card_visual_with_objects(table, field, title, x, y, w, h)` and `build_textbox_visual(text, x, y, w, h, font_size_pt, color, [bold])`. Task 4 Step 3 verifies the card helper's actual signature; Task 5 includes a bold-kwarg fallback note.

5. **Scope check** — single PR1, no decomposition needed. PR2 is a separate spec/plan cycle.
