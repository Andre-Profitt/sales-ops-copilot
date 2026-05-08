# RW Dashboard — Tab 1 (What Changed) Composition Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compose visuals on the `PageWhatChanged` tab of `rpt_vp_ops_scorecard` using primitives + measures shipped in the foundation phase. End state: Risk band (3 hero cards) + Change buckets (4 counter cards) + Detail table (top-20 open opps by ARR exposure). Window slicer position reserved; full field-parameter wiring deferred to Phase 2.

**Spec:** `docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md` § Tab 1.

**Architecture:** All visuals authored via existing `_pbir_helpers.py` builders (`build_card_visual`, `build_table_visual`). New pure-Python composer `scripts/sales/rw_compose_what_changed.py` finds the page by `displayName` (per `feedback_fabric_section_reorder_2026-05-08`) and appends visualContainers via `push_report`. Pre-flight every push with `rw_validate.py` to catch typos before LRO.

**Stack:** Python 3.13 · Fabric REST · `azure-identity` (`AzureCliCredential`) · existing PBIR-Legacy helpers.

**Foundation already shipped (don't re-build):**

- 5 redesign tabs already exist (`PageWhatChanged` is empty and ready)
- 98 measures live in `sm_sales_kpis_rw` — covers the spec's risk band, 3 of 4 change buckets, and partial detail-table needs
- Validator catches typos pre-push
- Probe-card pattern already running on `What Changed` (will be cleared in Task 1)

**Pragmatic deferrals (path-(a) consistent with foundation phase):**

- **Window slicer:** ship the 7d window only; reserve a 240×90 slot in the layout for a future field-parameter slicer
- **Slips bucket:** card placeholder with "Phase 2" subtitle — needs `f_ofh_close_date` ETL extension
- **Detail-table "Change" column:** complex row-context measure; ship Top-20-by-ARR table with `opp_name · account_name · region · arr_org_ccy · last_stage_change_date · stage_name` and add the "Change" column in Phase 2
- **Detail-table "Risk class" column:** same — defer until row-context Risk classification is available
- **Conditional formatting on Risk band:** ship cards plain; capture a browser-configured RAG shape in a follow-up via `rw_capture_visual.py` (Task 6)

---

## Phase 0 — Layout fixture + composer scaffold

### Task 1: Compose-tab CLI scaffold

**Files:**

- Create: `scripts/sales/rw_compose_what_changed.py`
- (Reuse: `_pbir_helpers.py`, `rw_add_visual._token / get_current_report_json / push_report`)

- [ ] **Step 1: Skeleton script that clears `What Changed` and pushes empty**

```python
# scripts/sales/rw_compose_what_changed.py
"""Compose the 'What Changed' tab of rpt_vp_ops_scorecard.

Idempotent: re-running clears the tab and rebuilds from scratch.
"""
from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual,
    build_table_visual,
)
from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)

PAGE = "What Changed"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(f"page {PAGE!r} not found; run --ensure-pages first")


def main() -> None:
    token = _token()
    print("getting report.json...")
    rj = get_current_report_json(token)
    section = _find_page(rj)
    print(f"  current visuals on {PAGE!r}: {len(section.get('visualContainers', []))}")
    section["visualContainers"] = []

    # Visuals composed in Phase 1-3 below, appended to section['visualContainers']

    print(f"\npushing; total visuals on {PAGE!r}: {len(section['visualContainers'])}")
    push_report(token, rj)
    print(
        f"\ndone. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run; expect "0 visuals" pushed**

Run: `python3 -m scripts.sales.rw_compose_what_changed`
Expected: LRO succeeds; report opens to an empty `What Changed` tab.

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_compose_what_changed.py
git commit -m "feat(track:rw): compose-tab scaffold for What Changed"
```

---

## Phase 1 — Risk band (3 hero cards)

### Task 2: Three risk-class cards

**Layout:** y=20 row. Three 320×140 cards across the top: At Risk · Watch · Healthy. Each shows the count metric with the ARR metric as secondary line. Spec's RAG colors deferred to Task 6 (browser capture).

**Files:**

- Modify: `scripts/sales/rw_compose_what_changed.py`

- [ ] **Step 1: Add the risk-band block**

Insert before the `push_report(token, rj)` line:

```python
    # ── Phase 1: Risk band ─────────────────────────────────────
    # Hero cards. ARR shown via a separate small card under each
    # count — a single card can only host one Measure per the
    # current builder. Deferred: combine into one card via objects
    # block (see Task 6).
    risk_band = [
        ("At Risk Opps Count", "At Risk Opps ARR", "At Risk", 20),
        ("Watch Opps Count", "Watch Opps ARR", "Watch", 360),
        ("Healthy Moves Count", "Healthy Moves ARR", "Healthy", 700),
    ]
    for count_msr, arr_msr, title, x in risk_band:
        # Top: count card (large)
        section["visualContainers"].append(
            build_card_visual(
                "f_opportunity", count_msr, f"{title} — count", x=x, y=20, w=320, h=120
            )
        )
        # Below: ARR card (smaller)
        section["visualContainers"].append(
            build_card_visual(
                "f_opportunity", arr_msr, f"{title} — ARR", x=x, y=145, w=320, h=80
            )
        )
```

- [ ] **Step 2: Pre-flight validate the dict against the live model**

Before pushing, run a programmatic sanity check by importing the validator:

```python
from scripts.sales.rw_validate import (
    fetch_measures_by_table,
    validate_visual_dict,
)

# (right before push_report)
by_table = fetch_measures_by_table()
errors = []
for vc in section["visualContainers"]:
    errors.extend(validate_visual_dict(vc, by_table))
if errors:
    raise SystemExit("\n".join(["Pre-flight validation failed:"] + errors))
print(f"  pre-flight: {len(section['visualContainers'])} visuals, all refs resolve ✓")
```

- [ ] **Step 3: Run; verify in browser**

Run: `python3 -m scripts.sales.rw_compose_what_changed`
Expected: 6 visuals (3 count cards + 3 ARR cards) in a 2-row band at the top of `What Changed`. Open URL, eyeball.

- [ ] **Step 4: Commit**

```bash
git add scripts/sales/rw_compose_what_changed.py
git commit -m "feat(track:rw): What Changed — risk band (At Risk / Watch / Healthy)"
```

---

## Phase 2 — Change buckets (4 counter cards)

### Task 3: Stage Moves · Slips · New Opps · Closed cards

**Layout:** y=255 row. Four 240×120 cards. Slips card uses a placeholder measure name pattern that flags "Phase 2" in the title; do NOT add a real measure ref to a non-existent measure (validator would block).

**Pragmatic choice for Slips:** instead of a phantom card, omit it from the row and document the gap in the build doc. Three real cards is better than four cards where one is fake.

**Files:**

- Modify: `scripts/sales/rw_compose_what_changed.py`

- [ ] **Step 1: Add the change-buckets block (3 cards, not 4)**

Insert after the risk band:

```python
    # ── Phase 2: Change buckets (3 of 4 spec'd; Slips deferred) ──
    # Spec calls for Stage Moves · Slips · New Opps · Closed.
    # Slips defers until f_ofh_close_date ETL ships — see
    # docs/sales/RW_VPOPS_DASHBOARD_BUILD.md (Foundation Phase).
    change_buckets = [
        ("f_stage_transition", "Stage Moves Count 7d", "Stage Moves (7d) — count", 20, 255),
        ("f_stage_transition", "Stage Moves ARR 7d", "Stage Moves (7d) — ARR", 20, 380, 240, 80),
        ("f_opportunity", "New Opps Count 7d", "New Opps (7d)", 280, 255),
        ("f_opportunity", "Closed Won Count 7d", "Won (7d)", 540, 255),
        ("f_opportunity", "Closed Lost Count 7d", "Lost (7d)", 800, 255),
    ]
    for entry in change_buckets:
        if len(entry) == 5:
            tbl, msr, title, x, y = entry
            w, h = 240, 120
        else:
            tbl, msr, title, x, y, w, h = entry
        section["visualContainers"].append(
            build_card_visual(tbl, msr, title, x=x, y=y, w=w, h=h)
        )
```

- [ ] **Step 2: Run + validate + push**

Run: `python3 -m scripts.sales.rw_compose_what_changed`
Expected: pre-flight validates 11 total visuals; LRO succeeds. Browser shows 6 risk-band visuals + 5 change-bucket visuals.

- [ ] **Step 3: Commit**

```bash
git add scripts/sales/rw_compose_what_changed.py
git commit -m "feat(track:rw): What Changed — change buckets (Slips deferred)"
```

---

## Phase 3 — Detail table

### Task 4: Top-20 open opps detail table

**Layout:** y=510, full width 1200×260. 6 columns; left-aligned strings, right-aligned numerics (table builder default).

**Spec columns vs reality:**

| Spec       | Ship now                            | Reason                                                |
| ---------- | ----------------------------------- | ----------------------------------------------------- |
| Opp        | ✓ `opp_name`                        | Available                                             |
| Owner      | ✗ → use `account_name`              | `owner_name` not denormalized; would need d_user join |
| Region     | ✓ `region`                          | On f_opportunity (denormalized)                       |
| Change     | ✗ defer                             | Row-context categorization needs new measure          |
| ARR        | ✓ `Total Open Pipeline ARR` measure | Aggregate, but renders as the table's $ column        |
| When       | ✓ `last_stage_change_date`          | On f_opportunity                                      |
| Risk class | ✗ defer                             | Same as Change — row-context calc                     |

Add `stage_name` as a 7th column to give the table some context.

**Files:**

- Modify: `scripts/sales/rw_compose_what_changed.py`

- [ ] **Step 1: Add the table block**

```python
    # ── Phase 3: Detail table ──────────────────────────────────
    # Top-20 by Open Pipeline ARR (descending implicit); columns
    # adapted to denormalized f_opportunity. "Change" + "Risk
    # class" columns deferred to row-context Phase 2.
    section["visualContainers"].append(
        build_table_visual(
            name="what_changed_detail",
            columns=[
                {"table": "f_opportunity", "field": "opp_name", "kind": "column", "title": "Opp"},
                {"table": "f_opportunity", "field": "account_name", "kind": "column", "title": "Account"},
                {"table": "f_opportunity", "field": "region", "kind": "column", "title": "Region"},
                {"table": "f_opportunity", "field": "stage_name", "kind": "column", "title": "Stage"},
                {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "kind": "measure", "title": "Open ARR"},
                {"table": "f_opportunity", "field": "last_stage_change_date", "kind": "column", "title": "Last Stage Move"},
            ],
            x=20, y=510, w=1200, h=260,
        )
    )
```

- [ ] **Step 2: Pre-flight + push**

Run: `python3 -m scripts.sales.rw_compose_what_changed`
Expected: pre-flight passes; LRO succeeds. Browser shows the table populated with rows below the cards.

- [ ] **Step 3: Verify table renders properly (manual)**

In browser:

- Confirm rows aren't blank
- Confirm column count = 6
- Confirm Open ARR column shows $ values
- Note: top-N filtering is a per-visual filter; without it the table will show all open opps. Spec says "top 20 by ARR" — apply via the table's Visual filter pane manually for now (or extend `build_table_visual` later to take a `top_n` kwarg).

- [ ] **Step 4: Commit**

```bash
git add scripts/sales/rw_compose_what_changed.py
git commit -m "feat(track:rw): What Changed — detail table (Top open opps by ARR)"
```

---

## Phase 4 — Polish + capture loop

### Task 5: Window slicer placeholder

**Goal:** reserve the (1000, 20, 240×90) slot for a future window slicer per spec. Today's measures bake the window into the name (1d / 7d / FQTD). Field-parameter slicer schema not in `_pbir_shapes.py` PENDING list — needs browser capture.

**Files:**

- Modify: `scripts/sales/rw_compose_what_changed.py`

- [ ] **Step 1: Add a textbox or basicShape placeholder**

`textbox` is on the PENDING list — schema not yet captured. Two options:

- (a) Skip the placeholder; document the spec deviation in the build doc
- (b) Capture textbox shape via `rw_capture_visual` (browser-author a textbox in the live editor first)

For this task, choose (a). Add a comment in the script noting the spec deviation:

```python
    # Spec calls for a window slicer at (1000, 20). Field-parameter
    # slicer shape not yet captured in _pbir_shapes.py — defer until
    # we live-author one and capture via rw_capture_visual. Today's
    # cards use the 7d window baked into the measure name.
```

- [ ] **Step 2: Commit (no live deploy needed)**

```bash
git add scripts/sales/rw_compose_what_changed.py
git commit -m "docs(track:rw): note window-slicer deferral on What Changed"
```

---

### Task 6: Build-doc update

**Files:**

- Modify: `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`

- [ ] **Step 1: Append a What Changed Composition section**

```markdown
## 2026-05-08 — Tab 1 (What Changed) shipped

Composed via `scripts/sales/rw_compose_what_changed.py`. Idempotent; re-run
to rebuild from scratch.

**Visuals shipped (12):**

- Risk band: At Risk · Watch · Healthy × {count, ARR} = 6 cards
- Change buckets: Stage Moves (count + ARR) · New Opps · Won · Lost = 5 cards
- Detail table: Top open opps by Open ARR (6 columns) = 1 table

**Spec deviations (path-(a) deferrals):**

- Slips card: needs `f_ofh_close_date` ETL (deferred per foundation)
- Detail table "Change" + "Risk class" columns: row-context measures TBD
- Detail table top-20 filter: apply via PBI Visual filter pane manually until
  `build_table_visual` grows a `top_n` kwarg
- Window slicer: field-parameter shape not in `_pbir_shapes.py`; cards use
  the 7d window today
- Conditional formatting on Risk band: `objects` shape not yet captured

**To rebuild:** `python3 -m scripts.sales.rw_compose_what_changed`
```

- [ ] **Step 2: Commit**

```bash
git add docs/sales/RW_VPOPS_DASHBOARD_BUILD.md
git commit -m "docs(track:rw): document What Changed tab composition"
```

---

## Self-review notes

**Spec coverage:**

| Spec element                                 | Status                                               |
| -------------------------------------------- | ---------------------------------------------------- |
| Window slicer at top                         | Deferred (Task 5 placeholder)                        |
| Risk band (3 cards)                          | ✓ shipped as 6 cards (count+ARR each) — Task 2       |
| Change buckets (4 cards)                     | ✓ 3 of 4 (Slips deferred) — Task 3                   |
| Detail table top-20                          | ✓ table shipped; top-20 filter manual today — Task 4 |
| RAG colors on cards                          | Deferred (Task 6 follow-up via `rw_capture_visual`)  |
| Layout standards (mono numerics, RAG colors) | Inherited from PBI defaults; CF deferred             |

**Validation strategy:** every push runs through `validate_visual_dict` against the live model. Catches measure typos before LRO. Already proven on the foundation phase.

**Pre-existing column dependencies (verify pre-task; bail if missing):**

- `f_opportunity[opp_name]`, `[account_name]`, `[region]`, `[stage_name]`, `[last_stage_change_date]` (all in deployed model — confirmed via `rw_inventory_measures` table block)
- Measures: `At Risk Opps Count/ARR`, `Watch Opps Count/ARR`, `Healthy Moves Count/ARR`, `Stage Moves Count 7d`, `Stage Moves ARR 7d`, `New Opps Count 7d`, `Closed Won Count 7d`, `Closed Lost Count 7d`, `Total Open Pipeline ARR` (all confirmed via rw_validate against the proposed dict before push)

**Out of scope (next per-tab plans):**

- Forecast tab composition
- Stage Hygiene tab (matrix + S3 gate panel + stall coaching)
- Renewals tab (cohort table + at-risk drilldown)
- Growth Mix tab (mostly deferred until ETL extensions ship)
- ETL extension to add `Stage_20_Approval__c`, CloseDate OFH, `APTS_RH_ASP_Annual__c`
- `build_table_visual` `top_n` kwarg
- Capture field-parameter slicer + textbox shapes from a browser-authored example
