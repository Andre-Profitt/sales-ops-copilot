# VP Ops Front-Page Spine Rebuild (PR1) — Design Spec

**Date:** 2026-05-09
**Track:** `track:rw`
**Status:** approved (brainstorm), pending implementation plan
**Owner:** Andre
**Predecessor work:** Codex's `303bc6b` (Zebra Exceptions lab proof) + Claude's `c419313..415bc37` (Zebra BI Knowledge Graph)
**Successor work:** PR2 spec (movement waterfall + gate-violation exception column + 5 new ARR/gate measures)

## Purpose

Replace the 45-visualContainer card wall on the live `VP Ops Scorecard` page (current state, verified 2026-05-09 against `tests/sales/test_rw_compose_scorecard_home.py:12`) with two structured spines + one compact KPI strip, using Zebra BI Tables grammar that Codex already proved renders against the live RW semantic model.

PR1 ships the **exception spine** (stalled-deal grammar) and the **KPI strip**. Both are bindable to existing measures — no new DAX. PR2 will add the **movement spine** (waterfall over 4 new ARR-7d measures) and a **gate-violation column** (1 new measure that joins to `Stage_20_Approval__c`).

## Scope

**In scope (PR1):**

- Rewrite `scripts/sales/rw_compose_scorecard_home.py:PAGE = "VP Ops Scorecard"` around three sections (`_build_exception_spine`, `_build_movement_spine_placeholder`, `_build_kpi_strip`)
- Lab-first deploy: apply to `~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/` first, render-verify in Power BI Desktop, then promote to live Fabric workspace `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
- Delete the existing 45-visualContainer card-wall pattern that the current `rw_compose_scorecard_home.py` instantiates (no deprecation, no half-states)
- Use existing measures only — bindings are validated by `data/zebra_kg_rw/bindings.jsonl` (33/33 bound)
- Update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` with the rebuild's render proof + screenshot evidence

**Out of scope (deferred to PR2):**

- Movement waterfall — needs 4 new ARR-7d measures (`New Opps ARR 7d`, `Closed Won ARR 7d`, `Closed Lost ARR 7d`, `Backward Moves ARR 7d`) + start/end period boundaries
- Gate-violation exception column — needs 1 new measure `Commercial Approval Gate Exception ARR` that joins f_opportunity to the SF `Stage_20_Approval__c` field
- Margin review / KYC gate exceptions — sfkg shows zero SF coverage for these, so we'd be authoring measures with no underlying data; defer until SF closes that gap
- Re-styling of `What Changed`, `Forecast`, or any other tab — only `VP Ops Scorecard` page in this PR

## Non-goals

- Custom-visual color tuning — Zebra's defaults are good enough, and the spec's prior brainstorm rule applies (no theme remap, no NAVY substitution)
- Tracker/comments layer — the dynamic-comments template grammar is a v3 enhancement, not v1
- Workforce or other project overlays — PR1 is RW VP Ops only

## Background — what each finding tells us

**The Zebra Tables proof already works.** Codex's `303bc6b` lab proof renders Zebra BI Tables against the live RW semantic model with `d_region[region]` × `Exception ARR / Exception Opps Count / At Risk Opps ARR / Watch Opps ARR`. The Zebra license activated 2026-05-09 (trial expires 2026-06-08). The harness fix in `_pbir_helpers.py` (group projections under `Primary` instead of native-table-style `Primary` / `Secondary` split) is the binding pattern this spec lifts.

**`Exception ARR` semantics — internally consistent, but distinct from the brief.** The deployed RW DAX defines exceptions as **stage-age** (Watch = stages 3–4 stalled >14d; At Risk = stages 5–7 stalled >21d, both Land+Expand only). The morning-brief alert "Stage 3+ ≥$500k no Commercial Approval" defines exceptions as **gate violations** against `Stage_20_Approval__c`. Two non-overlapping lists. PR1 surfaces stage-age exceptions (which is what the existing measure carries); PR2 adds the gate-violation column so dashboard and alerts share grammar.

**LAND / EXPAND / Renewal split — already honored at the measure layer.** Both stage-age measures filter `motion_type IN { "Land", "Expand" }`. The cardinal rule (`APTS_Opportunity_ARR__c` for Land+Expand vs `APTS_Renewal_ACV__c` for Renewals; never blend) is preserved. PR1 inherits this; the spine does not introduce any cross-motion measure on the front page.

**sfkg gate coverage — Commercial Approval is well-instrumented in SF (257 reports, 28 dashboards), Margin and KYC are not.** This sets PR2's measure-authoring boundary: only the Commercial Approval gate has the underlying SF field coverage to author a meaningful Fabric measure against.

## Architecture

### Page layout (1280×720)

```
+─────────────────────────────────────────────────────────────────────────+
| Page title row (textbox)                                                |
| ──────────────────────────────────────────────────────────────────────  |
| EXCEPTION SPINE                                                         |
|   Zebra BI Tables: d_region[region]                                     |
|   × Exception ARR | At Risk Opps ARR | Watch Opps ARR | Exception Opps  |
|     Count                                                               |
|   Height: ~280 px                                                       |
| ──────────────────────────────────────────────────────────────────────  |
| MOVEMENT SPINE PLACEHOLDER                                              |
|   Empty rectangle with textbox: "Movement spine — see PR2"              |
|   Height: ~240 px                                                       |
| ──────────────────────────────────────────────────────────────────────  |
| KPI STRIP                                                               |
|   Zebra BI Cards row (or 4 native cards as fallback)                    |
|   × Total Closed Won ARR | Win Rate ARR | Stage Forward Pct (LE)        |
|     | Renewal Retention Pct (Period)                                    |
|   Height: ~140 px                                                       |
+─────────────────────────────────────────────────────────────────────────+
```

The placeholder section is intentional — it preserves vertical real-estate for PR2's waterfall and signals to the executive viewer that "what changed" is coming, rather than the rebuild looking permanently incomplete.

### Why these three sections

- **Exception spine first** — executives scan top-to-bottom; the highest-decision signal goes first. Stalled deals at high ARR are the immediate "act today" list.
- **Movement spine middle** (placeholder in PR1) — the "why is the pipeline at $X today" answer; a waterfall is the canonical Zebra grammar for this question.
- **KPI strip last** — context floor. Single-row glance KPIs that anchor the viewer in win-rate / retention / stage-progression health. Compact = no card-wall regression.

### Files modified

| File                                            | Change                                                                                                                                                            |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/sales/rw_compose_scorecard_home.py`    | Rewritten around 3 builders. Existing 45-visualContainer card-wall pattern deleted. Existing `PAGE = "VP Ops Scorecard"` constant retained.                       |
| `tests/sales/test_rw_compose_scorecard_home.py` | New tests for each builder; existing tests updated or deleted to match the new layout.                                                                            |
| `scripts/sales/rw_apply_zebra_lab_proof.py`     | Extended (or sibling script added) to apply the _full_ three-section layout to the lab PBIP, not just the single Zebra Exceptions visual that `303bc6b` produced. |
| `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`        | Append a "Front-page spine rebuild — PR1" section with render-proof screenshot path.                                                                              |

### Components

#### `_build_exception_spine(values: list[dict]) -> dict`

Returns one PBIR `visualContainer` for a Zebra BI Tables visual. Lifts the binding pattern verbatim from `rw_apply_zebra_lab_proof.py:apply_zebra_exceptions_proof()` (Codex `303bc6b`). The signature matches `_pbir_helpers.build_zebra_bi_table_visual()`'s calling convention.

- visual type: `Zebra-BI-Tables` (custom visual GUID per `_pbir_helpers.py`)
- projection role: `Primary` (category + values combined under one role per the lab fix)
- bindings:
  - Category: `d_region[region]`
  - Values (in this exact order — matches Codex's lab proof; Zebra Tables uses positional ordering for IBCS column grouping, so re-ordering is a render regression):
    1. `Exception ARR`
    2. `Exception Opps Count`
    3. `At Risk Opps ARR`
    4. `Watch Opps ARR`
- position: x=0, y=80, w=1280, h=264 (see Layout table below)
- formatting: Zebra's default IBCS palette (no theme override)

#### `_build_movement_spine_placeholder() -> dict`

Returns a single textbox visualContainer with the text "Movement spine — see PR2 (`Pipeline ARR last 7d` waterfall, pending new ARR-7d measures)". Position x=0, y=360, w=1280, h=224. Background light grey to read as "wireframe placeholder" not "empty space."

#### `_build_kpi_strip() -> list[dict]`

Returns 4 visualContainers, each a Zebra BI Card (or — fallback — a native `kpiVisual`):

| KPI               | Measure                          | Rationale                                                           |
| ----------------- | -------------------------------- | ------------------------------------------------------------------- |
| Closed Won FQTD   | `Total Closed Won ARR`           | Quarter-to-date wins, ARR — primary outcome KPI                     |
| Win Rate          | `Win Rate ARR`                   | Conversion health, ARR-weighted                                     |
| Stage Hygiene     | `Stage Forward Pct (LE)`         | Process governance — % stages moving forward (LE = leading edge)    |
| Renewal Retention | `Renewal Retention Pct (Period)` | Renewal health, ACV side (see "Cardinal-rule justification" below). |

**Cardinal-rule justification for Renewal Retention co-display.** The rule from `~/.claude/CLAUDE.md.shared` is: _"ARR=Land+Expand (`APTS_Opportunity_ARR__c`) · ACV=Renewals (`APTS_Renewal_ACV__c`) · NEVER blend."_ The "blend" prohibition applies to the **compute layer** — a single metric must not sum ARR and ACV. A KPI strip is a **display layer**: each card renders one measure, computed independently, with its own format string. Showing ARR-side health (cards 1–3) alongside Renewal-side health (card 4) is standard enterprise scorecard practice — these are the two halves of total revenue health, and surfacing them separately on the same row is the _correct_ way to show executives both numbers without inviting a blended computation. The deployed DAX confirms separation: `Win Rate ARR` reads `f_opportunity[arr_org_ccy]`; `Renewal Retention Pct (Period)` reads `APTS_Renewal_ACV__c`. No measure crosses the boundary.

Each card has: title, current value with format string from the measure's TMDL, **and (Zebra Cards only)** sparkline over last 4 quarters, embedded variance arrow vs. PY. If the lab apply takes the native `kpiVisual` fallback (see Open questions), sparklines and variance arrows are deferred to PR2 — the cards still render with title + value. Cards are positioned: x=0/320/640/960, y=600, w=320, h=120.

### Layout zones (explicit, sums to 720)

| Zone                 | x             | y   | w    | h   | Notes                                                                                                                 |
| -------------------- | ------------- | --- | ---- | --- | --------------------------------------------------------------------------------------------------------------------- |
| Page title (textbox) | 0             | 0   | 1280 | 64  | Single-line title; matches the existing header padding (current code uses y=16 h=58; rounded up to 64 for clean math) |
| Exception spine      | 0             | 80  | 1280 | 264 | 16 px gap above (intentional breathing room)                                                                          |
| Movement placeholder | 0             | 360 | 1280 | 224 | 16 px gap above (separates exception from movement bands)                                                             |
| KPI strip (4 cards)  | 0/320/640/960 | 600 | 320  | 120 | 16 px gap above the strip; cards span full width                                                                      |

Total: 64 + 16 + 264 + 16 + 224 + 16 + 120 = **720 px**. No overlap, no overflow.

### Data flow

```
rw_compose_scorecard_home.py (composer)
    │
    ├─ _build_exception_spine() ─► PBIR visualContainer (Zebra Tables)
    ├─ _build_movement_spine_placeholder() ─► PBIR visualContainer (textbox)
    └─ _build_kpi_strip() ─► 4 PBIR visualContainers (Zebra Cards / native KPIs)
        │
        └─► assembled into the "VP Ops Scorecard" section's visualContainers list

Lab apply:
    rw_apply_zebra_lab_proof.py --target lab_pbip
        ─► writes the new visualContainers into rpt_vp_ops_scorecard.Report/report.json
        ─► preserves Zebra license blob (existing behavior)
        ─► Power BI Desktop opens the lab → render proof → screenshot

Live promote:
    python3 -m scripts.sales.rw_push_report
        ─► reads WORKSPACE_ID + REPORT_NAME from module-level constants
           (no argparse — the existing CLI shape; do NOT add flags in PR1)
        ─► uses same composer output, posts to Fabric REST
        ─► uses azure-identity/AzureCliCredential (existing auth path)
```

### Card deletion list (the 45 visualContainers that go away)

The existing `rw_compose_scorecard_home.py:_compose()` emits **45 visualContainers** on the front page (verified 2026-05-09: 3 header + 5 left-rail filter + 7 left-rail contract + 10 top exception row + 8 middle band + 9 bottom band = 45). The current `tests/sales/test_rw_compose_scorecard_home.py` line 12 asserts `len(visuals) == 45` and is the authoritative anchor. Per the brainstorm rule "Don't keep the card wall and just swap visual types," PR1 deletes (not deprecates) the helper-call patterns that produce these 45 visuals. The new layout emits **7 visualContainers** (1 title + 1 exception spine + 1 movement placeholder + 4 KPI cards). The exact deletion list belongs in the implementation plan; the spec commits to the count delta (45 → 7) as the success criterion.

## Error handling

- **Lab apply errors** — if the Zebra license blob is missing in the lab PBIP, `rw_apply_zebra_lab_proof.py` already logs a warning and proceeds. Reuse that pattern. Don't fail the apply just because license validation deferred to first Desktop open.
- **Live push errors** — Fabric REST throws on schema drift (e.g., a referenced measure that's been renamed). The composer must validate every measure name it emits against `fetch_measures_by_table()` output before pushing. If a measure is missing, FAIL FAST with a clear error pointing at the missing measure name.
- **Render-proof gate** — the spec REQUIRES a Desktop screenshot of the lab PBIP rendering before the live push runs. No "shipped, will verify later" — the lab proof is the precondition for live promote.

## Testing

- `tests/sales/test_rw_compose_scorecard_home.py`:
  - `test_compose_emits_seven_visualcontainers` — replaces the existing `len(visuals) == 45` assertion at `tests/sales/test_rw_compose_scorecard_home.py:12`. New assertion: `len(visuals) == 7` (1 page-title textbox + 1 exception Zebra Table + 1 placeholder textbox + 4 KPI cards).
  - `test_exception_spine_value_order_matches_lab_proof` — the value projection list, in order, is exactly `["Exception ARR", "Exception Opps Count", "At Risk Opps ARR", "Watch Opps ARR"]`. Locks against accidental reordering, since Zebra Tables uses positional ordering for IBCS column grouping.
  - `test_exception_spine_binds_existing_measures` — every measure name in the spine's value projections appears in `fetch_measures_by_table()`'s output.
  - `test_kpi_strip_binds_existing_measures` — same check for the strip.
  - `test_movement_placeholder_is_textbox_not_zebra` — confirms PR1 doesn't accidentally ship a half-built waterfall (the placeholder visual's `visualType` is `textbox`, not any Zebra GUID).
  - `test_layout_zones_sum_to_720px` — pure unit test over the layout-zone table: total y+h closes to exactly 720, no overlap, gap math matches the spec.

- Render proof — manual, but documented in `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` per the lab-first protocol.

- Pre-commit secret scan — match the existing pattern from Codex's `303bc6b`: scan `scripts/sales/`, `tests/sales/`, `docs/sales/` for the Zebra trial token substring before commit.

## Deployment sequence

1. Implementation plan (next) — TDD, bite-sized.
2. Land all changes on `feat/track-rw-tooling` (continues the existing track:rw branch).
3. Apply to lab PBIP (`rw_apply_zebra_lab_proof.py` extended for the three-section layout).
4. Open lab in Power BI Desktop on the Parallels VM (32 GB / 8 CPU, just resized). Verify render. Capture screenshot to `~/.frontier/artifacts/rw_vpops_spine_rebuild_<date>.png`.
5. Update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`.
6. Run full `pytest tests/sales/`.
7. Push to remote — Codex reviews at branch level.
8. After Codex review: promote to live Fabric (`rw_push_report.py`).
9. Smoke-check live workspace; confirm no Renewal ACV blending in the rendered cards (visual confirmation of the cardinal rule).

## Open questions deferred to plan

- Whether the KPI strip uses Zebra BI Cards (custom visual, license-bound) or native `kpiVisual` (no license dependency, simpler render). Recommendation: Zebra Cards for consistency with the spine; native fallback if Cards have a binding quirk we hit during the lab apply. Decide post-lab.
- Whether `rw_apply_zebra_lab_proof.py` is extended in-place or a sibling script `rw_apply_spine_rebuild.py` is added. Decide based on the diff size during implementation.

## Risk register

| Risk                                                                            | Likelihood | Mitigation                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zebra Cards binding quirk (only Tables proved so far)                           | Medium     | Lab-first protocol catches this; native fallback documented as a switch                                                                                                                                                                                                                                                                                                                                                      |
| Existing front-page consumers break (other reports referencing this page name?) | Low        | Page name unchanged (`VP Ops Scorecard`); only inner visualContainer set is rewritten                                                                                                                                                                                                                                                                                                                                        |
| Trial license expiry mid-build                                                  | Low        | 30-day window (expires 2026-06-08); PR1 + PR2 both fit comfortably                                                                                                                                                                                                                                                                                                                                                           |
| Cardinal rule violation (Renewal ACV blended into ARR)                          | Low        | All four spine + strip measures already isolate Land+Expand or Renewal cleanly; verified by reading deployed DAX                                                                                                                                                                                                                                                                                                             |
| Codex and Claude touching the composer in parallel                              | Medium     | (a) PR1 implementation pushes a per-file lock signal: prepend `# REBUILD IN PROGRESS — see specs/2026-05-09-vp-ops-front-page-spine-rebuild-design.md — DO NOT MODIFY UNTIL MERGED` at the top of `rw_compose_scorecard_home.py` as the FIRST commit of the implementation, removed at merge. (b) Push branch frequently so Codex sees PR1 progress at `git pull` time. (c) Spec committed before code; both agents read it. |

## Out-of-scope reminders

- No DAX authoring in PR1.
- No Workforce / Forecast / What Changed tab edits — VP Ops Scorecard page only.
- No theme JSON changes — the existing theme is the brand pattern per memory.
- No PBIX export attempts — `getDefinition` is the only push path that works against the tenant; no Desktop-export fallback.
